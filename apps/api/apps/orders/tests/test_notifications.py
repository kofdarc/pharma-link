"""
Order-lifecycle notification emails (Phase 3 of the operational-automation work).

These don't assert on wording, just on the mechanics that matter: an email goes out at the
right point, addressed to the shopper, and a failure to send one must never break the
underlying transaction (see test_a_notification_failure_does_not_break_order_placement).
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.models import Order
from apps.orders.services.lifecycle import accept_fulfillment, hand_over
from apps.orders.services.placement import place_order
from apps.orders.services.schedule import run_due_recurring_orders
from apps.payments.models import Payment
from apps.payments.providers.base import ChargeResult
from apps.payments.providers.mock_gateway import MockGatewayProvider
from apps.pharmacies.models import Pharmacy

HAMRA = (33.8975, 35.4790)
SHOPPER_HOME = (33.8991, 35.4772)


class NotificationTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )

    def place(self, payment_method=Payment.Provider.CASH_ON_DELIVERY):
        return place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            payment_method=payment_method,
        )


class OrderPlacedNotificationTests(NotificationTestCase):
    def test_placing_an_order_emails_the_shopper(self):
        order = self.place()

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.shopper.email, mail.outbox[0].to)
        self.assertIn(order.reference, mail.outbox[0].subject)

    def test_a_notification_failure_does_not_break_order_placement(self):
        with patch("apps.orders.services.placement.send_email", side_effect=RuntimeError("SMTP is down")):
            order = self.place()

        self.assertTrue(Order.objects.filter(id=order.id).exists(), "the order must still be created even if the email fails")


class FulfillmentAcceptedNotificationTests(NotificationTestCase):
    def test_accepting_a_fulfillment_emails_the_shopper(self):
        order = self.place()
        mail.outbox.clear()
        fulfillment = order.fulfillments.get()

        accept_fulfillment(fulfillment=fulfillment, user=self.owner)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.shopper.email, mail.outbox[0].to)


class OrderDeliveredNotificationTests(NotificationTestCase):
    def test_collection_in_store_emails_the_shopper_once(self):
        order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            fulfillment_type=Order.FulfillmentType.PICKUP,
        )
        fulfillment = order.fulfillments.get()
        accept_fulfillment(fulfillment=fulfillment, user=self.owner)
        mail.outbox.clear()

        hand_over(fulfillment=fulfillment, user=self.owner, handover_code=fulfillment.handover_code, collected_in_store=True)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COLLECTED)
        self.assertEqual(len(mail.outbox), 1, "the delivered/collected email must only fire once, at the rollup transition")
        self.assertIn(self.shopper.email, mail.outbox[0].to)


class PaymentFailedNotificationTests(NotificationTestCase):
    def test_a_declined_charge_emails_the_shopper(self):
        with patch.object(MockGatewayProvider, "charge", return_value=ChargeResult(status=Payment.Status.FAILED, failure_reason="Card declined")):
            with self.assertRaises(Exception):
                self.place(payment_method=Payment.Provider.MOCK_GATEWAY)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.shopper.email, mail.outbox[0].to)
        self.assertIn("failed", mail.outbox[0].subject.lower())


class RecurringOrderFailedNotificationTests(NotificationTestCase):
    def test_a_recurring_cycle_that_cannot_be_sourced_emails_the_shopper(self):
        from apps.orders.models import RecurringOrder

        # No stock at all for this medicine, anywhere: sourcing always fails.
        broke_medicine = Medicine.objects.create(brand_name="Nexium", strength="40mg", form="Tablet", regulated_price=Decimal("18.60"))
        recurring = RecurringOrder.objects.create(
            customer=self.shopper,
            address=self.address,
            label="Monthly refill",
            items=[{"medicine": str(broke_medicine.id), "quantity": 1}],
            interval_days=30,
            next_run_at=timezone.now(),
        )

        result = run_due_recurring_orders()

        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.shopper.email, mail.outbox[0].to)
        recurring.refresh_from_db()
        self.assertTrue(recurring.last_error)
