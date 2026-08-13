from apps.payments.models import Payment
from apps.payments.providers.base import ChargeResult, PaymentProvider


class CashOnDeliveryProvider(PaymentProvider):
    """
    No gateway involved: the driver or pharmacy counter collects cash at handover. The
    payment stays PENDING until the order is actually delivered/collected - see
    apps.payments.services.settle_cash_on_delivery, called from the order lifecycle.
    """

    code = Payment.Provider.CASH_ON_DELIVERY

    def charge(self, payment) -> ChargeResult:
        return ChargeResult(status=Payment.Status.PENDING)
