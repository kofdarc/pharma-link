from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from apps.accounts.models import NotificationPreferences
from apps.eprescriptions.services.issue import issue_prescription
from apps.eprescriptions.services.reminders import send_prescription_expiry_reminders
from apps.eprescriptions.services.renewal import request_renewal, respond_to_renewal
from apps.eprescriptions.tests.test_prescription_flow import make_doctor
from apps.messaging.models import WhatsAppNotification
from apps.messaging.notifications import deliver_notification
from apps.messaging.services import ingest_delivery_status
from apps.orders.models import RecurringOrder
from apps.orders.services.lifecycle import accept_fulfillment
from apps.orders.services.placement import place_order
from apps.orders.services.schedule import send_due_refill_reminders
from apps.payments.models import Payment
from apps.payments.providers.base import ChargeResult
from apps.payments.providers.mock_gateway import MockGatewayProvider
from apps.payments.services import charge_payment

from .test_messaging import MessagingTestCase


class OrderAndPharmacyNotificationTests(MessagingTestCase):
    def test_order_placement_queues_customer_and_pharmacy_templates(self):
        kinds = set(WhatsAppNotification.objects.values_list("kind", flat=True))

        self.assertEqual(
            kinds,
            {WhatsAppNotification.Kind.ORDER_UPDATE, WhatsAppNotification.Kind.PHARMACY_ALERT},
        )

    def test_acceptance_is_deduplicated_and_respects_order_preference(self):
        accept_fulfillment(fulfillment=self.fulfillment, user=self.owner)
        accept_fulfillment_notification = WhatsAppNotification.objects.filter(
            kind=WhatsAppNotification.Kind.ORDER_UPDATE,
            deduplication_key__endswith=":accepted",
        )
        self.assertEqual(accept_fulfillment_notification.count(), 1)

        preferences = NotificationPreferences.for_user(self.shopper)
        preferences.order_updates = False
        preferences.save(update_fields=["order_updates", "updated_at"])
        place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 1}], address=self.address)

        self.assertEqual(
            WhatsAppNotification.objects.filter(kind=WhatsAppNotification.Kind.ORDER_UPDATE).count(),
            2,
            "the second order must not add a customer update after opt-out",
        )

    def test_delivery_status_updates_the_template_record(self):
        notification = WhatsAppNotification.objects.filter(kind=WhatsAppNotification.Kind.ORDER_UPDATE).first()
        delivered = deliver_notification(notification.id)

        self.assertEqual(delivered.status, WhatsAppNotification.Status.SENT)
        self.assertTrue(ingest_delivery_status(provider_message_id=delivered.provider_message_id, provider_status="read"))
        delivered.refresh_from_db()
        self.assertEqual(delivered.status, WhatsAppNotification.Status.READ)


class RefillReminderTests(MessagingTestCase):
    def test_due_reminder_is_sent_once_and_honors_opt_out(self):
        recurring = RecurringOrder.objects.create(
            customer=self.shopper,
            address=self.address,
            label="Monthly refill",
            items=[{"medicine": str(self.medicine.id), "quantity": 1}],
            next_run_at=timezone.now() + timedelta(days=2),
        )

        self.assertEqual(send_due_refill_reminders(), 1)
        self.assertEqual(send_due_refill_reminders(), 0)
        self.assertEqual(
            WhatsAppNotification.objects.filter(kind=WhatsAppNotification.Kind.REFILL_REMINDER).count(),
            1,
        )

        preferences = NotificationPreferences.for_user(self.shopper)
        preferences.refill_reminders = False
        preferences.save(update_fields=["refill_reminders", "updated_at"])
        recurring.next_run_at += timedelta(days=30)
        recurring.save(update_fields=["next_run_at", "updated_at"])
        self.assertEqual(send_due_refill_reminders(now=recurring.next_run_at - timedelta(days=2)), 0)


class PrescriptionNotificationTests(MessagingTestCase):
    def setUp(self):
        super().setUp()
        self.doctor = make_doctor(email="doctor-notifications@test.test", license_number="LB-MD-NOTIFY")
        self.shopper.phone = self.address.phone
        self.shopper.save(update_fields=["phone", "updated_at"])

    def issue(self, *, target_pharmacy=None):
        prescription, _secret, _pin = issue_prescription(
            doctor=self.doctor,
            patient={
                "patient_name": "Shopper",
                "patient_email": self.shopper.email,
                "patient_phone": self.address.phone,
            },
            items=[{"medicine": str(self.medicine.id), "quantity_prescribed": 2}],
            target_pharmacy=target_pharmacy,
        )
        return prescription

    def test_targeted_prescription_alerts_the_pharmacy(self):
        prescription = self.issue(target_pharmacy=self.pharmacy)

        notification = WhatsAppNotification.objects.get(
            deduplication_key=f"pharmacy:{self.pharmacy.id}:prescription:{prescription.id}:new"
        )
        self.assertEqual(notification.kind, WhatsAppNotification.Kind.PHARMACY_ALERT)

    def test_expiry_reminders_send_at_seven_days_and_one_day_without_medication_details(self):
        prescription = self.issue()
        prescription.valid_until = timezone.now() + timedelta(days=6)
        prescription.save(update_fields=["valid_until", "updated_at"])

        self.assertEqual(send_prescription_expiry_reminders(), 1)
        self.assertEqual(send_prescription_expiry_reminders(), 0)
        prescription.valid_until = timezone.now() + timedelta(hours=12)
        prescription.save(update_fields=["valid_until", "updated_at"])
        self.assertEqual(send_prescription_expiry_reminders(), 1)

        notifications = WhatsAppNotification.objects.filter(kind=WhatsAppNotification.Kind.PRESCRIPTION_EXPIRY)
        self.assertEqual(notifications.count(), 2)
        for notification in notifications:
            self.assertNotIn(self.medicine.brand_name, notification.fallback_body)
            self.assertNotIn(self.medicine.brand_name, notification.body_parameters)

    def test_renewal_decision_notifies_the_patient(self):
        prescription = self.issue(target_pharmacy=self.pharmacy)
        renewal = request_renewal(
            prescription=prescription,
            pharmacy=self.pharmacy,
            requested_by_user=self.owner,
        )

        respond_to_renewal(renewal_request=renewal, approve=False)

        notification = WhatsAppNotification.objects.get(kind=WhatsAppNotification.Kind.RENEWAL_DECISION)
        self.assertEqual(notification.recipient_phone, "+96171000000")


class PaymentFailureNotificationTests(MessagingTestCase):
    def test_failed_retry_sends_the_payment_template(self):
        payment = self.order.payment
        payment.provider = Payment.Provider.MOCK_GATEWAY
        payment.save(update_fields=["provider", "updated_at"])

        with patch.object(
            MockGatewayProvider,
            "charge",
            return_value=ChargeResult(status=Payment.Status.FAILED, failure_reason="Card declined"),
        ):
            charge_payment(payment=payment, user=self.shopper)

        notification = WhatsAppNotification.objects.get(kind=WhatsAppNotification.Kind.PAYMENT_FAILURE)
        self.assertEqual(notification.status, WhatsAppNotification.Status.SENT)
        self.assertNotIn("Card declined", notification.fallback_body)
