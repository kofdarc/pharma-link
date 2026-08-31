"""
The Claude-native twin of
:mod:`apps.prescriptions.services.ocr.vision_structured`: one vision call from prescription
image straight to structured fields, over the Anthropic Messages API rather than an
OpenAI-compatible gateway.

Both exist for the same reason the transcribe-only pair does (``anthropic`` /
``openai_vision``): the platform should not be tied to one vendor, but the Anthropic path is
the quality ceiling on genuinely bad handwriting, so it stays available for deployments that
have made that data-handling call. The prompt, the output schema, and the response bounding
are shared with ``vision_structured`` - only the transport and the JSON-forcing trick differ,
since the Messages API has no ``response_format``.

Reads PDFs natively as a ``document`` block, no pdf2image/poppler rendering step.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType
from apps.prescriptions.services.ocr.vision_structured import (
    SYSTEM_PROMPT,
    USER_PROMPT,
    _bounded,
    _loads,
    render_text,
)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
REQUEST_TIMEOUT_SECONDS = 60
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}
MAX_TOKENS = 6000


class AnthropicStructuredOcrProvider(OcrProvider):
    """
    ``PRESCRIPTION_OCR_PROVIDER="anthropic_structured"`` (+ ``ANTHROPIC_API_KEY``, model from
    ``ANTHROPIC_OCR_MODEL``). Same settings as the transcribe-only ``anthropic`` provider, so
    switching between them is a one-value change with no new keys.

    Same boundary as every other provider here (docs/PRD.md non-goals): transcribe and lay
    out, never diagnose, advise, or substitute. See the module docstring of
    ``vision_structured`` for why the single-call shape reads handwriting better than the
    two-stage pipeline.
    """

    code = "anthropic_structured"
    supports_structured = True

    def extract_structured_fields(self, file, *, mime_type: str) -> dict:
        if not settings.ANTHROPIC_API_KEY:
            raise OcrProviderError("ANTHROPIC_API_KEY must be set to use the anthropic_structured OCR provider.")
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedFileType(f"anthropic_structured OCR supports JPEG/PNG/WebP/GIF/PDF, not '{mime_type}'.")

        file.seek(0)
        file_b64 = base64.standard_b64encode(file.read()).decode("ascii")
        content_block = (
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": file_b64}}
            if mime_type == "application/pdf"
            else {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": file_b64}}
        )
        payload = json.dumps(
            {
                "model": settings.ANTHROPIC_OCR_MODEL,
                "max_tokens": MAX_TOKENS,
                "temperature": 0,
                "system": SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": [content_block, {"type": "text", "text": USER_PROMPT}]},
                    # The Messages API has no response_format, so the assistant turn is
                    # prefilled with the opening brace: the model continues the JSON object
                    # rather than wrapping it in prose or a code fence. The brace is added
                    # back before parsing, since the response omits what was prefilled.
                    {"role": "assistant", "content": "{"},
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
            raise OcrProviderError(f"anthropic_structured OCR request failed: HTTP {exc.code}: {detail}"[:500]) from exc
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise OcrProviderError(f"anthropic_structured OCR request failed: {exc}") from exc

        text = "".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
        parsed = _loads("{" + text)
        if parsed is None:
            raise OcrProviderError("anthropic_structured OCR did not return a JSON object.")
        return _bounded(parsed)

    def extract_text(self, file, *, mime_type: str) -> OcrResult:
        fields = self.extract_structured_fields(file, mime_type=mime_type)
        return OcrResult(text=render_text(fields), provider=self.code, confidence=fields.get("transcription_confidence"))
