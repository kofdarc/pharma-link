from apps.payments.providers.base import PaymentProvider
from apps.payments.providers.cash_on_delivery import CashOnDeliveryProvider
from apps.payments.providers.mock_gateway import MockGatewayProvider

_PROVIDERS: dict[str, PaymentProvider] = {
    CashOnDeliveryProvider.code: CashOnDeliveryProvider(),
    MockGatewayProvider.code: MockGatewayProvider(),
}


def get_provider(code: str) -> PaymentProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown payment provider '{code}'.") from None


def available_providers() -> list[dict]:
    from apps.payments.models import Payment

    labels = dict(Payment.Provider.choices)
    return [{"code": code, "label": labels.get(code, code)} for code in _PROVIDERS]
