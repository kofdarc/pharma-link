from django.conf import settings

from apps.prescriptions.services.nlp.base import StructuredExtractor
from apps.prescriptions.services.nlp.openai_compatible import OpenAiCompatibleExtractor
from apps.prescriptions.services.nlp.regex_extractor import RegexExtractor


def get_extractor(code: str) -> StructuredExtractor:
    """
    RegexExtractor is a module-level singleton (stateless, no config). The
    openai_compatible extractor is built fresh from settings.PRESCRIPTION_NLP_* per call,
    like apps.analytics.providers.registry - so a settings change takes effect without a
    process restart and nothing holds a stale key.
    """
    if code == RegexExtractor.code:
        return RegexExtractor()
    if code == OpenAiCompatibleExtractor.code:
        return OpenAiCompatibleExtractor(
            base_url=settings.PRESCRIPTION_NLP_BASE_URL,
            api_key=settings.PRESCRIPTION_NLP_API_KEY,
            model=settings.PRESCRIPTION_NLP_MODEL,
            timeout_seconds=settings.PRESCRIPTION_NLP_TIMEOUT_SECONDS,
        )
    raise ValueError(f"Unknown prescription NLP extractor '{code}'.")
