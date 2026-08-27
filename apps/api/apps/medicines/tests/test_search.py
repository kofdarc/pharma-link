"""
Search & catalog matching - typo tolerance, brand<->generic aliasing, and multilingual
(Arabic-script) aliasing. See docs/AI_FEATURES.md §1.

These tests run against sqlite (this repo's dev/test DB, per DJANGO_TEST_SQLITE), so they
exercise the Python fuzzy-scan fallback in apps/medicines/services/search.py, not the
Postgres trigram fast path - that path is exercised implicitly by staying behind the same
public functions and is safe by construction (see migration 0008_trigram_search_indexes,
which no-ops on any non-Postgres backend).
"""

from django.test import TestCase

from apps.medicines.models import Medicine, MedicineAlias, PriceRegime, ProductCategory
from apps.medicines.services.search import best_catalog_match, normalize_name, search_medicines


class NormalizeNameTests(TestCase):
    def test_preserves_arabic_script(self):
        # The old ASCII-only pattern ([^a-z0-9]+) stripped Arabic entirely, making any
        # Arabic-script query un-matchable by the fuzzy fallback. This is the fix.
        self.assertEqual(normalize_name("بانادول"), "بانادول")

    def test_preserves_accented_latin(self):
        self.assertEqual(normalize_name("Efferalgan Café"), "efferalgan café")

    def test_collapses_punctuation_and_case(self):
        self.assertEqual(normalize_name("  Panadol!! 500MG "), "panadol 500mg")

    def test_empty_input(self):
        self.assertEqual(normalize_name(""), "")
        self.assertEqual(normalize_name(None), "")


class SearchMedicinesTests(TestCase):
    def setUp(self):
        self.panadol = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price="2.25",
        )
        MedicineAlias.objects.create(medicine=self.panadol, alias="Acetaminophen", alias_type=MedicineAlias.AliasType.GENERIC)
        MedicineAlias.objects.create(medicine=self.panadol, alias="بانادول", alias_type=MedicineAlias.AliasType.TRANSLITERATION)

        self.augmentin = Medicine.objects.create(
            brand_name="Augmentin",
            generic_name="Amoxicillin/Clavulanate",
            strength="1g",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price="14.75",
        )
        MedicineAlias.objects.create(medicine=self.augmentin, alias="Augmentine", alias_type=MedicineAlias.AliasType.MISSPELLING)

    def test_direct_brand_match(self):
        results = search_medicines("Panadol")
        self.assertIn(self.panadol, results)

    def test_generic_name_finds_brand(self):
        results = search_medicines("Paracetamol")
        self.assertIn(self.panadol, results)

    def test_alias_finds_brand(self):
        results = search_medicines("Acetaminophen")
        self.assertIn(self.panadol, results)

    def test_arabic_alias_exact_match(self):
        results = search_medicines("بانادول")
        self.assertIn(self.panadol, results)

    def test_misspelling_falls_back_to_fuzzy_match(self):
        # "Augmentine" is stored as a MISSPELLING alias of Augmentin, but a shopper typing a
        # *different* one-letter-off spelling should still land on it via the fuzzy scan.
        results = search_medicines("Augmentn")
        self.assertIn(self.augmentin, results)

    def test_no_results_for_unrelated_query(self):
        results = search_medicines("xyznonexistentdrug")
        self.assertNotIn(self.panadol, results)
        self.assertNotIn(self.augmentin, results)


class BestCatalogMatchTests(TestCase):
    def setUp(self):
        self.glucophage = Medicine.objects.create(
            brand_name="Glucophage",
            generic_name="Metformin",
            strength="850mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price="6.30",
        )
        MedicineAlias.objects.create(medicine=self.glucophage, alias="غلوكوفاج", alias_type=MedicineAlias.AliasType.TRANSLITERATION)

    def test_exact_alias_match_is_confidence_one(self):
        medicine, confidence = best_catalog_match("غلوكوفاج")
        self.assertEqual(medicine, self.glucophage)
        self.assertEqual(confidence, 1)

    def test_fuzzy_typo_match(self):
        medicine, confidence = best_catalog_match("Glucophag")
        self.assertEqual(medicine, self.glucophage)
        self.assertGreaterEqual(confidence, 0.78)

    def test_unrelated_name_returns_none(self):
        medicine, _confidence = best_catalog_match("Completely Unrelated Product Name")
        self.assertIsNone(medicine)
