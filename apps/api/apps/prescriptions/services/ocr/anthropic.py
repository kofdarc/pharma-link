from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 30
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

TRANSCRIBE_PROMPT = (
    "Transcribe exactly what is written on this prescription image, preserving line breaks. "
    "Output only the raw transcribed text - no summary, no interpretation, and no added "
    "dosage, drug, or medical advice beyond what is literally written on the page. If a word "
    "is illegible, write [illegible] in its place instead of guessing."
)


class AnthropicOcrProvider(OcrProvider):
    """
    Real vision-model transcription via the Claude API. Reads handwriting far better than
    Tesseract, since it's a genuine vision model rather than glyph-template matching - at the
    cost of a per-request API call and sending the prescription image (which can carry
    patient/doctor names) to Anthropic. Only reachable once PRESCRIPTION_OCR_PROVIDER is
    switched to "anthropic" with ANTHROPIC_API_KEY set (see config/settings.py); both are
    blank/default off, same inert-until-configured pattern as MetaCloudWhatsAppProvider.

    Uses urllib (stdlib) rather than adding the `anthropic` SDK as a dependency, matching the
    existing outbound-HTTP precedent in apps.messaging.providers.meta_cloud.

    Deliberately prompted to transcribe only, not interpret - this stays an OCR step, not a
    request for the model to read or judge the prescription (see docs/PRD.md non-goals: no
    diagnosis, no treatment advice, no substitution recommendations).
    """

    code = "anthropic"

    def extract_text(self, file, *, mime_type: str) -> OcrResult:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedFileType(f"Anthropic OCR supports JPEG/PNG/PDF files, not '{mime_type}'.")

        file.seek(0)
        file_b64 = base64.standard_b64encode(file.read()).decode("ascii")
        # PDF reads through the "document" block type - Claude reads PDFs natively, no
        # separate rendering step (unlike TesseractOcrProvider, which needs pdf2image).
        content_block = (
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": file_b64}}
            if mime_type == "application/pdf"
            else {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": file_b64}}
        )
        payload = json.dumps(
            {
                "model": settings.ANTHROPIC_OCR_MODEL,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            content_block,
                            {"type": "text", "text": TRANSCRIBE_PROMPT},
                        ],
                    }
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OcrProviderError(f"Anthropic OCR request failed: HTTP {exc.code}: {detail}"[:500]) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise OcrProviderError(f"Anthropic OCR request failed: {exc}") from exc

        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return OcrResult(text=text, provider=self.code)
