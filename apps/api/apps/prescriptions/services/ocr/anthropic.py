from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
# Adaptive thinking on a doctor's scrawl genuinely uses the wall clock - the model reasons
# stroke by stroke against real drug names before it commits - so this is well above the 30s
# a plain transcription needed.
REQUEST_TIMEOUT_SECONDS = 120
# Room for a full multi-drug page of transcription plus the model's (unbilled-to-us-here but
# still counted) adaptive reasoning tokens. 1024 truncated real prescriptions mid-page.
MAX_TOKENS = 8000
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# Written for handwriting, not print. The three things that move accuracy on a real Lebanese
# script: tell the model what it's looking at (so "Augmentin" beats "Avgmentin"), let it lean
# on pharmaceutical knowledge to resolve an unclear stroke *toward a drug that exists*, and
# hard-stop it from inventing a line, a dose, or a direction that isn't on the page. Resolving
# which real word a scrawl spells is still transcription - it is not reading, judging, or
# advising on the prescription (docs/PRD.md non-goals: no diagnosis, no treatment advice, no
# substitution).
TRANSCRIBE_PROMPT = (
    "You are transcribing a photographed or scanned medical prescription from Lebanon. It is "
    "often handwritten by a physician and may mix English, French, and Arabic on the same "
    "page.\n\n"
    "Transcribe every line exactly as written, preserving the original line breaks and "
    "reading order. Where a stroke is unclear, you may use knowledge of real medication "
    "names, standard strengths (mg/mcg/g/ml/IU), and posology abbreviations (e.g. cp, gel, "
    "1x3, BID, matin/soir) to choose the most likely reading - but only among words that "
    "actually appear on the page.\n\n"
    "Do not add a medication, dose, route, frequency, or instruction that is not written "
    "there. Do not summarise, translate, or comment. If a token is genuinely unreadable, "
    "write [illegible] in its place rather than guessing. Output only the transcription."
)


class AnthropicOcrProvider(OcrProvider):
    """
    Real vision-model transcription via the Claude API - the handwriting path. A doctor's
    scrawl is where classical OCR (Tesseract, EasyOCR) falls apart: they match glyphs and
    have no idea "Augmentin" is a word. This provider runs a frontier vision model with
    adaptive thinking, so it reasons about an ambiguous stroke against real drug-name and
    dosage knowledge before committing - which is the whole game on messy handwriting.

    Costs a per-request API call and sends the prescription image (which can carry
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
                "max_tokens": MAX_TOKENS,
                # Adaptive thinking + high effort: let the model deliberate over unclear
                # strokes instead of first-passing them. This is the single biggest lever
                # for handwriting accuracy, and it needs no beta header on current models.
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"},
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

        # A safety decline comes back HTTP 200 with stop_reason "refusal" and no usable text -
        # surface it as a provider error so the caller degrades to the deterministic path
        # rather than storing an empty transcription.
        if data.get("stop_reason") == "refusal":
            raise OcrProviderError("Anthropic OCR request was declined by a safety filter.")

        # Skip thinking blocks; keep only the visible transcription text.
        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        return OcrResult(text=text.strip(), provider=self.code)
