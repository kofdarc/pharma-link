"""
apps.prescriptions.services.extraction: turning raw OCR text into candidate drug lines.
Pure parsing logic - no OCR engine involved, see docs/AI_FEATURES.md §2.
"""

from decimal import Decimal

from django.test import TestCase

from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.prescriptions.services.extraction import extract_candidate_lines


class ExtractionTests(TestCase):
    def setUp(self):
        self.panadol = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("2.25"),
        )

    def test_matches_a_known_drug_with_dose_and_quantity(self):
        candidates = extract_candidate_lines("Panadol 500mg x30")

        self.assertEqual(len(candidates), 1)
        line = candidates[0]
        self.assertEqual(line["medicine_id"], str(self.panadol.id))
        self.assertEqual(line["dosage_guess"].replace(" ", "").lower(), "500mg")
        self.assertEqual(line["quantity_guess"], 30)

    def test_quantity_pattern_recognises_unit_words(self):
        candidates = extract_candidate_lines("Panadol 20 tablets")

        self.assertEqual(candidates[0]["quantity_guess"], 20)

    def test_metadata_lines_are_skipped(self):
        text = "Patient: Jane Doe\nDoctor: Dr. Rima Khalil\nDate: 2026-08-01\nPanadol 500mg x30"

        candidates = extract_candidate_lines(text)

        self.assertEqual(len(candidates), 1)
        self.assertIn("Panadol", candidates[0]["raw_line"])

    def test_blank_and_punctuation_only_lines_are_skipped(self):
        text = "\n\n---\nPanadol 500mg x30\n***"

        candidates = extract_candidate_lines(text)

        self.assertEqual(len(candidates), 1)

    def test_unmatched_drug_name_is_returned_with_no_medicine(self):
        candidates = extract_candidate_lines("Completely Unknown Drug 10mg x5")

        self.assertEqual(len(candidates), 1)
        self.assertIsNone(candidates[0]["medicine_id"])
        self.assertEqual(candidates[0]["medicine_name"], "")

    def test_multiple_lines_each_produce_a_candidate(self):
        text = "Panadol 500mg x30\nAnother Unknown Item x5"

        candidates = extract_candidate_lines(text)

        self.assertEqual(len(candidates), 2)

    def test_misspelled_drug_name_still_fuzzy_matches(self):
        candidates = extract_candidate_lines("Panadoll 500mg x30")

        self.assertEqual(candidates[0]["medicine_id"], str(self.panadol.id))

    def test_empty_text_yields_no_candidates(self):
        self.assertEqual(extract_candidate_lines(""), [])

    def test_french_metadata_lines_are_skipped(self):
        text = "Nom: Jean Dupont\nDocteur: Dr. Rima Khalil\nOrdonnance No: 4521\nPanadol 500mg x30"

        candidates = extract_candidate_lines(text)

        self.assertEqual(len(candidates), 1)
        self.assertIn("Panadol", candidates[0]["raw_line"])

    def test_arabic_metadata_lines_are_skipped(self):
        text = "اسم المريض: جون\nالطبيب: د. ريما\nPanadol 500mg x30"

        candidates = extract_candidate_lines(text)

        self.assertEqual(len(candidates), 1)
        self.assertIn("Panadol", candidates[0]["raw_line"])

    def test_a_drug_name_that_starts_like_a_metadata_prefix_is_not_skipped(self):
        # "tel" is a metadata prefix (téléphone/tel) but must not swallow "Telfast" - a
        # real drug - via naive substring matching. Regression test for that bug.
        Medicine.objects.create(
            brand_name="Telfast",
            generic_name="Fexofenadine",
            strength="120mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.FREE,
        )

        candidates = extract_candidate_lines("Telfast 120mg x10")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["medicine_name"], "Telfast 120mg Tablet")

    def test_french_posology_unit_words_are_recognised_as_quantity(self):
        candidates = extract_candidate_lines("Panadol 500mg 20 cp")

        self.assertEqual(candidates[0]["quantity_guess"], 20)

    def test_gelule_unit_word_is_recognised_as_quantity(self):
        candidates = extract_candidate_lines("Amoxicilline 500mg 14 gélules")

        self.assertEqual(candidates[0]["quantity_guess"], 14)

    def test_prefers_the_strength_variant_matching_the_written_dose(self):
        panadol_extra = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="1g",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("3.50"),
        )

        candidates = extract_candidate_lines("Panadol 1g x20")

        self.assertEqual(candidates[0]["medicine_id"], str(panadol_extra.id))

    def test_falls_back_to_the_name_match_when_no_strength_variant_exists(self):
        candidates = extract_candidate_lines("Panadol 250mg x20")

        self.assertEqual(candidates[0]["medicine_id"], str(self.panadol.id))
