"""
apps.prescriptions.services.structured / .nlp: turning OCR text into the structured field
set the patient sees and a pharmacist edits. The regex extractor is deterministic; the
openai_compatible path is exercised with the HTTP call mocked.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.prescriptions.services.nlp.base import NlpExtractorError
from apps.prescriptions.services.nlp.regex_extractor import RegexExtractor
from apps.prescriptions.services.structured import extract_structured

RX_TEXT = (
    "Dr. Rima Khalil\n"
    "Patient: John Smith\n"
    "Tel: 03 123 456\n"
    "Date: 14/03/2026\n"
    "Panadol 500mg x30 - 1 tablet twice daily for 7 days\n"
    "Amoxil 500mg x21 - 1 cap tid, no refills\n"
)


class RegexExtractorTests(TestCase):
    def setUp(self):
        Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("2.25"),
        )

    def test_header_fields(self):
        fields = RegexExtractor().extract(RX_TEXT)
        self.assertEqual(fields["doctor_name"], "Dr. Rima Khalil")
        self.assertEqual(fields["patient_name"], "John Smith")
        self.assertEqual(fields["patient_phone"], "03123456")
        self.assertEqual(fields["prescription_date"], "2026-03-14")

    def test_medications_with_directions_duration_refills(self):
        meds = RegexExtractor().extract(RX_TEXT)["medications"]
        self.assertEqual(len(meds), 2)
        panadol = meds[0]
        self.assertIn("Panadol", panadol["name"])
        self.assertEqual(panadol["quantity"], 30)
        self.assertIn("twice daily", panadol["directions"].lower())
        self.assertEqual(panadol["duration"], "7 days")
        self.assertEqual(meds[1]["refills"], 0)

    def test_empty_text_is_the_empty_shape(self):
        fields = RegexExtractor().extract("")
        self.assertEqual(fields["medications"], [])
        self.assertEqual(fields["doctor_name"], "")


class OrchestratorTests(TestCase):
    def test_blank_input_returns_empty_result_with_no_provider(self):
        result = extract_structured("   ")
        self.assertTrue(result.is_empty)
        self.assertEqual(result.provider, "")

    @override_settings(PRESCRIPTION_NLP_PROVIDER="regex")
    def test_default_uses_the_regex_extractor(self):
        result = extract_structured("Dr. Rima Khalil\nDate: 14/03/2026")
        self.assertEqual(result.provider, "regex")
        self.assertEqual(result.fields["doctor_name"], "Dr. Rima Khalil")

    @override_settings(
        PRESCRIPTION_NLP_PROVIDER="openai_compatible",
        PRESCRIPTION_NLP_BASE_URL="https://gw.test/v1",
        PRESCRIPTION_NLP_API_KEY="k",
        PRESCRIPTION_NLP_MODEL="some/model",
    )
    def test_openai_compatible_result_is_normalised(self):
        payload = {
            "patient_name": "  John Smith ",
            "patient_phone": "03 123 456",
            "doctor_name": "Dr. Rima Khalil",
            "prescription_date": "2026-03-14",
            "medications": [
                {"name": "Panadol", "strength": "500mg", "quantity": "30", "directions": "1 tab BID", "duration": "7 days", "refills": "0"},
                {"name": "", "strength": "junk"},  # dropped - no name
            ],
            "notes": "Bring ID",
            "unexpected": "ignored",
        }
        with patch(
            "apps.prescriptions.services.nlp.openai_compatible.OpenAiCompatibleExtractor.extract",
            return_value=payload,
        ):
            result = extract_structured(RX_TEXT)
        self.assertEqual(result.provider, "openai_compatible")
        self.assertEqual(result.fields["patient_name"], "John Smith")
        self.assertEqual(len(result.fields["medications"]), 1)
        self.assertEqual(result.fields["medications"][0]["quantity"], 30)
        self.assertNotIn("unexpected", result.fields)

    @override_settings(
        PRESCRIPTION_NLP_PROVIDER="openai_compatible",
        PRESCRIPTION_NLP_BASE_URL="https://gw.test/v1",
        PRESCRIPTION_NLP_API_KEY="k",
        PRESCRIPTION_NLP_MODEL="some/model",
    )
    def test_falls_back_to_regex_when_the_model_call_fails(self):
        with patch(
            "apps.prescriptions.services.nlp.openai_compatible.OpenAiCompatibleExtractor.extract",
            side_effect=NlpExtractorError("gateway down"),
        ):
            result = extract_structured("Dr. Rima Khalil\nDate: 14/03/2026")
        self.assertEqual(result.provider, "regex")
        self.assertEqual(result.fields["doctor_name"], "Dr. Rima Khalil")
