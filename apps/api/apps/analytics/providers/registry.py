from apps.analytics.providers.base import AssistantProvider
from apps.analytics.providers.null import NullAssistantProvider
from apps.analytics.providers.openai_compatible import OpenAiCompatibleProvider


def get_provider(code: str, *, base_url: str = "", api_key: str = "", model: str = "") -> AssistantProvider:
    """
    Unlike apps.prescriptions.services.ocr.registry / apps.messaging.providers.registry, this
    isn't a dict of module-level singletons - settings.ANALYTICS_AI_* is read once by the
    caller (apps.analytics.services.narrative) and passed straight through, so the instance is
    built fresh per call rather than looked up.
    """
    if code == NullAssistantProvider.code:
        return NullAssistantProvider()
    if code == OpenAiCompatibleProvider.code:
        if not (base_url and api_key and model):
            raise ValueError(
                f"Provider '{code}' needs base_url, api_key and model all set - got "
                f"base_url={base_url!r}, api_key={'<set>' if api_key else ''!r}, model={model!r}."
            )
        return OpenAiCompatibleProvider(base_url=base_url, api_key=api_key, model=model)
    raise ValueError(f"Unknown assistant provider '{code}'.")
