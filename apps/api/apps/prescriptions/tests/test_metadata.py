"""
apps.prescriptions.services.metadata: pulling the prescriber name and the
prescription date off raw OCR text so a patient's upload form can pre-fill them.
Pure string parsing - no OCR engine involved (see docs/AI_FEATURES.md §2).
"""

from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.prescriptions.services.metadata import (
    extract_doctor_name,
    extract_prescription_date,
    extract_prescription_metadata,
)


class DoctorNameTests(SimpleTestCase):
    def test_bare_title_prefix(self):
        self.assertEqual(extract_doctor_name("Dr. Haddad"), "Dr. Haddad")

    def test_title_without_period_is_normalised(self):
        self.assertEqual(extract_doctor_name("Dr Rima Khalil"), "Dr. Rima Khalil")

    def test_english_label(self):
        self.assertEqual(extract_doctor_name("Doctor: Rima Khalil"), "Dr. Rima Khalil")

    def test_french_label(self):
        self.assertEqual(extract_doctor_name("Docteur: Jean Khoury"), "Dr. Jean Khoury")

    def test_prescriber_label_keeps_the_plain_name(self):
        self.assertEqual(extract_doctor_name("Prescriber: Rima Khalil, MD"), "Rima Khalil")

    def test_credential_and_trailing_detail_are_trimmed(self):
        self.assertEqual(extract_doctor_name("Dr. Rima Khalil, License 4521"), "Dr. Rima Khalil")

    def test_found_among_other_lines(self):
        text = "Patient: Jane Doe\nDr. Rima Khalil\nPanadol 500mg x30"
        self.assertEqual(extract_doctor_name(text), "Dr. Rima Khalil")

    def test_arabic_label_and_title(self):
        self.assertEqual(extract_doctor_name("الطبيب: د. ريما خليل"), "ريما خليل")

    def test_a_patient_name_line_is_not_mistaken_for_the_doctor(self):
        self.assertIsNone(extract_doctor_name("Patient name: John Smith"))

    def test_no_doctor_anywhere(self):
        self.assertIsNone(extract_doctor_name("Panadol 500mg x30\nTake one twice daily"))


class PrescriptionDateTests(SimpleTestCase):
    def setUp(self):
        # A recent date whose day-of-month is <= 12, so "dd/mm/yyyy" is genuinely
        # ambiguous with "mm/dd/yyyy" and exercises the day-first default.
        day = timezone.localdate()
        while day.day > 12:
            day -= timedelta(days=1)
        self.recent = day

    def test_iso_date_with_label(self):
        self.assertEqual(extract_prescription_date(f"Date: {self.recent.isoformat()}"), self.recent.isoformat())

    def test_day_first_slashes(self):
        text = f"Date: {self.recent.day:02d}/{self.recent.month:02d}/{self.recent.year}"
        self.assertEqual(extract_prescription_date(text), self.recent.isoformat())

    def test_day_first_dotted(self):
        text = f"{self.recent.day:02d}.{self.recent.month:02d}.{self.recent.year}"
        self.assertEqual(extract_prescription_date(text), self.recent.isoformat())

    def test_text_month(self):
        text = f"Prescribed on {self.recent.day} {self.recent.strftime('%b')} {self.recent.year}"
        self.assertEqual(extract_prescription_date(text), self.recent.isoformat())

    def test_unambiguous_month_first_is_read_as_month_first(self):
        target = timezone.localdate()
        while target.day <= 12:
            target -= timedelta(days=1)
        text = f"Date: {target.month:02d}/{target.day:02d}/{target.year}"
        self.assertEqual(extract_prescription_date(text), target.isoformat())

    def test_date_of_birth_line_is_skipped(self):
        text = f"Date of birth: 12/05/1980\nDate: {self.recent.isoformat()}"
        self.assertEqual(extract_prescription_date(text), self.recent.isoformat())

    def test_a_date_far_in_the_past_is_rejected(self):
        self.assertIsNone(extract_prescription_date("12/05/1980"))

    def test_a_future_date_is_rejected(self):
        self.assertIsNone(extract_prescription_date("Date: 01/01/2099"))

    def test_no_date_present(self):
        self.assertIsNone(extract_prescription_date("Panadol 500mg x30"))


class MetadataTests(SimpleTestCase):
    def test_combines_both_fields(self):
        today = timezone.localdate().isoformat()
        fields = extract_prescription_metadata(f"Dr. Rima Khalil\nDate: {today}\nPanadol 500mg x30")
        self.assertEqual(fields, {"doctor_name": "Dr. Rima Khalil", "prescription_date": today})

    def test_missing_values_are_absent_not_blank(self):
        self.assertEqual(extract_prescription_metadata("Panadol 500mg x30"), {})

    def test_empty_text(self):
        self.assertEqual(extract_prescription_metadata(""), {})
