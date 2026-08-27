from __future__ import annotations

from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType

SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# eng+fra+ara covers the scripts Lebanese prescriptions are actually written in - the
# default was English-only, which silently produced garbage on French or Arabic pages
# rather than an error (see docs/AI_FEATURES.md §2). Requires the tesseract-ocr-fra and
# tesseract-ocr-ara system packages (installed in the Dockerfile); a dev machine without
# them still works, tesseract just falls back to whichever of the three it has.
TESSERACT_LANGUAGES = "eng+fra+ara"

# PDF pages render at this DPI before OCR - high enough for a phone-photo-quality scan
# without producing an unreasonably large image.
PDF_RENDER_DPI = 300


def _preprocess(image):
    """Grayscale + autocontrast - these are phone photos of paper on a counter, and
    Tesseract's accuracy is sensitive to lighting/contrast in a way a real vision model
    isn't. Cheap, deterministic, no model involved."""
    from PIL import ImageOps

    return ImageOps.autocontrast(image.convert("L"))


def _ocr_image(image, lang: str):
    import pytesseract
    from pytesseract import Output

    processed = _preprocess(image)
    text = pytesseract.image_to_string(processed, lang=lang)
    data = pytesseract.image_to_data(processed, lang=lang, output_type=Output.DICT)
    word_confidences = [int(conf) for conf in data.get("conf", []) if str(conf).lstrip("-").isdigit() and int(conf) >= 0]
    confidence = (sum(word_confidences) / len(word_confidences) / 100) if word_confidences else None
    return text, confidence


class TesseractOcrProvider(OcrProvider):
    """
    Default (see settings.PRESCRIPTION_OCR_PROVIDER): self-hosted, open-source, needs no
    external account or API key. Reads printed prescriptions reasonably well; doctor
    handwriting is a known weak spot (docs/AI_FEATURES.md §2) - AnthropicOcrProvider exists
    for that case. Handles JPG/PNG images and PDFs (rendered page-by-page via pdf2image,
    which needs the poppler-utils system package - installed in the Dockerfile).
    """

    code = "tesseract"

    def extract_text(self, file, *, mime_type: str) -> OcrResult:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedFileType(f"Tesseract OCR supports JPEG/PNG/PDF files, not '{mime_type}', in this build.")

        file.seek(0)

        if mime_type == "application/pdf":
            from pdf2image import convert_from_bytes
            from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError

            try:
                pages = convert_from_bytes(file.read(), dpi=PDF_RENDER_DPI)
            except (PDFPageCountError, PDFSyntaxError) as exc:
                raise OcrProviderError(f"Could not read this PDF: {exc}") from exc
            page_results = [_ocr_image(page, TESSERACT_LANGUAGES) for page in pages]
            text = "\n\n".join(page_text for page_text, _confidence in page_results)
            confidences = [confidence for _text, confidence in page_results if confidence is not None]
        else:
            from PIL import Image

            image = Image.open(file)
            text, page_confidence = _ocr_image(image, TESSERACT_LANGUAGES)
            confidences = [page_confidence] if page_confidence is not None else []

        overall_confidence = (sum(confidences) / len(confidences)) if confidences else None
        return OcrResult(text=text, provider=self.code, confidence=overall_confidence)
