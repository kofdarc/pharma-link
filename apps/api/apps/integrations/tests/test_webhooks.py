"""
Outgoing webhooks: dispatch_webhook_event() must stay a fast, HTTP-free write (it can be
called from inside a request/transaction path), and deliver_pending_webhooks() - the only
place an actual network call happens - must sign correctly, retry on failure up to a cap,
and never let one bad endpoint block another delivery.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import Mock, patch
from urllib.error import URLError

from django.test import TestCase

from apps.accounts.models import UserRole
from apps.integrations.authentication import canonical_string
from apps.integrations.models import WebhookDelivery, WebhookEndpoint
from apps.integrations.services.webhooks import MAX_WEBHOOK_ATTEMPTS, deliver_pending_webhooks, dispatch_webhook_event
from apps.pharmacies.models import Pharmacy


class WebhookTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.owner = User.objects.create_user(email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.endpoint = WebhookEndpoint.objects.create(
            pharmacy=self.pharmacy, url="https://pos.example.test/hook", secret="whsec_test", events=[], is_active=True
        )


class DispatchWebhookEventTests(WebhookTestCase):
    def test_dispatch_creates_a_pending_delivery_with_no_network_call(self):
        with patch("apps.integrations.services.webhooks.urllib.request.urlopen") as urlopen:
            dispatch_webhook_event(pharmacy=self.pharmacy, event_type="order.placed", payload={"order_reference": "MO-1"})

        urlopen.assert_not_called()
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.event, "order.placed")
        self.assertEqual(delivery.payload, {"order_reference": "MO-1"})

    def test_inactive_endpoints_are_skipped(self):
        self.endpoint.is_active = False
        self.endpoint.save(update_fields=["is_active"])

        dispatch_webhook_event(pharmacy=self.pharmacy, event_type="order.placed", payload={})

        self.assertFalse(WebhookDelivery.objects.exists())

    def test_an_endpoint_subscribed_to_specific_events_ignores_the_rest(self):
        self.endpoint.events = ["stock.synced"]
        self.endpoint.save(update_fields=["events"])

        dispatch_webhook_event(pharmacy=self.pharmacy, event_type="order.placed", payload={})

        self.assertFalse(WebhookDelivery.objects.exists())

    def test_another_pharmacy_s_endpoint_never_receives_this_pharmacy_s_event(self):
        other_pharmacy = Pharmacy.objects.create(name="Achrafieh Health", area="Achrafieh", city="Beirut", phone="+961-1-111-111")
        WebhookEndpoint.objects.create(pharmacy=other_pharmacy, url="https://other.example.test/hook", secret="whsec_other", events=[], is_active=True)

        dispatch_webhook_event(pharmacy=self.pharmacy, event_type="order.placed", payload={})

        self.assertEqual(WebhookDelivery.objects.filter(endpoint__pharmacy=other_pharmacy).count(), 0)


class DeliverPendingWebhooksTests(WebhookTestCase):
    def _pending(self, **kwargs):
        defaults = {"endpoint": self.endpoint, "event": "order.placed", "payload": {"order_reference": "MO-1"}, "status": WebhookDelivery.Status.PENDING}
        defaults.update(kwargs)
        return WebhookDelivery.objects.create(**defaults)

    def test_a_successful_post_is_marked_delivered_and_correctly_signed(self):
        delivery = self._pending()
        response = Mock()
        response.getcode.return_value = 200
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)

        with patch("apps.integrations.services.webhooks.urllib.request.urlopen", return_value=response) as urlopen:
            attempted = deliver_pending_webhooks()

        self.assertEqual(attempted, 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DELIVERED)
        self.assertEqual(delivery.status_code, 200)
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNotNone(delivery.delivered_at)

        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, self.endpoint.url)
        body = request.data
        timestamp = request.get_header("X-pharmalink-timestamp")
        nonce = request.get_header("X-pharmalink-nonce")
        signature = request.get_header("X-pharmalink-signature")
        canonical = canonical_string(method="POST", path="/hook", timestamp=timestamp, nonce=nonce, body=body)
        expected = hmac.new(self.endpoint.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(signature, expected, "the outgoing signature must use the same HMAC scheme as the machine API")
        self.assertEqual(json.loads(body)["event"], "order.placed")

    def test_a_failed_delivery_stays_pending_for_retry_and_bumps_endpoint_failures(self):
        delivery = self._pending()

        with patch("apps.integrations.services.webhooks.urllib.request.urlopen", side_effect=URLError("connection refused")):
            deliver_pending_webhooks()

        delivery.refresh_from_db()
        self.endpoint.refresh_from_db()
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING)
        self.assertEqual(delivery.attempts, 1)
        self.assertTrue(delivery.error)
        self.assertEqual(self.endpoint.consecutive_failures, 1)

    def test_retries_are_capped_then_marked_failed(self):
        delivery = self._pending(attempts=MAX_WEBHOOK_ATTEMPTS - 1)

        with patch("apps.integrations.services.webhooks.urllib.request.urlopen", side_effect=URLError("connection refused")):
            deliver_pending_webhooks()

        delivery.refresh_from_db()
        self.assertEqual(delivery.attempts, MAX_WEBHOOK_ATTEMPTS)
        self.assertEqual(delivery.status, WebhookDelivery.Status.FAILED)

    def test_one_endpoint_failing_does_not_block_delivery_to_another(self):
        other_pharmacy = Pharmacy.objects.create(name="Achrafieh Health", area="Achrafieh", city="Beirut", phone="+961-1-111-111")
        other_endpoint = WebhookEndpoint.objects.create(pharmacy=other_pharmacy, url="https://other.example.test/hook", secret="whsec_other", events=[], is_active=True)
        self._pending()
        self._pending(endpoint=other_endpoint)

        ok_response = Mock()
        ok_response.getcode.return_value = 200
        ok_response.__enter__ = Mock(return_value=ok_response)
        ok_response.__exit__ = Mock(return_value=False)

        def side_effect(request, timeout=None):
            if request.full_url == self.endpoint.url:
                raise URLError("connection refused")
            return ok_response

        with patch("apps.integrations.services.webhooks.urllib.request.urlopen", side_effect=side_effect):
            attempted = deliver_pending_webhooks()

        self.assertEqual(attempted, 2)
        self.assertEqual(WebhookDelivery.objects.filter(endpoint=self.endpoint, status=WebhookDelivery.Status.PENDING).count(), 1)
        self.assertEqual(WebhookDelivery.objects.filter(endpoint=other_endpoint, status=WebhookDelivery.Status.DELIVERED).count(), 1)


class OrderPlacementWebhookTests(TestCase):
    def test_placing_an_order_dispatches_an_order_placed_webhook_to_the_pharmacy(self):
        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from apps.inventory.services.stock import create_inventory_batch
        from apps.medicines.models import Medicine
        from apps.orders.services.placement import place_order

        User = get_user_model()
        pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal("33.8975"), longitude=Decimal("35.4790"),
        )
        owner = User.objects.create_user(email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=pharmacy)
        shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=owner,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )
        address = shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal("33.8991"), longitude=Decimal("35.4772"), is_default=True,
        )
        WebhookEndpoint.objects.create(pharmacy=pharmacy, url="https://pos.example.test/hook", secret="whsec_test", events=["order.placed"], is_active=True)

        order = place_order(customer=shopper, items=[{"medicine": str(medicine.id), "quantity": 2}], address=address)

        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.event, "order.placed")
        self.assertEqual(delivery.payload["order_reference"], order.reference)
        self.assertEqual(delivery.status, WebhookDelivery.Status.PENDING, "the HTTP call must not happen inline")
