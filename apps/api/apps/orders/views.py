from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin, IsShopper
from apps.eprescriptions.models import Prescription
from apps.medicines.models import Medicine
from apps.orders.models import DeliveryAddress, Order, OrderFulfillment, PharmacyReview, RecurringOrder
from apps.orders.serializers import (
    BasketQuoteSerializer,
    DeliveryAddressSerializer,
    HandoverSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    PharmacyOrderFulfillmentSerializer,
    PharmacyReviewSerializer,
    RecurringOrderSerializer,
    RejectFulfillmentSerializer,
)
from apps.orders.services.lifecycle import (
    FulfillmentError,
    accept_fulfillment,
    cancel_order,
    hand_over,
    mark_ready,
    reject_fulfillment,
    set_review_visibility,
    submit_review,
)
from apps.orders.services.placement import OrderError, place_order
from apps.orders.services.sourcing import plan_basket
from apps.pharmacies.models import Pharmacy


class DeliveryAddressViewSet(ModelViewSet):
    serializer_class = DeliveryAddressSerializer
    permission_classes = [IsShopper]

    def get_queryset(self):
        return DeliveryAddress.objects.filter(user=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        address = serializer.save(user=self.request.user)
        if address.is_default or self.get_queryset().count() == 1:
            DeliveryAddress.objects.filter(user=self.request.user).exclude(id=address.id).update(is_default=False)
            if not address.is_default:
                address.is_default = True
                address.save(update_fields=["is_default", "updated_at"])


class BasketQuoteView(APIView):
    """
    Shows the shopper exactly how their basket would be sourced BEFORE they commit, including
    how many pharmacies are involved and why. No stock is held by a quote.
    """

    permission_classes = [IsShopper]

    def post(self, request):
        serializer = BasketQuoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan = plan_basket(
            items=[{"medicine": str(entry["medicine"]), "quantity": entry["quantity"]} for entry in data["items"]],
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            radius_km=data.get("radius_km"),
        )
        return Response(plan)


class ShopperOrderViewSet(ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsShopper]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            Order.objects.filter(customer=self.request.user)
            .prefetch_related("fulfillments__lines__medicine", "fulfillments__pharmacy")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        if not request.user.email_verified:
            return Response({"detail": _("Verify your email before placing an order.")}, status=status.HTTP_403_FORBIDDEN)
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        address = None
        if data.get("address"):
            address = DeliveryAddress.objects.filter(id=data["address"], user=request.user).first()
            if address is None:
                return Response({"detail": _("Address not found.")}, status=status.HTTP_400_BAD_REQUEST)
        elif data["fulfillment_type"] == Order.FulfillmentType.DELIVERY:
            address = DeliveryAddress.objects.filter(user=request.user, is_default=True).first()

        prescription = None
        if data.get("prescription_code"):
            prescription = Prescription.objects.filter(code=data["prescription_code"].strip().upper()).first()

        idempotency_key = request.headers.get("Idempotency-Key", "")[:120]

        try:
            order = place_order(
                customer=request.user,
                items=[{"medicine": str(entry["medicine"]), "quantity": entry["quantity"]} for entry in data["items"]],
                address=address,
                fulfillment_type=data["fulfillment_type"],
                scheduled_for=data.get("scheduled_for"),
                window_minutes=data.get("window_minutes", 120),
                notes=data.get("notes", ""),
                prescription=prescription,
                payment_method=data["payment_method"],
                idempotency_key=idempotency_key,
            )
        except OrderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            # Lost the race against an identical concurrent request; the winner's order is
            # the correct response either way.
            order = Order.objects.filter(customer=request.user, idempotency_key=idempotency_key).first()
            if order is None:
                raise
            return Response(self.get_serializer(order).data, status=status.HTTP_200_OK)
        return Response(self.get_serializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            order = cancel_order(order=self.get_object(), user=request.user, reason=request.data.get("reason", ""))
        except FulfillmentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        order = self.get_object()
        serializer = PharmacyReviewSerializer(data={**request.data, "order": order.id})
        serializer.is_valid(raise_exception=True)
        pharmacy = Pharmacy.objects.filter(id=serializer.validated_data["pharmacy"].id).first()
        try:
            review = submit_review(
                order=order,
                pharmacy=pharmacy,
                customer=request.user,
                rating=serializer.validated_data["rating"],
                comment=serializer.validated_data.get("comment", ""),
                was_complete=serializer.validated_data.get("was_complete", True),
            )
        except FulfillmentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PharmacyReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class RecurringOrderViewSet(ModelViewSet):
    serializer_class = RecurringOrderSerializer
    permission_classes = [IsShopper]

    def get_queryset(self):
        return RecurringOrder.objects.filter(customer=self.request.user)

    def perform_create(self, serializer):
        address = serializer.validated_data["address"]
        if address.user_id != self.request.user.id:
            raise FulfillmentError(_("That address belongs to another account."))

        prescription = None
        prescription_code = serializer.validated_data.pop("prescription_code", "")
        if prescription_code:
            prescription = Prescription.objects.filter(code=prescription_code.strip().upper()).first()
            if prescription is None:
                raise FulfillmentError(_("No prescription was found with that code."))

        needs_prescription = Medicine.objects.filter(
            id__in=[entry["medicine"] for entry in serializer.validated_data["items"]], requires_prescription=True
        ).exists()
        if needs_prescription and (prescription is None or not prescription.is_consumable):
            raise FulfillmentError(_("A valid prescription code is required to repeat an order containing prescription items."))

        next_run = serializer.validated_data.get("next_run_at") or timezone.now() + timedelta(days=serializer.validated_data.get("interval_days", 30))
        serializer.save(customer=self.request.user, next_run_at=next_run, prescription=prescription)


class PharmacyOrderViewSet(ReadOnlyModelViewSet):
    """The pharmacy's queue of incoming platform orders."""

    serializer_class = PharmacyOrderFulfillmentSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        qs = (
            OrderFulfillment.objects.filter(pharmacy=self.request.user.pharmacy)
            .select_related("order", "pharmacy")
            .prefetch_related("lines__medicine")
        )
        state = self.request.query_params.get("status")
        if state:
            qs = qs.filter(status=state)
        if self.request.query_params.get("open") == "true":
            qs = qs.filter(status__in=[OrderFulfillment.Status.PENDING, OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY])
        return qs.order_by("-created_at")

    def _run(self, operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs), None
        except FulfillmentError as exc:
            return None, Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return None, Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        result, error = self._run(accept_fulfillment, fulfillment=self.get_object(), user=request.user)
        return error or Response(self.get_serializer(result).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = RejectFulfillmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, error = self._run(reject_fulfillment, fulfillment=self.get_object(), user=request.user, reason=serializer.validated_data.get("reason", ""))
        return error or Response(self.get_serializer(result).data)

    @action(detail=True, methods=["post"], url_path="ready")
    def ready(self, request, pk=None):
        result, error = self._run(mark_ready, fulfillment=self.get_object(), user=request.user)
        return error or Response(self.get_serializer(result).data)

    @action(detail=True, methods=["post"])
    def handover(self, request, pk=None):
        serializer = HandoverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result, error = self._run(
            hand_over,
            fulfillment=self.get_object(),
            user=request.user,
            handover_code=serializer.validated_data.get("handover_code", ""),
            collected_in_store=serializer.validated_data.get("collected_in_store", False),
        )
        return error or Response(self.get_serializer(result).data)


class AdminReviewViewSet(ReadOnlyModelViewSet):
    """Lets a platform admin moderate reviews that are abusive or off-topic."""

    serializer_class = PharmacyReviewSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = PharmacyReview.objects.select_related("order", "pharmacy", "customer").order_by("-created_at")

    @action(detail=True, methods=["post"])
    def hide(self, request, pk=None):
        review = set_review_visibility(review=self.get_object(), is_hidden=True, reason=request.data.get("reason", ""), user=request.user)
        return Response(self.get_serializer(review).data)

    @action(detail=True, methods=["post"])
    def unhide(self, request, pk=None):
        review = set_review_visibility(review=self.get_object(), is_hidden=False, user=request.user)
        return Response(self.get_serializer(review).data)
