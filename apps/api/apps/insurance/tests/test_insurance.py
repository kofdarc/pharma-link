"""
What must hold:
  - compute_copay applies the plan's coverage percentage and never lets the patient pay
    less than the copay floor, without ever pushing the insurer's share negative
  - placing an insured shop order creates one claim per fulfillment and charges the
    shopper's Payment only the total copay, not the full order total
  - an insured counter sale on a client's account charges the ClientLedgerEntry only the
    copay, not the full invoice
  - a claim can only move SUBMITTED -> APPROVED/REJECTED -> PAID, never backwards or twice
  - a pharmacy can only see its own claims; a shopper can only see their own policies
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.customers.models import Client, ClientLedgerEntry
from apps.insurance.models import InsuranceClaim, InsurancePlan, InsuranceProvider, PatientInsurancePolicy
from apps.insurance.services import InsuranceError, compute_copay, submit_claim_for_sale, update_claim_status
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.services.lifecycle import cancel_order, reject_fulfillment
from apps.orders.services.placement import place_order
from apps.pharmacies.models import Pharmacy
from apps.sales.models import Sale
from apps.sales.services.create_sale import create_sale

HAMRA = (Decimal("33.8975"), Decimal("35.4790"))


class ComputeCopayTests(TestCase):
    def setUp(self):
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        self.plan_80_pct = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"), copay_minimum=Decimal("0"))
        self.plan_with_floor = InsurancePlan.objects.create(
            provider=provider, name="With floor", coverage_percentage=Decimal("90"), copay_minimum=Decimal("5.00")
        )
        self.plan_full = InsurancePlan.objects.create(provider=provider, name="Full", coverage_percentage=Decimal("100"), copay_minimum=Decimal("0"))
        self.plan_none = InsurancePlan.objects.create(provider=provider, name="None", coverage_percentage=Decimal("0"), copay_minimum=Decimal("0"))

    def test_percentage_coverage_without_floor(self):
        copay, covered = compute_copay(self.plan_80_pct, Decimal("100.00"))
        self.assertEqual(copay, Decimal("20.00"))
        self.assertEqual(covered, Decimal("80.00"))

    def test_floor_wins_when_percentage_copay_is_smaller(self):
        # 90% coverage on 10.00 leaves a 1.00 computed copay, below the 5.00 floor.
        copay, covered = compute_copay(self.plan_with_floor, Decimal("10.00"))
        self.assertEqual(copay, Decimal("5.00"))
        self.assertEqual(covered, Decimal("5.00"))

    def test_floor_never_exceeds_the_billed_amount(self):
        copay, covered = compute_copay(self.plan_with_floor, Decimal("3.00"))
        self.assertEqual(copay, Decimal("3.00"))
        self.assertEqual(covered, Decimal("0.00"))

    def test_full_coverage_zeroes_the_copay(self):
        copay, covered = compute_copay(self.plan_full, Decimal("42.00"))
        self.assertEqual(copay, Decimal("0.00"))
        self.assertEqual(covered, Decimal("42.00"))

    def test_no_coverage_patient_pays_everything(self):
        copay, covered = compute_copay(self.plan_none, Decimal("42.00"))
        self.assertEqual(copay, Decimal("42.00"))
        self.assertEqual(covered, Decimal("0.00"))


class ClaimStatusTransitionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"))
        client = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-000", created_by=self.owner)
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, client=client, member_id="M-1", holder_name="Jane Doe")
        sale = Sale.objects.create(invoice_number="INV-1", pharmacy=self.pharmacy, staff_user=self.owner, total=Decimal("100.00"))
        self.claim = submit_claim_for_sale(sale=sale, policy=self.policy, user=self.owner)

    def test_submitted_can_move_to_approved(self):
        claim = update_claim_status(claim=self.claim, status=InsuranceClaim.Status.APPROVED, approval_code="AC-1", user=self.owner)
        self.assertEqual(claim.status, InsuranceClaim.Status.APPROVED)
        self.assertEqual(claim.approval_code, "AC-1")
        self.assertIsNotNone(claim.approved_at)

    def test_submitted_can_move_to_rejected(self):
        claim = update_claim_status(claim=self.claim, status=InsuranceClaim.Status.REJECTED, rejection_reason="Expired card", user=self.owner)
        self.assertEqual(claim.status, InsuranceClaim.Status.REJECTED)

    def test_cannot_skip_straight_to_paid(self):
        with self.assertRaises(InsuranceError):
            update_claim_status(claim=self.claim, status=InsuranceClaim.Status.PAID, user=self.owner)

    def test_rejected_is_terminal(self):
        update_claim_status(claim=self.claim, status=InsuranceClaim.Status.REJECTED, user=self.owner)
        self.claim.refresh_from_db()
        with self.assertRaises(InsuranceError):
            update_claim_status(claim=self.claim, status=InsuranceClaim.Status.APPROVED, user=self.owner)

    def test_approved_then_paid_then_terminal(self):
        update_claim_status(claim=self.claim, status=InsuranceClaim.Status.APPROVED, user=self.owner)
        self.claim.refresh_from_db()
        claim = update_claim_status(claim=self.claim, status=InsuranceClaim.Status.PAID, user=self.owner)
        self.assertEqual(claim.status, InsuranceClaim.Status.PAID)
        self.assertIsNotNone(claim.paid_at)
        claim.refresh_from_db()
        with self.assertRaises(InsuranceError):
            update_claim_status(claim=claim, status=InsuranceClaim.Status.APPROVED, user=self.owner)


class InsuredOrderTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=HAMRA[0], longitude=HAMRA[1],
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("10.00"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("5.00"),
                "selling_price": Decimal("10.00"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=HAMRA[0], longitude=HAMRA[1], is_default=True,
        )
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"), copay_minimum=Decimal("0"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, customer_user=self.shopper, member_id="M-1", holder_name="Shopper")

    def test_insured_order_creates_a_claim_and_reduces_payment_to_the_copay(self):
        order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            insurance_policy=self.policy,
        )
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)
        claim = InsuranceClaim.objects.get(order_fulfillment=fulfillment)
        self.assertEqual(claim.billed_amount, Decimal("20.00"))
        self.assertEqual(claim.patient_copay, Decimal("4.00"))
        self.assertEqual(claim.covered_amount, Decimal("16.00"))
        # Delivery fee is never insurance-eligible, so it's added on top of the copay.
        self.assertEqual(order.payment.amount, claim.patient_copay + order.delivery_fee)

    def test_uninsured_order_still_charges_the_full_total(self):
        order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
        )
        self.assertEqual(order.payment.amount, order.total)
        self.assertFalse(InsuranceClaim.objects.filter(order_fulfillment__order=order).exists())


class InsuredCounterSaleTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("10.00"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("5.00"),
                "selling_price": Decimal("10.00"),
            },
        )
        self.client_record = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-001", created_by=self.owner)
        provider = InsuranceProvider.objects.create(name="LibanCard")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("50"), copay_minimum=Decimal("0"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, client=self.client_record, member_id="M-2", holder_name="Jane Doe")

    def test_insured_on_account_sale_charges_the_ledger_only_the_copay(self):
        sale = create_sale(
            user=self.owner,
            pharmacy=self.pharmacy,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            payment_method=Sale.PaymentMethod.ON_ACCOUNT,
            client=self.client_record,
            insurance_policy=self.policy,
        )
        self.assertEqual(sale.total, Decimal("20.00"))
        claim = InsuranceClaim.objects.get(sale=sale)
        self.assertEqual(claim.patient_copay, Decimal("10.00"))
        ledger_entry = ClientLedgerEntry.objects.get(sale=sale)
        self.assertEqual(ledger_entry.amount, Decimal("10.00"))


class InsuranceApiScopingTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.other_pharmacy = Pharmacy.objects.create(name="Achrafieh Health", area="Achrafieh", city="Beirut", phone="+961-1-000-001")
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.other_owner = User.objects.create_user(email="owner@ach.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.other_pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.other_shopper = User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER)

        provider = InsuranceProvider.objects.create(name="GlobeMed")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, customer_user=self.shopper, member_id="M-1", holder_name="Shopper")

        client = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-002", created_by=self.owner)
        client_policy = PatientInsurancePolicy.objects.create(plan=plan, client=client, member_id="M-3", holder_name="Jane Doe")
        sale = Sale.objects.create(invoice_number="INV-2", pharmacy=self.pharmacy, staff_user=self.owner, total=Decimal("50.00"))
        self.claim = submit_claim_for_sale(sale=sale, policy=client_policy, user=self.owner)

    def test_shopper_only_sees_own_policies(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.get("/api/shop/insurance-policies/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.policy.id)])

        self.client.force_authenticate(self.other_shopper)
        response = self.client.get("/api/shop/insurance-policies/")
        self.assertEqual(response.data["results"], [])

    def test_pharmacy_only_sees_its_own_claims(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/pharmacy/insurance-claims/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.claim.id)])

        self.client.force_authenticate(self.other_owner)
        response = self.client.get("/api/pharmacy/insurance-claims/")
        self.assertEqual(response.data["results"], [])

    def test_pharmacy_can_approve_its_own_claim_via_the_status_action(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"/api/pharmacy/insurance-claims/{self.claim.id}/status/", {"status": "APPROVED", "approval_code": "AC-9"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "APPROVED")

    def test_pharmacy_cannot_act_on_another_pharmacys_claim(self):
        self.client.force_authenticate(self.other_owner)
        response = self.client.post(f"/api/pharmacy/insurance-claims/{self.claim.id}/status/", {"status": "APPROVED"})
        self.assertEqual(response.status_code, 404)


class ClaimCancellationOnRejectionTests(TestCase):
    """Rejecting/cancelling a never-dispensed fulfillment must not leave a live claim behind."""

    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=HAMRA[0], longitude=HAMRA[1],
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("10.00"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("5.00"),
                "selling_price": Decimal("10.00"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=HAMRA[0], longitude=HAMRA[1], is_default=True,
        )
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, customer_user=self.shopper, member_id="M-1", holder_name="Shopper")

    def place(self):
        return place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            insurance_policy=self.policy,
        )

    def test_rejecting_a_fulfillment_cancels_its_submitted_claim(self):
        order = self.place()
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)
        claim = InsuranceClaim.objects.get(order_fulfillment=fulfillment)
        self.assertEqual(claim.status, InsuranceClaim.Status.SUBMITTED)

        reject_fulfillment(fulfillment=fulfillment, user=self.owner, reason="Out of stock after all")

        claim.refresh_from_db()
        self.assertEqual(claim.status, InsuranceClaim.Status.CANCELLED)

    def test_cancelling_an_order_cancels_its_submitted_claims(self):
        order = self.place()
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)
        claim = InsuranceClaim.objects.get(order_fulfillment=fulfillment)

        cancel_order(order=order, user=self.shopper, reason="Changed my mind")

        claim.refresh_from_db()
        self.assertEqual(claim.status, InsuranceClaim.Status.CANCELLED)

    def test_rejecting_an_already_approved_claim_is_left_alone(self):
        order = self.place()
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)
        claim = InsuranceClaim.objects.get(order_fulfillment=fulfillment)
        update_claim_status(claim=claim, status=InsuranceClaim.Status.APPROVED, user=self.owner)

        reject_fulfillment(fulfillment=fulfillment, user=self.owner, reason="Out of stock after all")

        claim.refresh_from_db()
        self.assertEqual(claim.status, InsuranceClaim.Status.APPROVED)


class ExpiredPolicyRejectedTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=HAMRA[0], longitude=HAMRA[1],
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        self.plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"))

    def test_is_expired_true_for_a_past_valid_until(self):
        client = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-003", created_by=self.owner)
        policy = PatientInsurancePolicy.objects.create(
            plan=self.plan, client=client, member_id="M-4", holder_name="Jane Doe",
            valid_until=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.assertTrue(policy.is_expired)

    def test_is_expired_false_without_a_valid_until(self):
        client = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-004", created_by=self.owner)
        policy = PatientInsurancePolicy.objects.create(plan=self.plan, client=client, member_id="M-5", holder_name="Jane Doe")
        self.assertFalse(policy.is_expired)


class InsuredOrderHttpApiTests(APITestCase):
    """Exercises the real /api/shop/orders/ endpoint, not just place_order() directly."""

    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=HAMRA[0], longitude=HAMRA[1],
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(
            email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=True
        )
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("10.00"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("5.00"),
                "selling_price": Decimal("10.00"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=HAMRA[0], longitude=HAMRA[1], is_default=True,
        )
        provider = InsuranceProvider.objects.create(name="GlobeMed")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("80"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, customer_user=self.shopper, member_id="M-1", holder_name="Shopper")
        self.expired_policy = PatientInsurancePolicy.objects.create(
            plan=plan, customer_user=self.shopper, member_id="M-2", holder_name="Shopper",
            valid_until=timezone.localdate() - timezone.timedelta(days=1),
        )
        self.other_shopper_policy = PatientInsurancePolicy.objects.create(
            plan=plan,
            customer_user=User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER),
            member_id="M-3", holder_name="Someone else",
        )

    def _place(self, **overrides):
        self.client.force_authenticate(self.shopper)
        payload = {
            "items": [{"medicine": str(self.medicine.id), "quantity": 2}],
            "address": str(self.address.id),
            "fulfillment_type": "DELIVERY",
            "payment_method": "COD",
        }
        payload.update(overrides)
        return self.client.post("/api/shop/orders/", payload, format="json")

    def test_placing_an_order_with_insurance_charges_only_the_copay(self):
        response = self._place(insurance_policy=str(self.policy.id))
        self.assertEqual(response.status_code, 201, response.data)
        # 2 x $10.00 = $20.00 subtotal, 80% coverage -> $4.00 copay, plus the $3.00 delivery
        # fee (never insurance-eligible) = $7.00 actually charged.
        self.assertEqual(response.data["payment"]["amount"], "7.00")

    def test_placing_an_order_with_an_expired_policy_is_rejected(self):
        response = self._place(insurance_policy=str(self.expired_policy.id))
        self.assertEqual(response.status_code, 400)

    def test_placing_an_order_with_another_shoppers_policy_is_rejected(self):
        response = self._place(insurance_policy=str(self.other_shopper_policy.id))
        self.assertEqual(response.status_code, 400)


class InsuredSaleHttpApiTests(APITestCase):
    """Exercises the real /api/pharmacy/sales/ endpoint, not just create_sale() directly."""

    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("10.00"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("5.00"),
                "selling_price": Decimal("10.00"),
            },
        )
        self.client_record = Client.objects.create(pharmacy=self.pharmacy, full_name="Jane Doe", phone="+961-71-000-005", created_by=self.owner)
        provider = InsuranceProvider.objects.create(name="LibanCard")
        plan = InsurancePlan.objects.create(provider=provider, name="Standard", coverage_percentage=Decimal("50"))
        self.policy = PatientInsurancePolicy.objects.create(plan=plan, client=self.client_record, member_id="M-2", holder_name="Jane Doe")
        self.expired_policy = PatientInsurancePolicy.objects.create(
            plan=plan, client=self.client_record, member_id="M-6", holder_name="Jane Doe",
            valid_until=timezone.localdate() - timezone.timedelta(days=1),
        )

    def _sell(self, **overrides):
        self.client.force_authenticate(self.owner)
        payload = {
            "items": [{"medicine": str(self.medicine.id), "quantity": 2}],
            "client": str(self.client_record.id),
            "payment_method": "ON_ACCOUNT",
        }
        payload.update(overrides)
        return self.client.post("/api/pharmacy/sales/", payload, format="json")

    def test_selling_with_insurance_charges_the_ledger_only_the_copay(self):
        response = self._sell(insurance_policy=str(self.policy.id))
        self.assertEqual(response.status_code, 201, response.data)
        sale_id = response.data["id"]
        entry = ClientLedgerEntry.objects.get(sale_id=sale_id)
        self.assertEqual(entry.amount, Decimal("10.00"))

    def test_selling_with_an_expired_policy_is_rejected(self):
        response = self._sell(insurance_policy=str(self.expired_policy.id))
        self.assertEqual(response.status_code, 400)

    def test_selling_with_a_policy_from_another_client_is_rejected(self):
        other_client = Client.objects.create(pharmacy=self.pharmacy, full_name="Other Client", phone="+961-71-000-006", created_by=self.owner)
        other_policy = PatientInsurancePolicy.objects.create(
            plan=self.policy.plan, client=other_client, member_id="M-7", holder_name="Other Client"
        )
        response = self._sell(insurance_policy=str(other_policy.id))
        self.assertEqual(response.status_code, 400)
