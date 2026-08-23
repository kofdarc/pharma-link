"""
What must hold:
  - sending a message lazily creates the Conversation and delivers via the configured
    WhatsApp provider (console in tests)
  - a shopper can only see/message their own order's conversations, never another shopper's
  - a pharmacy can only see/message its own fulfillments, never another pharmacy's
  - inbound webhook messages are matched to the right conversation by phone number pair
  - malformed phone numbers are rejected rather than silently mis-sent
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.messaging.models import Conversation, Message
from apps.messaging.phone import InvalidPhoneNumber, normalize_to_e164
from apps.messaging.services import get_or_create_conversation, ingest_inbound, send_message
from apps.orders.services.placement import place_order
from apps.pharmacies.models import Pharmacy

HAMRA = (33.8975, 35.4790)
SHOPPER_HOME = (33.8991, 35.4772)


class MessagingTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000", whatsapp="+96170111111",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.other_pharmacy = Pharmacy.objects.create(
            name="Other Pharmacy", area="Hamra", city="Beirut", address="Other street", phone="+961-1-000-001", whatsapp="+96170222222",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.other_owner = User.objects.create_user(email="owner@other.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.other_pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.other_shopper = User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER)
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
            label="Home", contact_name="Shopper", phone="+96171000000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )
        self.order = place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 2}], address=self.address)
        self.fulfillment = self.order.fulfillments.get()


class SendMessageTests(MessagingTestCase):
    def test_sending_a_message_lazily_creates_the_conversation_and_sends_it(self):
        self.assertFalse(Conversation.objects.filter(order_fulfillment=self.fulfillment).exists())

        conversation = get_or_create_conversation(order_fulfillment=self.fulfillment)
        message = send_message(conversation=conversation, sender=self.owner, body="Your order is ready for pickup.")

        self.assertEqual(message.status, Message.Status.SENT)
        self.assertTrue(message.provider_message_id.startswith("console-"))
        conversation.refresh_from_db()
        self.assertIsNotNone(conversation.last_message_at)

    def test_getting_the_conversation_twice_does_not_duplicate_it(self):
        first = get_or_create_conversation(order_fulfillment=self.fulfillment)
        second = get_or_create_conversation(order_fulfillment=self.fulfillment)
        self.assertEqual(first.id, second.id)


class InboundMatchingTests(MessagingTestCase):
    def test_inbound_message_matches_the_right_pharmacy_when_the_shopper_has_two_threads(self):
        other_order = place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 1}], address=self.address)
        # Force a second fulfillment at a different pharmacy so the shopper has two open threads.
        create_inventory_batch(
            user=self.other_owner,
            pharmacy=self.other_pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 5,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )
        conversation_a = get_or_create_conversation(order_fulfillment=self.fulfillment)
        conversation_b, _ = Conversation.objects.get_or_create(
            order_fulfillment=other_order.fulfillments.get(),
            defaults={"customer": self.shopper, "pharmacy": self.other_pharmacy, "customer_phone": self.address.phone},
        )

        message = ingest_inbound(from_phone=self.address.phone, to_phone=self.other_pharmacy.whatsapp, body="When will it be ready?")

        self.assertIsNotNone(message)
        self.assertEqual(message.conversation_id, conversation_b.id)
        self.assertNotEqual(message.conversation_id, conversation_a.id)

    def test_inbound_message_with_no_matching_conversation_is_dropped(self):
        message = ingest_inbound(from_phone="+96171999999", to_phone=self.pharmacy.whatsapp, body="Hello?")
        self.assertIsNone(message)


class PhoneNormalizationTests(TestCase):
    def test_a_valid_lebanese_number_normalizes_to_e164(self):
        self.assertEqual(normalize_to_e164("71 000 000", default_region="LB"), "+96171000000")

    def test_garbage_input_raises_instead_of_silently_failing_later(self):
        with self.assertRaises(InvalidPhoneNumber):
            normalize_to_e164("not-a-phone-number")


class ConversationApiScopingTests(APITestCase):
    def setUp(self):
        MessagingTestCase.setUp(self)

    def test_shopper_can_message_their_own_fulfillment(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post(f"/api/shop/order-fulfillments/{self.fulfillment.id}/messages/", {"body": "Hi, when will this be ready?"})
        self.assertEqual(response.status_code, 201)

    def test_another_shopper_cannot_reach_someone_elses_fulfillment(self):
        self.client.force_authenticate(self.other_shopper)
        response = self.client.get(f"/api/shop/order-fulfillments/{self.fulfillment.id}/messages/")
        self.assertEqual(response.status_code, 404)

    def test_pharmacy_can_message_its_own_fulfillment(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(f"/api/pharmacy/order-fulfillments/{self.fulfillment.id}/messages/", {"body": "It'll be ready in 15 minutes."})
        self.assertEqual(response.status_code, 201)

    def test_another_pharmacy_cannot_reach_a_fulfillment_that_isnt_theirs(self):
        self.client.force_authenticate(self.other_owner)
        response = self.client.get(f"/api/pharmacy/order-fulfillments/{self.fulfillment.id}/messages/")
        self.assertEqual(response.status_code, 404)
