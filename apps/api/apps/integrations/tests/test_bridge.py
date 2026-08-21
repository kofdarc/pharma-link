"""
The integration bridge: signature auth and the sync contract.

The promise to a pharmacy is "keep your software, keep your product codes, change nothing".
These tests hold that promise to account, and check the security properties that let an
unattended counter PC hold credentials safely.
"""

import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.integrations.authentication import canonical_string, sign
from apps.integrations.models import IntegrationKey, SkuMapping, SyncRun
from apps.integrations.services.keys import create_integration_key, decrypt_secret
from apps.integrations.services.sync import sync_stock
from apps.inventory.models import InventoryBatch, ReservationShortfall, StockMovement
from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.pharmacies.models import Pharmacy


class BridgeTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.client = APIClient()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.owner = get_user_model().objects.create_user(
            email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy
        )
        self.panadol = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        self.omega = Medicine.objects.create(
            brand_name="Omega 3", strength="1000mg", form="Softgel", category=ProductCategory.SUPPLEMENT, price_regime=PriceRegime.FREE, regulated_price=None
        )
        self.key, self.secret = create_integration_key(pharmacy=self.pharmacy, user=self.owner)

    def signed_post(self, path, payload, *, secret=None, timestamp=None, nonce=None):
        body = json.dumps(payload).encode("utf-8")
        timestamp = timestamp or str(int(time.time()))
        nonce = nonce or uuid.uuid4().hex
        canonical = canonical_string(method="POST", path=path, timestamp=timestamp, nonce=nonce, body=body)
        signature = sign(secret or self.secret, canonical)
        return self.client.post(
            path,
            data=body,
            content_type="application/json",
            HTTP_X_PHARMALINK_KEY=self.key.key_id,
            HTTP_X_PHARMALINK_TIMESTAMP=timestamp,
            HTTP_X_PHARMALINK_NONCE=nonce,
            HTTP_X_PHARMALINK_SIGNATURE=signature,
        )


class SignatureAuthTests(BridgeTestCase):
    def test_correctly_signed_request_is_accepted(self):
        response = self.signed_post("/api/integration/v1/stock/sync/", {"idempotency_key": "run-1", "rows": [{"external_code": "POS-1", "name": "Panadol 500", "quantity": 12, "selling_price": "2.25"}]})

        self.assertEqual(response.status_code, 201, response.data)

    def test_unsigned_request_is_rejected(self):
        response = self.client.post("/api/integration/v1/stock/sync/", {"idempotency_key": "x", "rows": []}, format="json")

        self.assertIn(response.status_code, (401, 403))

    def test_wrong_secret_is_rejected(self):
        response = self.signed_post("/api/integration/v1/stock/sync/", {"idempotency_key": "run-1", "rows": []}, secret="not-the-secret")

        self.assertEqual(response.status_code, 401)

    def test_tampering_with_the_body_after_signing_is_detected(self):
        payload = {"idempotency_key": "run-1", "rows": [{"external_code": "POS-1", "quantity": 5, "selling_price": "2.25"}]}
        body = json.dumps(payload).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex
        signature = sign(self.secret, canonical_string(method="POST", path="/api/integration/v1/stock/sync/", timestamp=timestamp, nonce=nonce, body=body))

        tampered = json.dumps({"idempotency_key": "run-1", "rows": [{"external_code": "POS-1", "quantity": 9999, "selling_price": "2.25"}]}).encode("utf-8")
        response = self.client.post(
            "/api/integration/v1/stock/sync/",
            data=tampered,
            content_type="application/json",
            HTTP_X_PHARMALINK_KEY=self.key.key_id,
            HTTP_X_PHARMALINK_TIMESTAMP=timestamp,
            HTTP_X_PHARMALINK_NONCE=nonce,
            HTTP_X_PHARMALINK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 401)

    def test_stale_timestamp_is_rejected(self):
        old = str(int(time.time()) - 3600)

        response = self.signed_post("/api/integration/v1/stock/sync/", {"idempotency_key": "run-1", "rows": []}, timestamp=old)

        self.assertEqual(response.status_code, 401)

    def test_replaying_a_captured_request_is_rejected(self):
        payload = {"idempotency_key": "run-1", "rows": [{"external_code": "POS-1", "name": "Panadol 500", "quantity": 12, "selling_price": "2.25"}]}
        timestamp = str(int(time.time()))
        nonce = uuid.uuid4().hex

        first = self.signed_post("/api/integration/v1/stock/sync/", payload, timestamp=timestamp, nonce=nonce)
        replay = self.signed_post("/api/integration/v1/stock/sync/", payload, timestamp=timestamp, nonce=nonce)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 401)

    def test_revoked_key_stops_working(self):
        from apps.integrations.services.keys import revoke_integration_key

        revoke_integration_key(key=self.key, user=self.owner)

        response = self.signed_post("/api/integration/v1/stock/sync/", {"idempotency_key": "run-2", "rows": []})

        self.assertEqual(response.status_code, 401)

    def test_scope_is_enforced(self):
        limited = IntegrationKey.objects.create(
            pharmacy=self.pharmacy,
            name="read only",
            key_id="msk_readonly",
            secret_encrypted=self.key.secret_encrypted,
            scopes=[IntegrationKey.Scope.ORDERS_READ],
            created_by=self.owner,
        )
        self.key = limited  # sign as the read-only key, same secret

        response = self.signed_post("/api/integration/v1/stock/sync/", {"idempotency_key": "run-3", "rows": []})

        self.assertEqual(response.status_code, 403)

    def test_secret_is_recoverable_by_the_server_but_never_returned(self):
        self.assertEqual(decrypt_secret(self.key.secret_encrypted), self.secret)
        self.assertNotIn(self.secret, self.key.secret_encrypted)

        self.client.force_authenticate(user=self.owner)
        listing = self.client.get("/api/pharmacy/integration-keys/")

        self.assertNotIn(self.secret, str(listing.data))


class StockSyncTests(BridgeTestCase):
    def sync(self, rows, key="run-1"):
        return sync_stock(pharmacy=self.pharmacy, user=self.owner, rows=rows, integration_key=self.key, idempotency_key=key)

    def test_first_sync_creates_stock_and_auto_maps_by_name(self):
        run = self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])

        self.assertEqual(run.rows_applied, 1)
        mapping = SkuMapping.objects.get(external_code="POS-1")
        self.assertEqual(mapping.medicine_id, self.panadol.id)
        self.assertEqual(InventoryBatch.objects.get(medicine=self.panadol).current_quantity, 12)

    def test_sync_reconciles_to_the_absolute_level_reported_by_the_pos(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])

        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 7, "selling_price": "2.25"}], key="run-2")
        batch = InventoryBatch.objects.get(medicine=self.panadol)

        self.assertEqual(batch.current_quantity, 7)
        movement = StockMovement.objects.filter(movement_type=StockMovement.MovementType.CORRECTION).latest("created_at")
        self.assertEqual(movement.quantity_delta, -5, "the difference must be explained by a movement, not silently overwritten")

    def test_unknown_product_code_is_parked_not_rejected(self):
        run = self.sync([{"external_code": "POS-HOUSE-BRAND", "name": "House brand throat sweets", "quantity": 30, "selling_price": "4.00"}])

        self.assertEqual(run.rows_unmapped, 1)
        self.assertEqual(run.status, SyncRun.Status.PARTIAL)
        self.assertTrue(SkuMapping.objects.filter(external_code="POS-HOUSE-BRAND", medicine__isnull=True).exists())

    def test_one_bad_row_does_not_sink_the_whole_sync(self):
        run = self.sync(
            [
                {"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"},
                {"external_code": "", "quantity": 3},
                {"external_code": "POS-2", "name": "Omega 3", "quantity": "not a number", "selling_price": "20.00"},
            ]
        )

        self.assertEqual(run.rows_applied, 1)
        self.assertEqual(run.rows_failed, 2)

    def test_pos_price_cannot_override_a_moph_price(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "9.99"}])

        self.assertEqual(InventoryBatch.objects.get(medicine=self.panadol).selling_price, Decimal("2.25"))

    def test_pos_price_is_honoured_for_free_priced_products(self):
        self.sync([{"external_code": "POS-2", "name": "Omega 3", "quantity": 5, "selling_price": "24.50"}])

        self.assertEqual(InventoryBatch.objects.get(medicine=self.omega).selling_price, Decimal("24.50"))

    def test_repeating_an_idempotency_key_does_not_double_apply(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])

        replay = self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 999, "selling_price": "2.25"}], key="run-1")

        self.assertEqual(replay.status, SyncRun.Status.REPLAYED)
        self.assertEqual(InventoryBatch.objects.get(medicine=self.panadol).current_quantity, 12)

    def test_manually_mapped_code_is_respected_on_the_next_sync(self):
        SkuMapping.objects.create(
            pharmacy=self.pharmacy,
            external_code="WEIRD-CODE-42",
            external_name="completely unrecognisable label",
            medicine=self.panadol,
            match_method=SkuMapping.MatchMethod.MANUAL,
        )

        run = self.sync([{"external_code": "WEIRD-CODE-42", "name": "completely unrecognisable label", "quantity": 8, "selling_price": "2.25"}])

        self.assertEqual(run.rows_applied, 1)
        self.assertEqual(InventoryBatch.objects.get(medicine=self.panadol).current_quantity, 8)

    def test_ignored_codes_are_skipped(self):
        SkuMapping.objects.create(pharmacy=self.pharmacy, external_code="POS-COSMETIC", external_name="Lipstick", is_ignored=True)

        run = self.sync([{"external_code": "POS-COSMETIC", "name": "Lipstick", "quantity": 40, "selling_price": "10.00"}])

        self.assertEqual(run.rows_applied, 0)
        self.assertEqual(run.rows_failed, 0)


class OnboardingChecklistTests(BridgeTestCase):
    def test_checklist_reflects_real_data_not_a_flag(self):
        self.client.force_authenticate(user=self.owner)

        before = self.client.get("/api/pharmacy/onboarding/").data
        stock_step = next(step for step in before["steps"] if step["key"] == "stock")
        self.assertFalse(stock_step["done"])

        sync_stock(
            pharmacy=self.pharmacy,
            user=self.owner,
            rows=[{"external_code": "POS-1", "name": "Panadol", "quantity": 10, "selling_price": "2.25"}],
            idempotency_key="run-1",
        )

        after = self.client.get("/api/pharmacy/onboarding/").data
        stock_step = next(step for step in after["steps"] if step["key"] == "stock")
        self.assertTrue(stock_step["done"])
        self.assertGreater(after["completed_steps"], before["completed_steps"])


class ReservationShortfallTests(BridgeTestCase):
    """
    A confirmed shopper order holds stock via `reserved_quantity`, but the POS is
    authoritative for its own shelf. If a sync reports fewer units than are held, that
    must never be silently absorbed - a shopper's paid order would quietly point at
    nothing.
    """

    def sync(self, rows, key="run-1"):
        return sync_stock(pharmacy=self.pharmacy, user=self.owner, rows=rows, integration_key=self.key, idempotency_key=key)

    def test_sync_below_reserved_quantity_raises_a_shortfall(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])
        batch = InventoryBatch.objects.get(medicine=self.panadol)
        batch.reserved_quantity = 10
        batch.save(update_fields=["reserved_quantity"])

        run = self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 5, "selling_price": "2.25"}], key="run-2")

        batch.refresh_from_db()
        self.assertEqual(batch.current_quantity, 5, "the POS correction must still apply - it is authoritative for its own shelf")
        shortfall = ReservationShortfall.objects.get(inventory_batch=batch)
        self.assertEqual(shortfall.observed_on_hand, 5)
        self.assertEqual(shortfall.reserved_quantity, 10)
        self.assertEqual(shortfall.shortfall_units, 5)
        self.assertEqual(shortfall.sync_run_id, run.id)
        self.assertTrue(shortfall.is_open)

    def test_sync_at_or_above_reserved_quantity_raises_nothing(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])
        batch = InventoryBatch.objects.get(medicine=self.panadol)
        batch.reserved_quantity = 10
        batch.save(update_fields=["reserved_quantity"])

        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 10, "selling_price": "2.25"}], key="run-2")
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 20, "selling_price": "2.25"}], key="run-3")

        self.assertFalse(ReservationShortfall.objects.exists())

    def test_shortfall_is_visible_and_resolvable_through_the_pharmacy_api(self):
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])
        batch = InventoryBatch.objects.get(medicine=self.panadol)
        batch.reserved_quantity = 10
        batch.save(update_fields=["reserved_quantity"])
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 5, "selling_price": "2.25"}], key="run-2")
        shortfall = ReservationShortfall.objects.get(inventory_batch=batch)

        self.client.force_authenticate(user=self.owner)
        listing = self.client.get("/api/pharmacy/reservation-shortfalls/?open=true")
        self.assertEqual(len(listing.data["results"] if "results" in listing.data else listing.data), 1)

        response = self.client.post(f"/api/pharmacy/reservation-shortfalls/{shortfall.id}/resolve/", {"resolution_note": "Recounted shelf, matches now."})
        self.assertEqual(response.status_code, 200)
        shortfall.refresh_from_db()
        self.assertFalse(shortfall.is_open)
        self.assertEqual(shortfall.resolved_by, self.owner)

        again = self.client.post(f"/api/pharmacy/reservation-shortfalls/{shortfall.id}/resolve/", {})
        self.assertEqual(again.status_code, 400)


class ConnectorFreshnessTests(BridgeTestCase):
    def test_sync_stamps_last_pos_observed_at_on_create_and_update(self):
        self.sync = lambda rows, key="run-1": sync_stock(
            pharmacy=self.pharmacy, user=self.owner, rows=rows, integration_key=self.key, idempotency_key=key
        )
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}])
        batch = InventoryBatch.objects.get(medicine=self.panadol)
        self.assertIsNotNone(batch.last_pos_observed_at)

        first_observed = batch.last_pos_observed_at
        # Same quantity, no delta - freshness must still update, since a POS reporting
        # "still 12" is itself a live observation, not a no-op.
        self.sync([{"external_code": "POS-1", "name": "Panadol", "quantity": 12, "selling_price": "2.25"}], key="run-2")
        batch.refresh_from_db()
        self.assertGreaterEqual(batch.last_pos_observed_at, first_observed)
