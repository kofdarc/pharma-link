from __future__ import annotations

from apps.prescriptions.services.ocr.base import OcrProvider, OcrProviderError, OcrResult, UnsupportedFileType

SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# EasyOCR loads a separate recognition network per language, and only some combinations are
# compatible with each other - unlike Tesseract's eng+fra+ara, which works fine together.
# Verified empirically against the installed package: Reader(["en", "fr", "ar"]) is rejected
# outright with "Arabic is only compatible with English". So this runs two separate
# compatible readers - en+fr and en+ar - over the same image and merges their output, rather
# than silently dropping Arabic (or French) to fit a single reader's language group. Doubles
# recognition work per request (the detector network is shared/downloaded once either way);
# accepted as the cost of covering the same English/French/Arabic script mix real Lebanese
# prescriptions use (docs/AI_FEATURES.md §2) with a free, still fully self-hosted provider.
READER_LANGUAGE_SETS = (["en", "fr"], ["en", "ar"])

# PDF pages render at this DPI before OCR - matches TesseractOcrProvider's setting so the two
# providers see comparable input quality.
PDF_RENDER_DPI = 300

_readers: dict[tuple[str, ...], object] = {}


def _get_reader(languages: list[str]):
    """
    Reader construction loads the detection + recognition model weights - genuinely slow
    (seconds, plus a one-time download on first use) and memory-heavy, so each language set's
    reader is built once per process and cached, not rebuilt per request.
    """
    key = tuple(languages)
    if key not in _readers:
        import easyocr

        try:
            _readers[key] = easyocr.Reader(languages, gpu=False)
        except ValueError as exc:
            raise OcrProviderError(f"EasyOCR could not load language set {languages}: {exc}") from exc
    return _readers[key]


# Two detections are treated as the same physical text region if their bbox centers fall
# within this many pixels of each other.
REGION_MATCH_DISTANCE_PX = 20


def _bbox_center(bbox) -> tuple[float, float]:
    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _merge_reader_results(results_by_reader):
    """
    Both readers detect and transcribe every physical text region on the page - including
    English text, which neither reader is "wrong" to pick up. Naively concatenating both
    readers' output would duplicate every line, and worse, keep the losing reader's garbage:
    verified empirically that running plain English text ("PANADOL 500MG") through the en+ar
    reader produces mangled Arabic-digit output ("P٥٧A٥٥L5٥٥MIG") alongside the correct
    en+fr transcription for the same region, rather than failing loudly.

    So this matches detections across readers by approximate bbox position (the same region,
    give or take a few pixels of detector jitter) and keeps only the higher-confidence
    transcription per region - which is usually also the correctly-scripted one, since
    running text through its native language's recognizer scores higher than forcing it
    through the wrong one.
    """
    merged: list[list] = []  # each entry: [center, text, confidence]
    for results in results_by_reader:
        for bbox, text, confidence in results:
            center = _bbox_center(bbox)
            match = next((entry for entry in merged if _distance(entry[0], center) <= REGION_MATCH_DISTANCE_PX), None)
            if match is None:
                merged.append([center, text, confidence])
            elif confidence > match[2]:
                match[1], match[2] = text, confidence
    return [(text, confidence) for _center, text, confidence in merged]


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _ocr_image(image):
    import numpy as np

    array = np.array(image)
    results_by_reader = [_get_reader(languages).readtext(array) for languages in READER_LANGUAGE_SETS]
    merged = _merge_reader_results(results_by_reader)
    if not merged:
        return "", None
    lines = [text for text, _confidence in merged]
    confidences = [confidence for _text, confidence in merged]
    return "\n".join(lines), (sum(confidences) / len(confidences))


class EasyOcrProvider(OcrProvider):
    """
    Free, self-hosted alternative to TesseractOcrProvider - a real deep-learning
    detection+recognition pipeline (CRAFT + CRNN) rather than classical glyph matching, so it
    generalises better to varied fonts, lighting, and moderately messy handwriting. Still
    meaningfully behind AnthropicOcrProvider on genuine doctor handwriting - no drug-name
    world knowledge, no language-model context to disambiguate an illegible stroke - see the
    quality comparison in docs/AI_FEATURES.md §2.

    Heavier than Tesseract: pulls in PyTorch, downloads ~100s of MB of model weights on first
    use per process, and is slower per request even on CPU. Opt in via
    PRESCRIPTION_OCR_PROVIDER=easyocr; nothing here runs unless selected.
    """

    code = "easyocr"

    def extract_text(self, file, *, mime_type: str) -> OcrResult:
        if mime_type not in SUPPORTED_MIME_TYPES:
            raise UnsupportedFileType(f"EasyOCR supports JPEG/PNG/PDF files, not '{mime_type}', in this build.")

        file.seek(0)

        if mime_type == "application/pdf":
            from pdf2image import convert_from_bytes
            from pdf2image.exceptions import PDFPageCountError, PDFSyntaxError

            try:
                pages = convert_from_bytes(file.read(), dpi=PDF_RENDER_DPI)
            except (PDFPageCountError, PDFSyntaxError) as exc:
                raise OcrProviderError(f"Could not read this PDF: {exc}") from exc
            page_results = [_ocr_image(page) for page in pages]
            text = "\n\n".join(page_text for page_text, _confidence in page_results)
            confidences = [confidence for _text, confidence in page_results if confidence is not None]
        else:
            from PIL import Image

            image = Image.open(file)
            text, page_confidence = _ocr_image(image)
            confidences = [page_confidence] if page_confidence is not None else []

        overall_confidence = (sum(confidences) / len(confidences)) if confidences else None
        return OcrResult(text=text, provider=self.code, confidence=overall_confidence)
