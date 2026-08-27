from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPlatformAdmin, IsShopper
from apps.orders.models import Order
from apps.payments.models import Payment, SavedPaymentMethod
from apps.payments.providers.registry import available_providers
from apps.payments.serializers import PaymentSerializer, SavedPaymentMethodSerializer
from apps.payments.services import charge_payment, refund_payment


class PaymentMethodsView(APIView):
    """Lets checkout render available payment methods instead of hardcoding provider codes."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(available_providers())


class SavedPaymentMethodViewSet(ModelViewSet):
    """
    The shopper's own saved ways to pay.

    Distinct from PaymentMethodsView above, which lists the *providers* the
    platform supports. This is what a particular person has chosen to keep.
    """

    serializer_class = SavedPaymentMethodSerializer
    permission_classes = [IsShopper]

    def get_queryset(self):
        return SavedPaymentMethod.objects.filter(user=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        # Cleared before the insert, not after: the unique constraint rejects a
        # second default outright rather than letting one briefly exist.
        wants_default = serializer.validated_data.get("is_default", False) or not self.get_queryset().exists()
        if wants_default:
            self.get_queryset().update(is_default=False)
        # The first method saved is the default whether or not it was asked for:
        # an account with methods but no default has nothing to pre-select.
        serializer.save(user=self.request.user, is_default=wants_default)

    @transaction.atomic
    def perform_update(self, serializer):
        if serializer.validated_data.get("is_default", False):
            self.get_queryset().exclude(id=serializer.instance.id).update(is_default=False)
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        was_default = instance.is_default
        instance.delete()
        remaining = self.get_queryset().first()
        # Never leave the account with methods but nothing to pay with by default.
        if was_default and remaining is not None:
            remaining.is_default = True
            remaining.save(update_fields=["is_default", "updated_at"])


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
