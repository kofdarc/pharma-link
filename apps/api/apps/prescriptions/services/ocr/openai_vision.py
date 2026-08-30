from __future__ import annotations

import base64

from django.conf import settings

from apps.common.openai_chat import Endpoint, OpenAiChatError, chat_completion
from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType

REQUEST_TIMEOUT_SECONDS = 45
# Some gateways sit behind Cloudflare bot rules that 403 urllib's default
# "Python-urllib/x.y" UA outright (the same lesson apps.analytics.providers.openai_compatible
# learned against OpenCode Zen). Send one explicitly.
USER_AGENT = "PharmaLink-Prescriptions/1.0"
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
PDF_RENDER_DPI = 200

TRANSCRIBE_PROMPT = (
    "Transcribe exactly what is written on this prescription image, preserving line breaks. "
    "Output only the raw transcribed text - no summary, no interpretation, and no added "
    "dosage, drug, or medical advice beyond what is literally written on the page. If a word "
    "is illegible, write [illegible] in its place instead of guessing."
)


class OpenAiVisionOcrProvider(OcrProvider):
    """
    Vision-model transcription over any OpenAI-compatible `/chat/completions` endpoint that
    accepts image content blocks - OpenRouter, a local Ollama (`llama3.2-vision`, `qwen2-vl`),
    Groq, and friends. This is the non-Anthropic answer to handwriting: classical OCR
    (Tesseract, EasyOCR) reads print, not a doctor's scrawl, and only a real vision-language
    model has the drug-name world knowledge to disambiguate an illegible stroke.

    Inert until configured, like every other outbound adapter in this codebase: with
    PRESCRIPTION_OCR_VISION_BASE_URL / _API_KEY / _MODEL unset it raises rather than
    half-working. Prompted to transcribe only, never to interpret - this stays an OCR step,
    not a "read this prescription" request (docs/PRD.md non-goals). Sends the scan image
    (which can carry patient/doctor names) to whichever gateway is configured, so it is a
    data-handling decision, same as the Anthropic provider - just not tied to one vendor.

    stdlib urllib, no SDK - one POST of one JSON body per page.
    """

    code = "openai_vision"

    def extract_text(self, file, *, mime_type: str) -> OcrResult:
        base_url = settings.PRESCRIPTION_OCR_VISION_BASE_URL
        api_key = settings.PRESCRIPTION_OCR_VISION_API_KEY
        model = settings.PRESCRIPTION_OCR_VISION_MODEL
        if not (base_url and api_key and model):
            raise OcrProviderError(
                "PRESCRIPTION_OCR_VISION_BASE_URL, _API_KEY and _MODEL must all be set to use the openai_vision OCR provider."
            )
        timeout = getattr(settings, "PRESCRIPTION_OCR_VISION_TIMEOUT_SECONDS", REQUEST_TIMEOUT_SECONDS)

        file.seek(0)
        if mime_type == "application/pdf":
            pages = _render_pdf_pages(file.read())
            text = "\n\n".join(
                self._transcribe(page_bytes, "image/png", base_url, api_key, model, timeout) for page_bytes in pages
            )
        elif mime_type in SUPPORTED_IMAGE_MIME_TYPES:
            text = self._transcribe(file.read(), mime_type, base_url, api_key, model, timeout)
        else:
            raise UnsupportedFileType(f"openai_vision OCR supports JPEG/PNG/WebP/GIF images and PDF, not '{mime_type}'.")

        return OcrResult(text=text, provider=self.code)

    def _transcribe(self, data: bytes, mime_type: str, base_url: str, api_key: str, model: str, timeout: int) -> str:
        data_url = f"data:{mime_type};base64,{base64.standard_b64encode(data).decode('ascii')}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": TRANSCRIBE_PROMPT},
                ],
            }
        ]
        try:
            message = chat_completion(
                Endpoint(base_url, api_key, model),
                messages=messages,
                temperature=0,
                # Room for a full-page transcription plus a thinking model's internal
                # reasoning tokens (Gemini 3.x etc.) when this runs as the shared fallback.
                max_tokens=6000,
                timeout=timeout,
                user_agent=USER_AGENT,
            )
        except OpenAiChatError as exc:
            raise OcrProviderError(f"openai_vision OCR request failed: {exc}") from exc
        return message.get("content") or ""


def _render_pdf_pages(pdf_bytes: bytes) -> list[bytes]:
    try:
        from pdf2image import convert_from_bytes
        from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError
    except ImportError as exc:
        raise OcrProviderError("Reading a PDF with the openai_vision provider needs pdf2image/poppler installed.") from exc

    import io

    try:
        pages = convert_from_bytes(pdf_bytes, dpi=PDF_RENDER_DPI)
    except (PDFPageCountError, PDFSyntaxError) as exc:
        raise OcrProviderError(f"Could not read this PDF: {exc}") from exc

    rendered = []
    for page in pages:
        buffer = io.BytesIO()
        page.save(buffer, format="PNG")
        rendered.append(buffer.getvalue())
    return rendered
