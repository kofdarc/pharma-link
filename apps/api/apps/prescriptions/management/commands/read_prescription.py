"""
Run the configured OCR provider against a local image/PDF and print what it read - the
tuning loop for prescription extraction. Nothing is stored and no PrescriptionRecord is
touched; this only exercises the same code path an upload takes.

    python manage.py read_prescription ~/scans/rx.jpg
    python manage.py read_prescription ~/scans/rx.jpg --provider anthropic_structured
    python manage.py read_prescription ~/scans/*.jpg --json

Reads credentials from the environment the same way the app does (apps/api/.env), so keys
stay out of the shell history and out of any transcript.
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.prescriptions.models import OCR_LOW_CONFIDENCE_THRESHOLD
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.registry import get_provider
from apps.prescriptions.services.structured import extract_structured, structured_from_vision


class Command(BaseCommand):
    help = "OCR a local prescription image with the configured provider and print the structured read."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Image or PDF files to read.")
        parser.add_argument(
            "--provider",
            default=None,
            help="Override PRESCRIPTION_OCR_PROVIDER for this run (e.g. vision_structured, anthropic_structured).",
        )
        parser.add_argument("--json", action="store_true", help="Print the raw structured fields as JSON.")

    def handle(self, *args, **options):
        code = options["provider"] or settings.PRESCRIPTION_OCR_PROVIDER
        try:
            provider = get_provider(code)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.MIGRATE_HEADING(f"provider: {code}"))

        for raw_path in options["paths"]:
            path = Path(raw_path).expanduser()
            if not path.is_file():
                self.stderr.write(self.style.ERROR(f"{path}: not a file"))
                continue

            mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"=== {path.name} ({mime_type}) ==="))

            try:
                with path.open("rb") as file_obj:
                    if getattr(provider, "supports_structured", False):
                        raw = provider.extract_structured_fields(file_obj, mime_type=mime_type)
                        result = structured_from_vision(raw, provider.code)
                    else:
                        raw = None
                        ocr = provider.extract_text(file_obj, mime_type=mime_type)
                        self.stdout.write(self.style.HTTP_INFO("--- transcription ---"))
                        self.stdout.write(ocr.text or "(empty)")
                        result = extract_structured(ocr.text)
            except (OcrProviderError, UnsupportedFileType, ValueError, OSError) as exc:
                self.stderr.write(self.style.ERROR(f"{path.name}: {exc}"))
                continue

            if options["json"]:
                self.stdout.write(json.dumps({"raw": raw, "fields": result.fields, "confidence": result.confidence}, indent=2))
                continue

            self._render(result, raw)

    def _render(self, result, raw):
        fields = result.fields
        low = result.confidence < OCR_LOW_CONFIDENCE_THRESHOLD
        verdict = self.style.ERROR("LOW CONFIDENCE - hidden from patient") if low else self.style.SUCCESS("shown to patient")
        self.stdout.write(f"confidence: {result.confidence}  (threshold {OCR_LOW_CONFIDENCE_THRESHOLD})  {verdict}")
        if raw and raw.get("transcription_confidence") is not None:
            self.stdout.write(f"model self-rating: {raw['transcription_confidence']}  illegible tokens: {raw.get('illegible_count', 0)}")

        self.stdout.write("")
        for label, key in (
            ("patient", "patient_name"),
            ("phone", "patient_phone"),
            ("prescriber", "doctor_name"),
            ("date", "prescription_date"),
        ):
            self.stdout.write(f"{label:>12}: {fields.get(key) or '-'}")

        self.stdout.write("")
        self.stdout.write(f"medications ({len(fields.get('medications') or [])}):")
        for med in fields.get("medications") or []:
            link = med.get("catalog_name") or self.style.WARNING("no catalog match")
            self.stdout.write(f"  · {med.get('name')} {med.get('strength')}".rstrip())
            for label, key in (("dose", "dose_pattern"), ("directions", "directions"), ("duration", "duration")):
                if med.get(key):
                    self.stdout.write(f"      {label}: {med[key]}")
            if med.get("quantity") is not None:
                self.stdout.write(f"      qty: {med['quantity']}")
            self.stdout.write(f"      catalog: {link}")

        if fields.get("notes"):
            self.stdout.write("")
            self.stdout.write(f"notes: {fields['notes']}")
