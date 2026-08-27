from apps.prescriptions.services.ocr.anthropic import AnthropicOcrProvider
from apps.prescriptions.services.ocr.base import OcrProvider
from apps.prescriptions.services.ocr.easyocr_provider import EasyOcrProvider
from apps.prescriptions.services.ocr.tesseract import TesseractOcrProvider

_PROVIDERS: dict[str, OcrProvider] = {
    TesseractOcrProvider.code: TesseractOcrProvider(),
    EasyOcrProvider.code: EasyOcrProvider(),
    AnthropicOcrProvider.code: AnthropicOcrProvider(),
}


def get_provider(code: str) -> OcrProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown OCR provider '{code}'.") from None
