"""
The single-call image -> structured fields providers (vision_structured /
anthropic_structured) and the pipeline that prefers them. HTTP is mocked throughout: no
network, no key needed to run this.

The fixture is a real prescription that the previous two-stage pipeline failed on in
production - a handwritten Indian dental script with an unlabelled patient line, `1-0-1`
dose columns, and four drugs that are not in the Lebanese catalog (Augmentin, Enzoflam,
Pan-D, Hexigel). It scored 0.0 and the patient was shown "we couldn't read this
prescription clearly enough" over a read that was, in fact, perfectly legible.
"""

import io
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.prescriptions.services.ocr.anthropic_structured import AnthropicStructuredOcrProvider
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.vision_structured import VisionStructuredOcrProvider, render_text
from apps.prescriptions.services.structured import extraction_confidence, structured_from_vision, vision_confidence

VISION_SETTINGS = dict(
    PRESCRIPTION_OCR_VISION_BASE_URL="https://gw.test/v1",
    PRESCRIPTION_OCR_VISION_API_KEY="vk-test",
    PRESCRIPTION_OCR_VISION_MODEL="some/vision-model",
)

# What a working vision read of that dental script looks like.
DENTAL_SCRIPT = {
    "patient_name": "Sachin Sansare",
    "patient_age": "28/M",
    "patient_phone": "",
    "doctor_name": "",
    "clinic_name": "The White Tusk",
    "prescription_date": "2022-10-12",
    "medications": [
        {
            "name": "Augmentin", "strength": "625mg", "quantity": None, "dose_pattern": "1-0-1",
            "directions": "1 tablet in the morning and 1 at night, after meals",
            "duration": "5 days", "refills": None, "legible": True,
        },
        {
            "name": "Enzoflam", "strength": "", "quantity": None, "dose_pattern": "1-0-1",
            "directions": "1 tablet in the morning and 1 at night, after meals",
            "duration": "5 days", "refills": None, "legible": True,
        },
        {
            "name": "Pan-D", "strength": "40mg", "quantity": None, "dose_pattern": "1-0-0",
            "directions": "1 tablet in the morning, before meals",
            "duration": "5 days", "refills": None, "legible": True,
        },
        {
            "name": "Hexigel", "strength": "", "quantity": None, "dose_pattern": "1-0-1",
            "directions": "Gum paint, massage morning and night",
            "duration": "1 week", "refills": None, "legible": True,
        },
    ],
    "notes": "Adv: Hexigel gum paint massage",
    "illegible_count": 0,
    "transcription_confidence": 0.9,
}


def _chat_response(payload: dict):
    fake = MagicMock()
    fake.read.return_value = json.dumps({"choices": [{"message": {"content": json.dumps(payload)}}]}).encode("utf-8")
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


def _anthropic_response(payload: dict):
    # The provider prefills the assistant turn with "{", so the response omits it.
    body = json.dumps(payload)[1:]
    fake = MagicMock()
    fake.read.return_value = json.dumps({"content": [{"type": "text", "text": body}]}).encode("utf-8")
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


class VisionStructuredProviderTests(TestCase):
    def test_raises_when_not_configured(self):
        with self.assertRaises(OcrProviderError):
            VisionStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/png")

    @override_settings(**VISION_SETTINGS)
    def test_rejects_an_unsupported_file_type(self):
        with self.assertRaises(UnsupportedFileType):
            VisionStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"x"), mime_type="text/plain")

    @override_settings(**VISION_SETTINGS)
    @patch("urllib.request.urlopen")
    def test_reads_every_row_of_the_dental_script(self, urlopen):
        urlopen.return_value = _chat_response(DENTAL_SCRIPT)
        fields = VisionStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/jpeg")

        self.assertEqual([med["name"] for med in fields["medications"]], ["Augmentin", "Enzoflam", "Pan-D", "Hexigel"])
        # The row with no printed strength survives - it was silently dropped before.
        self.assertEqual(fields["medications"][1]["strength"], "")
        # Dosing notation is kept verbatim AND expanded, never one at the cost of the other.
        self.assertEqual(fields["medications"][0]["dose_pattern"], "1-0-1")
        self.assertIn("morning", fields["medications"][0]["directions"])
        self.assertEqual(fields["patient_name"], "Sachin Sansare")
        self.assertEqual(fields["prescription_date"], "2022-10-12")

    @override_settings(**VISION_SETTINGS)
    @patch("urllib.request.urlopen")
    def test_drops_keys_the_model_invented(self, urlopen):
        urlopen.return_value = _chat_response({**DENTAL_SCRIPT, "diagnosis": "pulpitis", "advice": "extract the tooth"})
        fields = VisionStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/jpeg")
        self.assertNotIn("diagnosis", fields)
        self.assertNotIn("advice", fields)

    @override_settings(**VISION_SETTINGS)
    @patch("urllib.request.urlopen")
    def test_raises_on_a_non_json_answer(self, urlopen):
        fake = MagicMock()
        fake.read.return_value = json.dumps({"choices": [{"message": {"content": "I can't read this."}}]}).encode("utf-8")
        fake.__enter__.return_value = fake
        fake.__exit__.return_value = False
        urlopen.return_value = fake
        with self.assertRaises(OcrProviderError):
            VisionStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/jpeg")

    @override_settings(**VISION_SETTINGS)
    @patch("urllib.request.urlopen")
    def test_extract_text_renders_the_same_read_as_plain_text(self, urlopen):
        urlopen.return_value = _chat_response(DENTAL_SCRIPT)
        result = VisionStructuredOcrProvider().extract_text(io.BytesIO(b"img"), mime_type="image/jpeg")
        self.assertIn("Augmentin 625mg", result.text)
        self.assertIn("Enzoflam", result.text)
        self.assertIn("Sachin Sansare", result.text)
        # One call, not two - the text view is rendered from the structured read.
        self.assertEqual(urlopen.call_count, 1)


class AnthropicStructuredProviderTests(TestCase):
    @override_settings(ANTHROPIC_API_KEY="", PRESCRIPTION_OCR_PROVIDER="anthropic_structured")
    def test_raises_when_not_configured(self):
        with self.assertRaises(OcrProviderError):
            AnthropicStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/png")

    @override_settings(ANTHROPIC_API_KEY="sk-test", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    @patch("urllib.request.urlopen")
    def test_reads_the_dental_script_through_the_prefilled_brace(self, urlopen):
        urlopen.return_value = _anthropic_response(DENTAL_SCRIPT)
        fields = AnthropicStructuredOcrProvider().extract_structured_fields(io.BytesIO(b"img"), mime_type="image/jpeg")
        self.assertEqual([med["name"] for med in fields["medications"]], ["Augmentin", "Enzoflam", "Pan-D", "Hexigel"])


class VisionConfidenceTests(TestCase):
    def test_a_clean_read_of_out_of_catalog_drugs_is_not_low_confidence(self):
        """The production bug, as a test. Four drugs, none of them in the Lebanese catalog,
        read perfectly - this must reach the patient."""
        result = structured_from_vision(DENTAL_SCRIPT, "vision_structured")
        self.assertGreaterEqual(result.confidence, 0.45)
        self.assertEqual(len(result.fields["medications"]), 4)
        # Nothing linked to a SKU, and that is fine - it says nothing about the read quality.
        self.assertTrue(all(med["medicine_id"] == "" for med in result.fields["medications"]))

    def test_illegible_rows_pull_the_score_down(self):
        half_illegible = {
            **DENTAL_SCRIPT,
            "medications": [
                {**DENTAL_SCRIPT["medications"][0], "legible": False},
                {**DENTAL_SCRIPT["medications"][1], "legible": False},
                DENTAL_SCRIPT["medications"][2],
                DENTAL_SCRIPT["medications"][3],
            ],
        }
        self.assertLess(vision_confidence(half_illegible), vision_confidence(DENTAL_SCRIPT))

    def test_a_read_the_model_does_not_trust_is_low_confidence(self):
        unsure = {**DENTAL_SCRIPT, "transcription_confidence": 0.2}
        self.assertLess(vision_confidence(unsure), 0.45)

    def test_no_medications_read_is_treated_as_a_weak_result(self):
        empty = {**DENTAL_SCRIPT, "medications": []}
        self.assertLess(vision_confidence(empty), vision_confidence(DENTAL_SCRIPT))

    def test_a_bad_read_stays_hidden_however_confident_the_model_sounds(self):
        """The other half of the fix. Loosening the score must not let a genuinely failed
        read through - a model that rates itself 1.0 while marking every drug row illegible,
        or reading no drug rows at all, has contradicted itself and is not trusted."""
        all_illegible = {
            **DENTAL_SCRIPT,
            "transcription_confidence": 1.0,
            "medications": [{**med, "legible": False} for med in DENTAL_SCRIPT["medications"]],
        }
        self.assertLess(vision_confidence(all_illegible), 0.45)
        self.assertLess(vision_confidence({**DENTAL_SCRIPT, "transcription_confidence": 1.0, "medications": []}), 0.45)

    def test_a_garbled_regex_read_is_still_hidden(self):
        """Letterhead fragments with no dose, no quantity and no catalog match must not
        become a medication list just because the parsed-row credit was added."""
        garbled = {
            "patient_name": "",
            "doctor_name": "",
            "prescription_date": "",
            "medications": [
                {"name": "[illegible]", "strength": "", "dose_pattern": "", "directions": "", "duration": "", "quantity": None, "medicine_id": ""},
                {"name": "Cln Adr", "strength": "", "dose_pattern": "", "directions": "", "duration": "", "quantity": None, "medicine_id": ""},
            ],
        }
        self.assertLess(extraction_confidence(garbled), 0.45)

    def test_age_and_clinic_are_kept_in_notes_rather_than_dropped(self):
        result = structured_from_vision(DENTAL_SCRIPT, "vision_structured")
        self.assertIn("The White Tusk", result.fields["notes"])
        self.assertIn("28/M", result.fields["notes"])


class RenderTextTests(TestCase):
    def test_renders_a_readable_transcription(self):
        text = render_text(DENTAL_SCRIPT)
        self.assertIn("Patient: Sachin Sansare", text)
        self.assertIn("Pan-D 40mg", text)
        self.assertIn("1-0-0", text)
