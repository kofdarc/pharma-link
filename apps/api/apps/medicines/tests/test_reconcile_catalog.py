from decimal import Decimal
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.medicines.management.commands.reconcile_medicine_catalog import build_reconciliation_plan, enrich_unique_matches
from apps.medicines.models import Medicine, PriceRegime
from apps.medicines.services.moph_sync import MophRow, sync_prices


class ReconciliationPlanTests(SimpleTestCase):
    def setUp(self):
        self.legacy = Medicine(
            brand_name="EXAMPLE BRAND",
            generic_name="Example ingredient",
            strength="10mg",
            form="Tablet, film coated",
            classification="A01AA01",
            price_regime=PriceRegime.REGULATED,
            regulated_price=None,
        )
        self.priced = Medicine(
            brand_name="Example Brand",
            strength="10mg",
            form="Tablet",
            classification="",
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("4.25"),
        )
        self.unmatched = Medicine(
            brand_name="Legacy Only",
            strength="20mg",
            form="Capsule",
            classification="N02BE01",
            price_regime=PriceRegime.REGULATED,
            regulated_price=None,
        )

    def test_unique_brand_strength_match_ignores_case_and_form_wording(self):
        pairs, ambiguous, unmatched = build_reconciliation_plan([self.legacy, self.unmatched], [self.priced])

        self.assertEqual(pairs, [(self.legacy, self.priced)])
        self.assertEqual(ambiguous, 0)
        self.assertEqual(unmatched, 1)

    def test_enrichment_copies_missing_atc_and_generic_metadata(self):
        enriched = enrich_unique_matches([(self.legacy, self.priced)], updated_at=timezone.now())

        self.assertEqual(enriched, [self.priced])
        self.assertEqual(self.priced.classification, "A01AA01")
        self.assertEqual(self.priced.generic_name, "Example ingredient")


class ActiveRegulatedPriceConstraintTests(TestCase):
    def test_database_rejects_active_regulated_medicine_without_price(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Medicine.objects.create(
                brand_name="Invalid active regulated medicine",
                price_regime=PriceRegime.REGULATED,
                regulated_price=None,
            )

    def test_database_allows_inactive_legacy_regulated_medicine_without_price(self):
        medicine = Medicine.objects.create(
            brand_name="Historical regulated medicine",
            price_regime=PriceRegime.REGULATED,
            regulated_price=None,
            is_active=False,
        )

        self.assertIsNotNone(medicine.pk)


class MophSyncIdentityMatchingTests(TestCase):
    def test_sync_reuses_unique_brand_strength_when_form_wording_changes(self):
        existing = Medicine.objects.create(
            brand_name="Example Brand",
            strength="10mg",
            form="Capsule, soft gelatin",
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("3.00"),
        )

        result = sync_prices(
            [
                MophRow(
                    brand_name="Example Brand",
                    strength="10mg",
                    form="Softgel",
                    manufacturer="Example Manufacturer",
                    price_usd=Decimal("4.25"),
                )
            ],
            reference="test price list",
        )

        existing.refresh_from_db()
        self.assertEqual(Medicine.objects.count(), 1)
        self.assertEqual(existing.regulated_price, Decimal("4.25"))
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["created"], 0)
