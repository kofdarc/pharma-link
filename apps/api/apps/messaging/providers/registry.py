from apps.messaging.providers.base import WhatsAppProvider
from apps.messaging.providers.console import ConsoleWhatsAppProvider
from apps.messaging.providers.meta_cloud import MetaCloudWhatsAppProvider

_PROVIDERS: dict[str, WhatsAppProvider] = {
    ConsoleWhatsAppProvider.code: ConsoleWhatsAppProvider(),
    MetaCloudWhatsAppProvider.code: MetaCloudWhatsAppProvider(),
}


def get_provider(code: str) -> WhatsAppProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown WhatsApp provider '{code}'.") from None
