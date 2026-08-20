from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformAdmin, IsShopper
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.providers.registry import available_providers
from apps.payments.serializers import PaymentSerializer
from apps.payments.services import charge_payment, refund_payment


class PaymentMethodsView(APIView):
    """Lets checkout render available payment methods instead of hardcoding provider codes."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(available_providers())


class OrderPaymentView(APIView):
    """
    Confirms/retries a gateway charge for the shopper's own order. Cash-on-delivery orders
    settle automatically at handover (see apps.payments.services.settle_cash_on_delivery)
    and never need this endpoint.
    """

    permission_classes = [IsShopper]

    def post(self, request, pk=None):
        order = Order.objects.filter(id=pk, customer=request.user).first()
        if order is None:
            return Response({"detail": _("Order not found.")}, status=status.HTTP_404_NOT_FOUND)
        payment = getattr(order, "payment", None)
        if payment is None:
            return Response({"detail": _("This order has no payment on file.")}, status=status.HTTP_400_BAD_REQUEST)
        if payment.provider == Payment.Provider.CASH_ON_DELIVERY:
            return Response({"detail": _("Cash on delivery settles at handover, not online.")}, status=status.HTTP_400_BAD_REQUEST)
        payment = charge_payment(payment=payment, user=request.user)
        return Response(PaymentSerializer(payment).data)


class AdminOrderRefundView(APIView):
    """Support-initiated refund outside a full order cancellation (e.g. a goodwill credit)."""

    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk=None):
        order = Order.objects.filter(id=pk).first()
        if order is None:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        payment = getattr(order, "payment", None)
        if payment is None:
            return Response({"detail": "This order has no payment on file."}, status=status.HTTP_400_BAD_REQUEST)
        if payment.status != Payment.Status.PAID:
            return Response({"detail": f"Only a paid payment can be refunded (currently {payment.status})."}, status=status.HTTP_400_BAD_REQUEST)
        payment = refund_payment(payment=payment, user=request.user)
        return Response(PaymentSerializer(payment).data)
