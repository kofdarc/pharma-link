"""
E-prescription security and the partial-dispense rules.

A prescription is consumable by any pharmacy with no account, so the security properties
are the product: a leaked code must be useless, a tampered key must fail, brute force must
stall, and the prescribed quantity must be a hard ceiling even across different pharmacies.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.eprescriptions.models import Doctor, Prescription, PrescriptionAccessLog
from apps.eprescriptions.services.activation import ActivationError, activate_doctor
from apps.eprescriptions.services.access import PrescriptionAuthError, authenticate
from apps.eprescriptions.services.dispense import DispenseError, dispense_prescription
from apps.eprescriptions.services.issue import issue_prescription
from apps.medicines.models import DrugSchedule, Medicine, PriceRegime, ProductCategory
from apps.pharmacies.models import Pharmacy


def make_doctor(*, activated=True, email="doc@doctors.test", license_number="LB-MD-1") -> Doctor:
    doctor = Doctor.objects.create(
        license_number=license_number,
        full_name="Rima Khalil",
        email=email,
        specialty="Family medicine",
        is_active=True,
    )
    if activated:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(email=email, password="Password123!", role=UserRole.DOCTOR)
        doctor.user = user
        doctor.is_activated = True
        doctor.activated_at = timezone.now()
        doctor.save()
    return doctor


class DoctorActivationTests(TestCase):
    def test_roster_doctor_activates_with_licence_and_email(self):
        doctor = make_doctor(activated=False)

        activated = activate_doctor(license_number="LB-MD-1", email="doc@doctors.test", password="Str0ngPassphrase!")

        self.assertTrue(activated.is_activated)
        self.assertIsNotNone(activated.user)
        self.assertEqual(activated.user.role, UserRole.DOCTOR)
        self.assertEqual(activated.id, doctor.id)

    def test_wrong_email_is_rejected_without_revealing_whether_the_licence_exists(self):
        make_doctor(activated=False)

        with self.assertRaises(ActivationError) as unknown_licence:
            activate_doctor(license_number="LB-MD-DOES-NOT-EXIST", email="doc@doctors.test", password="Str0ngPassphrase!")
        with self.assertRaises(ActivationError) as wrong_email:
            activate_doctor(license_number="LB-MD-1", email="someone.else@doctors.test", password="Str0ngPassphrase!")

        self.assertEqual(str(unknown_licence.exception), str(wrong_email.exception))

    def test_activation_cannot_be_repeated(self):
        make_doctor(activated=False)
        activate_doctor(license_number="LB-MD-1", email="doc@doctors.test", password="Str0ngPassphrase!")

        with self.assertRaises(ActivationError):
            activate_doctor(license_number="LB-MD-1", email="doc@doctors.test", password="An0therPassphrase!")


class PrescriptionIssueTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.medicine = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")

    def test_secrets_are_not_stored_in_clear(self):
        prescription, secret, pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
        )

        self.assertNotIn(secret, prescription.secret_hash)
        self.assertNotIn(pin, prescription.pin_hash)
        self.assertEqual(len(prescription.secret_hash), 64)
        self.assertTrue(prescription.pin_hash.startswith("pbkdf2_"))
        self.assertNotEqual(prescription.secret_hash, prescription.pin_hash)

    def test_unactivated_doctor_cannot_issue(self):
        dormant = make_doctor(activated=False, email="dormant@doctors.test", license_number="LB-MD-2")

        with self.assertRaises(Exception):
            issue_prescription(
                doctor=dormant,
                patient={"patient_name": "Anyone"},
                items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 1}],
            )

    def test_patient_email_receives_the_prescription(self):
        from django.core import mail

        _prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad", "patient_email": "georges@example.test"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 14}],
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("georges@example.test", mail.outbox[0].to)
        message = mail.outbox[0]
        html = message.alternatives[0].content
        self.assertIn('src="cid:prescription-qr"', html)
        self.assertIn('src="cid:healthconnect-logo"', html)
        self.assertTrue(any(
            isinstance(attachment, tuple) and attachment[0].endswith(".png")
            for attachment in message.attachments
        ))
        self.assertTrue(any(
            not isinstance(attachment, tuple) and attachment.get("Content-ID") == "<prescription-qr>"
            for attachment in message.attachments
        ))


class PrescriptionAccessTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price="2.25")
        self.prescription, self.secret, self.pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 20}],
        )

    def test_correct_qr_key_grants_access(self):
        prescription, method = authenticate(code=self.prescription.code, key=self.secret)

        self.assertEqual(prescription.id, self.prescription.id)
        self.assertEqual(method, "QR")

    def test_correct_pin_grants_access_for_manual_entry(self):
        _prescription, method = authenticate(code=self.prescription.code, pin=self.pin)

        self.assertEqual(method, "MANUAL")

    def test_code_alone_is_not_enough(self):
        with self.assertRaises(PrescriptionAuthError) as context:
            authenticate(code=self.prescription.code, key="", pin="")

        self.assertEqual(context.exception.status, 403)

    def test_tampered_key_is_rejected(self):
        tampered = self.secret[:-2] + ("aa" if not self.secret.endswith("aa") else "bb")

        with self.assertRaises(PrescriptionAuthError):
            authenticate(code=self.prescription.code, key=tampered)

    @override_settings(PRESCRIPTION_MAX_FAILED_ATTEMPTS=3, PRESCRIPTION_LOCKOUT_MINUTES=15)
    def test_repeated_bad_pins_lock_the_prescription(self):
        for _attempt in range(3):
            with self.assertRaises(PrescriptionAuthError):
                authenticate(code=self.prescription.code, pin="000000")

        with self.assertRaises(PrescriptionAuthError) as context:
            authenticate(code=self.prescription.code, pin=self.pin)  # even the right PIN is refused while locked
        self.assertEqual(context.exception.status, 429)

    def test_every_attempt_is_logged(self):
        authenticate(code=self.prescription.code, key=self.secret)
        with self.assertRaises(PrescriptionAuthError):
            authenticate(code=self.prescription.code, pin="999999")

        actions = list(PrescriptionAccessLog.objects.values_list("action", flat=True))
        self.assertIn(PrescriptionAccessLog.Action.VIEW, actions)
        self.assertIn(PrescriptionAccessLog.Action.AUTH_FAILED, actions)

    def test_unknown_code_is_logged_and_refused(self):
        with self.assertRaises(PrescriptionAuthError):
            authenticate(code="RX-ZZZZ-ZZZZ", key="anything")

        self.assertTrue(PrescriptionAccessLog.objects.filter(action=PrescriptionAccessLog.Action.AUTH_FAILED, code_attempted="RX-ZZZZ-ZZZZ").exists())

    def test_cancelled_prescription_cannot_be_opened(self):
        self.prescription.status = Prescription.Status.CANCELLED
        self.prescription.save()

        with self.assertRaises(PrescriptionAuthError) as context:
            authenticate(code=self.prescription.code, key=self.secret)

        self.assertEqual(context.exception.status, 409)


class PrescriptionDispenseTests(TestCase):
    def setUp(self):
        self.doctor = make_doctor()
        self.antibiotic = Medicine.objects.create(brand_name="Augmentin", strength="1g", form="Tablet", regulated_price="14.75")
        self.painkiller = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price="2.25")
        self.prescription, self.secret, self.pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad"},
            items=[
                {"medicine": str(self.antibiotic.id), "medicine_text": "Augmentin 1g", "quantity_prescribed": 14},
                {"medicine": str(self.painkiller.id), "medicine_text": "Panadol 500mg", "quantity_prescribed": 20},
            ],
        )
        self.items = list(self.prescription.items.all())

    def _details(self, name="Walk-in Pharmacy"):
        return {"pharmacy_name": name, "pharmacist_name": "Pharmacist", "method": "QR"}

    def test_pharmacy_without_an_account_can_dispense(self):
        dispense = dispense_prescription(
            prescription=self.prescription,
            lines=[{"prescription_item": str(self.items[0].id), "quantity": 14}],
            pharmacy_details=self._details("Unregistered Corner Pharmacy"),
            pharmacy=None,
        )

        self.assertIsNone(dispense.pharmacy_id)
        self.assertEqual(dispense.pharmacy_name, "Unregistered Corner Pharmacy")

    def test_partial_dispense_leaves_the_rest_claimable_elsewhere(self):
        dispense_prescription(
            prescription=self.prescription,
            lines=[{"prescription_item": str(self.items[0].id), "quantity": 14}],
            pharmacy_details=self._details("First Pharmacy"),
        )
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, Prescription.Status.PARTIALLY_DISPENSED)

        dispense_prescription(
            prescription=self.prescription,
            lines=[{"prescription_item": str(self.items[1].id), "quantity": 20}],
            pharmacy_details=self._details("Second Pharmacy"),
        )
        self.prescription.refresh_from_db()

        self.assertEqual(self.prescription.status, Prescription.Status.FULLY_DISPENSED)
        self.assertEqual(self.prescription.dispenses.count(), 2)

    def test_prescribed_quantity_is_a_hard_ceiling(self):
        with self.assertRaises(DispenseError) as context:
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(self.items[0].id), "quantity": 15}],
                pharmacy_details=self._details(),
            )

        self.assertIn("only 14", str(context.exception))

    def test_the_same_units_cannot_be_dispensed_twice(self):
        dispense_prescription(
            prescription=self.prescription,
            lines=[{"prescription_item": str(self.items[0].id), "quantity": 8}],
            pharmacy_details=self._details("First Pharmacy"),
        )

        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(self.items[0].id), "quantity": 7}],
                pharmacy_details=self._details("Second Pharmacy"),
            )

        self.items[0].refresh_from_db()
        self.assertEqual(self.items[0].quantity_dispensed, 8)
        self.assertEqual(self.items[0].quantity_remaining, 6)

    def test_expired_prescription_cannot_be_dispensed(self):
        self.prescription.valid_until = timezone.now() - timedelta(days=1)
        self.prescription.save()

        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(self.items[0].id), "quantity": 1}],
                pharmacy_details=self._details(),
            )

    def test_controlled_item_must_be_dispensed_in_full_by_one_pharmacy(self):
        self.antibiotic.drug_schedule = DrugSchedule.CONTROLLED
        self.antibiotic.save(update_fields=["drug_schedule"])

        with self.assertRaises(DispenseError) as context:
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(self.items[0].id), "quantity": 7}],
                pharmacy_details=self._details("First Pharmacy"),
            )
        self.assertIn("controlled substance", str(context.exception))

        # Taking the full remaining quantity in one pharmacy is fine.
        dispense_prescription(
            prescription=self.prescription,
            lines=[{"prescription_item": str(self.items[0].id), "quantity": 14}],
            pharmacy_details=self._details("First Pharmacy"),
        )
        self.items[0].refresh_from_db()
        self.assertEqual(self.items[0].quantity_remaining, 0)

    def test_deactivated_doctor_licence_blocks_dispensing(self):
        self.doctor.is_active = False
        self.doctor.save(update_fields=["is_active"])

        with self.assertRaises(DispenseError) as context:
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(self.items[0].id), "quantity": 1}],
                pharmacy_details=self._details(),
            )
        self.assertIn("no longer active", str(context.exception))

    def test_items_from_another_prescription_are_refused(self):
        other, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Someone Else"},
            items=[{"medicine": str(self.painkiller.id), "quantity_prescribed": 5}],
        )
        foreign_item = other.items.first()

        with self.assertRaises(DispenseError):
            dispense_prescription(
                prescription=self.prescription,
                lines=[{"prescription_item": str(foreign_item.id), "quantity": 1}],
                pharmacy_details=self._details(),
            )


class PublicEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.doctor = make_doctor()
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price="2.25")
        self.prescription, self.secret, self.pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad", "patient_phone": "+961-3-201-455", "patient_email": "georges@example.test"},
            items=[{"medicine": str(self.medicine.id), "medicine_text": "Panadol 500mg", "quantity_prescribed": 20}],
        )

    def test_lookup_then_dispense_without_any_account(self):
        lookup = self.client.post("/api/public/rx/lookup/", {"code": self.prescription.code, "key": self.secret}, format="json")
        self.assertEqual(lookup.status_code, 200, lookup.data)
        ticket = lookup.data["dispense_ticket"]

        result = self.client.post(
            "/api/public/rx/dispense/",
            {
                "ticket": ticket,
                "pharmacy_name": "Corner Pharmacy",
                "pharmacist_name": "M. Saab",
                "items": [{"prescription_item": lookup.data["items"][0]["id"], "quantity": 20}],
            },
            format="json",
        )

        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["prescription_status"], Prescription.Status.FULLY_DISPENSED)

    def test_public_payload_withholds_patient_contact_details(self):
        lookup = self.client.post("/api/public/rx/lookup/", {"code": self.prescription.code, "pin": self.pin}, format="json")

        body = str(lookup.data)
        self.assertIn("Georges Haddad", body)  # the pharmacist needs the name
        self.assertNotIn("georges@example.test", body)
        self.assertNotIn("+961-3-201-455", body)

    def test_dispense_requires_a_ticket_from_a_real_lookup(self):
        result = self.client.post(
            "/api/public/rx/dispense/",
            {"ticket": "forged-ticket", "pharmacy_name": "X", "pharmacist_name": "Y", "items": [{"prescription_item": str(self.prescription.items.first().id), "quantity": 1}]},
            format="json",
        )

        self.assertEqual(result.status_code, 401)

    def test_lookup_without_key_or_pin_is_a_validation_error(self):
        result = self.client.post("/api/public/rx/lookup/", {"code": self.prescription.code}, format="json")

        self.assertEqual(result.status_code, 400)


class MyPrescriptionsViewTests(TestCase):
    """
    A Prescription has no owning user account (see its security-model docstring) - the
    'mine' endpoint links a signed-in shopper to their prescriptions by matching the
    account's own email against what the doctor recorded as the patient's email.
    """

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.client = APIClient()
        self.doctor = make_doctor()
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price="2.25")
        self.shopper = get_user_model().objects.create_user(email="georges@example.test", password="Password123!", role=UserRole.CUSTOMER)
        self.prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Georges Haddad", "patient_email": "georges@example.test"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 20}],
        )
        issue_prescription(
            doctor=self.doctor,
            patient={"patient_name": "Someone Else", "patient_email": "someone-else@example.test"},
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 5}],
        )

    def test_returns_only_prescriptions_matching_the_signed_in_email(self):
        self.client.force_authenticate(user=self.shopper)

        result = self.client.get("/api/shop/prescriptions/mine/")

        self.assertEqual(result.status_code, 200)
        self.assertEqual([entry["code"] for entry in result.data], [self.prescription.code])

    def test_email_match_is_case_insensitive(self):
        self.shopper.email = "Georges@Example.test"
        self.shopper.save(update_fields=["email"])
        self.client.force_authenticate(user=self.shopper)

        result = self.client.get("/api/shop/prescriptions/mine/")

        self.assertEqual([entry["code"] for entry in result.data], [self.prescription.code])

    def test_requires_authentication(self):
        result = self.client.get("/api/shop/prescriptions/mine/")

        self.assertEqual(result.status_code, 401)
