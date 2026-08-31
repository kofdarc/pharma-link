from apps.prescriptions.services.ocr.anthropic import AnthropicOcrProvider
from apps.prescriptions.services.ocr.anthropic_structured import AnthropicStructuredOcrProvider
from apps.prescriptions.services.ocr.base import OcrProvider
from apps.prescriptions.services.ocr.easyocr_provider import EasyOcrProvider
from apps.prescriptions.services.ocr.openai_vision import OpenAiVisionOcrProvider
from apps.prescriptions.services.ocr.tesseract import TesseractOcrProvider
from apps.prescriptions.services.ocr.vision_structured import VisionStructuredOcrProvider

_PROVIDERS: dict[str, OcrProvider] = {
    TesseractOcrProvider.code: TesseractOcrProvider(),
    EasyOcrProvider.code: EasyOcrProvider(),
    AnthropicOcrProvider.code: AnthropicOcrProvider(),
    OpenAiVisionOcrProvider.code: OpenAiVisionOcrProvider(),
    # Single-call image -> structured fields (supports_structured). Better on handwriting
    # than any transcribe-only provider above, because the page context that makes a scrawl
    # readable is still there when the fields are filled in.
    VisionStructuredOcrProvider.code: VisionStructuredOcrProvider(),
    AnthropicStructuredOcrProvider.code: AnthropicStructuredOcrProvider(),
}


def get_provider(code: str) -> OcrProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown OCR provider '{code}'.") from None
