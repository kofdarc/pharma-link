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

    def refund(self, payment) -> ChargeResult:
        """No gateway ever held the money. If cash was already collected at handover the
        pharmacy/driver has to hand it back manually - this only flips the record straight."""
        return ChargeResult(status=Payment.Status.REFUNDED, raw={"note": "Cash on delivery: no gateway settlement to reverse."})
