import secrets

from apps.payments.models import Payment
from apps.payments.providers.base import ChargeResult, PaymentProvider


class MockGatewayProvider(PaymentProvider):
    """
    Stands in for a real Lebanese payment gateway that hasn't been chosen yet, so checkout
    can demo a full "pay online" flow without an account or a redirect. Charges succeed
    instantly with a fake reference. Swap this class out once a provider is picked; nothing
    else in checkout needs to change.
    """

    code = Payment.Provider.MOCK_GATEWAY

    def charge(self, payment) -> ChargeResult:
        return ChargeResult(
            status=Payment.Status.PAID,
            external_reference=f"MOCK-{secrets.token_hex(6).upper()}",
            raw={"simulated": True},
        )
