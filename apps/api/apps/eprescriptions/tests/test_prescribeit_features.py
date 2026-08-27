"""
The PrescribeIT-style features layered on top of the base e-prescribing flow:
  - Create Rx: a doctor can send directly to a chosen pharmacy instead of the patient
    carrying a QR/PIN, and that pharmacy can then dispense without one.
  - Renew Rx: a pharmacy with legitimate contact with a prescription can request a
    renewal; the doctor can approve (issuing a fresh linked prescription) or deny.
  - Prescription Cancel: a targeted pharmacy is notified when the doctor cancels.
  - Rx Status: a pharmacist substitution is pushed back to the doctor.
  - Clinical Communication: doctor and target pharmacy can message each other.
  - Formulary Services: a doctor can look up a named patient's known insurance coverage.
  - Guaranteed delivery: fax is a back-up channel when the prescription can't reach the
    patient by email (none on file, or the send fails).
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.eprescriptions.models import Prescription, PrescriptionRenewalRequest
from apps.eprescriptions.services.issue import cancel_prescription, issue_prescription
from apps.eprescriptions.services.renewal import RenewalError, request_renewal, respond_to_renewal
from apps.insurance.models import InsurancePlan, InsuranceProvider, PatientInsurancePolicy
from apps.medicines.models import Medicine
from apps.messaging.models import Conversation
from apps.pharmacies.models import Pharmacy

from .test_prescription_flow import make_doctor


def make_pharmacy(**overrides) -> Pharmacy:
    defaults = dict(
        name="Cedar Care",
        area="Hamra",
        city="Beirut",
        address="Hamra street",
        phone="+961-1-000-000",
        whatsapp="+96170111111",
        latitude=Decimal("33.8975"),
        longitude=Decimal("35.4790"),
        is_active=True,
    )
    defaults.update(overrides)
    return Pharmacy.objects.create(**defaults)


def make_pharmacy_user(pharmacy, *, email="owner@hamra.test"):
    return get_user_model().objects.create_user(email=email, password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=pharmacy)


class CreateRxTargetingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = make_doctor()
        self.pharmacy = make_pharmacy()
        self.pharmacy_user = make_pharmacy_user(self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")

    def test_doctor_sends_directly_to_a_pharmacy(self):
        self.client.force_authenticate(user=self.doctor.user)

        result = self.client.post(
            "/api/doctor/prescriptions/",
            {
                "patient_name": "Georges Haddad",
                "target_pharmacy": str(self.pharmacy.id),
                "items": [{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            },
            format="json",
        )

        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(str(result.data["target_pharmacy"]), str(self.pharmacy.id))

        self.client.force_authenticate(user=self.pharmacy_user)
        incoming = self.client.get("/api/pharmacy/incoming-prescriptions/")
        self.assertEqual([entry["code"] for entry in incoming.data["results"]], [result.data["code"]])

    def test_deferred_transmission_is_unchanged_when_no_pharmacy_is_chosen(self):
        self.client.force_authenticate(user=self.doctor.user)

        result = self.client.post(
            "/api/doctor/prescriptions/",
            {"patient_name": "Georges Haddad", "items": [{"medicine": str(self.medicine.id), "quantity_prescribed": 14}]},
            format="json",
        )

        self.assertEqual(result.status_code, 201, result.data)
        self.assertIsNone(result.data["target_pharmacy"])

        self.client.force_authenticate(user=self.pharmacy_user)
        incoming = self.client.get("/api/pharmacy/incoming-prescriptions/")
        self.assertEqual(incoming.data["results"], [])

    def test_targeted_pharmacy_can_dispense_without_a_qr_or_pin(self):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )
        item = prescription.items.first()
        self.client.force_authenticate(user=self.pharmacy_user)

        result = self.client.post(
            f"/api/pharmacy/incoming-prescriptions/{prescription.id}/dispense/",
            {"pharmacist_name": "M. Saab", "items": [{"prescription_item": str(item.id), "quantity": 14}]},
            format="json",
        )

        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["status"], Prescription.Status.FULLY_DISPENSED)

    def test_a_different_pharmacy_cannot_see_or_dispense_a_targeted_prescription(self):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )
        other_pharmacy = make_pharmacy(name="Other Pharmacy", phone="+961-1-000-002", whatsapp="+96170333333")
        other_user = make_pharmacy_user(other_pharmacy, email="owner@other.test")
        self.client.force_authenticate(user=other_user)

        listing = self.client.get("/api/pharmacy/incoming-prescriptions/")
        self.assertEqual(listing.data["results"], [])

        result = self.client.post(
            f"/api/pharmacy/incoming-prescriptions/{prescription.id}/dispense/",
            {"pharmacist_name": "X", "items": [{"prescription_item": str(prescription.items.first().id), "quantity": 1}]},
            format="json",
        )
        self.assertEqual(result.status_code, 404)


class CancelNotifiesTargetPharmacyTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.pharmacy = make_pharmacy()
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")

    def test_cancelling_a_targeted_prescription_messages_the_pharmacy(self):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )

        cancel_prescription(prescription=prescription, reason="Patient improved")

        conversation = Conversation.objects.get(prescription=prescription)
        message = conversation.messages.get()
        self.assertIn("cancelled", message.body)
        self.assertIn("Patient improved", message.body)

    def test_cancelling_a_deferred_prescription_sends_no_message(self):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor, patient={"patient_name": "Georges Haddad"}, items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}]
        )

        cancel_prescription(prescription=prescription)

        self.assertFalse(Conversation.objects.filter(prescription=prescription).exists())


class DispenseSubstitutionNotifiesDoctorTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.pharmacy = make_pharmacy()
        self.pharmacy_user = make_pharmacy_user(self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")
        self.client = APIClient()

    def test_a_substitution_notifies_the_doctor(self):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )
        item = prescription.items.first()
        self.client.force_authenticate(user=self.pharmacy_user)

        result = self.client.post(
            f"/api/pharmacy/incoming-prescriptions/{prescription.id}/dispense/",
            {"pharmacist_name": "M. Saab", "items": [{"prescription_item": str(item.id), "quantity": 14, "substituted_with": "Clavamox 1g"}]},
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)

        conversation = Conversation.objects.get(prescription=prescription)
        message = conversation.messages.get()
        self.assertIn("Clavamox 1g", message.body)


class RenewalRequestTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.pharmacy = make_pharmacy()
        self.pharmacy_user = make_pharmacy_user(self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")
        self.prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )
        self.client = APIClient()

    def test_pharmacy_without_contact_with_the_prescription_cannot_request_a_renewal(self):
        other_pharmacy = make_pharmacy(name="Other Pharmacy", phone="+961-1-000-002", whatsapp="+96170333333")

        with self.assertRaises(RenewalError):
            request_renewal(prescription=self.prescription, pharmacy=other_pharmacy, requested_by_user=None)

    def test_approving_a_renewal_issues_a_linked_prescription(self):
        renewal_request = request_renewal(prescription=self.prescription, pharmacy=self.pharmacy, requested_by_user=self.pharmacy_user, note="Refill needed")

        approved = respond_to_renewal(renewal_request=renewal_request, approve=True)

        self.assertEqual(approved.status, PrescriptionRenewalRequest.Status.APPROVED)
        self.assertIsNotNone(approved.new_prescription)
        self.assertEqual(approved.new_prescription.renewed_from_id, self.prescription.id)
        self.assertEqual(approved.new_prescription.target_pharmacy_id, self.pharmacy.id)
        self.assertEqual(approved.new_prescription.items.first().quantity_prescribed, 14)

    def test_denying_a_renewal_issues_nothing(self):
        renewal_request = request_renewal(prescription=self.prescription, pharmacy=self.pharmacy, requested_by_user=self.pharmacy_user)

        denied = respond_to_renewal(renewal_request=renewal_request, approve=False, response_note="Needs an in-person visit")

        self.assertEqual(denied.status, PrescriptionRenewalRequest.Status.DENIED)
        self.assertIsNone(denied.new_prescription)

    def test_a_second_pending_request_is_rejected(self):
        request_renewal(prescription=self.prescription, pharmacy=self.pharmacy, requested_by_user=self.pharmacy_user)

        with self.assertRaises(RenewalError):
            request_renewal(prescription=self.prescription, pharmacy=self.pharmacy, requested_by_user=self.pharmacy_user)

    def test_end_to_end_via_the_api(self):
        self.client.force_authenticate(user=self.pharmacy_user)
        created = self.client.post("/api/pharmacy/renewal-requests/", {"prescription": str(self.prescription.id), "note": "Refill needed"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)

        self.client.force_authenticate(user=self.doctor.user)
        pending = self.client.get("/api/doctor/renewal-requests/")
        self.assertEqual(len(pending.data["results"]), 1)

        responded = self.client.post(f"/api/doctor/renewal-requests/{created.data['id']}/respond/", {"approve": True}, format="json")
        self.assertEqual(responded.status_code, 200, responded.data)
        self.assertEqual(responded.data["status"], "APPROVED")

    def test_other_doctors_cannot_see_or_respond_to_this_renewal_request(self):
        renewal_request = request_renewal(prescription=self.prescription, pharmacy=self.pharmacy, requested_by_user=self.pharmacy_user)
        other_doctor = make_doctor(email="other@doctors.test", license_number="LB-MD-OTHER")
        self.client.force_authenticate(user=other_doctor.user)

        listing = self.client.get("/api/doctor/renewal-requests/")
        self.assertEqual(listing.data["results"], [])

        result = self.client.post(f"/api/doctor/renewal-requests/{renewal_request.id}/respond/", {"approve": True}, format="json")
        self.assertEqual(result.status_code, 404)


class ClinicalCommunicationTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.pharmacy = make_pharmacy()
        self.pharmacy_user = make_pharmacy_user(self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")
        self.prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            target_pharmacy=self.pharmacy,
        )
        self.client = APIClient()

    def test_pharmacy_and_doctor_can_message_each_other_on_the_same_thread(self):
        self.client.force_authenticate(user=self.pharmacy_user)
        sent = self.client.post(f"/api/pharmacy/prescriptions/{self.prescription.id}/messages/", {"body": "Do you have a generic preference?"}, format="json")
        self.assertEqual(sent.status_code, 201, sent.data)

        self.client.force_authenticate(user=self.doctor.user)
        thread = self.client.get(f"/api/doctor/prescriptions/{self.prescription.id}/messages/")
        self.assertEqual(len(thread.data), 1)
        self.assertEqual(thread.data[0]["body"], "Do you have a generic preference?")

        reply = self.client.post(f"/api/doctor/prescriptions/{self.prescription.id}/messages/", {"body": "Generic is fine."}, format="json")
        self.assertEqual(reply.status_code, 201, reply.data)

        self.assertEqual(Conversation.objects.get(prescription=self.prescription).messages.count(), 2)

    def test_pharmacy_cannot_message_a_prescription_not_targeted_at_it(self):
        untargeted, _s, _p = issue_prescription(doctor=self.doctor, patient={"patient_name": "Someone Else"}, items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 1}])
        self.client.force_authenticate(user=self.pharmacy_user)

        result = self.client.get(f"/api/pharmacy/prescriptions/{untargeted.id}/messages/")
        self.assertEqual(result.status_code, 404)


class FaxBackupDeliveryTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")

    def test_no_email_on_file_falls_back_to_fax(self):
        prescription, _secret, pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad", "patient_fax": "+961-1-555-000"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
        )

        self.assertIsNone(prescription.email_sent_at)
        self.assertIsNotNone(prescription.fax_sent_at)

    def test_failed_email_send_falls_back_to_fax(self):
        with patch("apps.eprescriptions.services.mailer.send_email", side_effect=RuntimeError("SMTP down")):
            prescription, _secret, pin = issue_prescription(
                doctor=self.doctor,
                patient={"patient_name": "Georges Haddad", "patient_email": "georges@example.test", "patient_fax": "+961-1-555-000"},
                items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
            )

        self.assertIsNone(prescription.email_sent_at)
        self.assertIsNotNone(prescription.fax_sent_at)

    def test_successful_email_does_not_use_fax(self):
        prescription, _secret, pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad", "patient_email": "georges@example.test", "patient_fax": "+961-1-555-000"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
        )

        self.assertIsNotNone(prescription.email_sent_at)
        self.assertIsNone(prescription.fax_sent_at)

    def test_no_email_and_no_fax_still_issues_the_prescription(self):
        """The paper/e-signed copy handed to the patient is always the authoritative record -
        digital delivery is a convenience on top, never a precondition for issuing."""
        prescription, _secret, pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
        )

        self.assertIsNone(prescription.email_sent_at)
        self.assertIsNone(prescription.fax_sent_at)
        self.assertEqual(prescription.status, Prescription.Status.ISSUED)


class FormularyLookupTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.client = APIClient()
        self.shopper = get_user_model().objects.create_user(email="georges@example.test", password="Password123!", role=UserRole.CUSTOMER)
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        self.plan = InsurancePlan.objects.create(provider=provider, name="Gold", coverage_percentage=Decimal("80"), copay_minimum=Decimal("5"))
        PatientInsurancePolicy.objects.create(plan=self.plan, customer_user=self.shopper, member_id="GM-1", holder_name="Georges Haddad")

    def test_doctor_finds_the_patients_plan_by_email(self):
        self.client.force_authenticate(user=self.doctor.user)

        result = self.client.get("/api/doctor/formulary/lookup/", {"patient_email": "georges@example.test"})

        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual([entry["name"] for entry in result.data], ["Gold"])
        self.assertEqual(result.data[0]["coverage_percentage"], "80.00")

    def test_no_match_returns_an_empty_list_not_an_error(self):
        self.client.force_authenticate(user=self.doctor.user)

        result = self.client.get("/api/doctor/formulary/lookup/", {"patient_email": "nobody@example.test"})

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, [])

    def test_requires_a_search_parameter(self):
        self.client.force_authenticate(user=self.doctor.user)

        result = self.client.get("/api/doctor/formulary/lookup/")

        self.assertEqual(result.status_code, 400)

    def test_a_shopper_cannot_use_the_doctor_endpoint(self):
        self.client.force_authenticate(user=self.shopper)

        result = self.client.get("/api/doctor/formulary/lookup/", {"patient_email": "georges@example.test"})

        self.assertEqual(result.status_code, 403)
