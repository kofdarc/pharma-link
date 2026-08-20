from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.billing.models import PharmacySubscription, PlatformServiceFee, SubscriptionPlan
from apps.billing.serializers import PharmacySubscriptionSerializer, PlatformServiceFeeSerializer, SubscriptionPlanSerializer
from apps.billing.services import mark_service_fee_paid


class AdminSubscriptionPlanViewSet(ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsPlatformAdmin]


class AdminPharmacySubscriptionViewSet(ModelViewSet):
    queryset = PharmacySubscription.objects.select_related("pharmacy", "plan").order_by("pharmacy__name")
    serializer_class = PharmacySubscriptionSerializer
    permission_classes = [IsPlatformAdmin]


class PharmacySubscriptionView(APIView):
    """What a pharmacy sees about its own plan. Admins manage the assignment."""

    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        subscription = getattr(request.user.pharmacy, "subscription", None)
        if subscription is None:
            return Response({"detail": "No subscription on file."}, status=status.HTTP_404_NOT_FOUND)
        return Response(PharmacySubscriptionSerializer(subscription).data)


class PharmacyServiceFeeViewSet(ReadOnlyModelViewSet):
    serializer_class = PlatformServiceFeeSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return PlatformServiceFee.objects.filter(pharmacy=self.request.user.pharmacy).select_related("fulfillment__order")


class AdminServiceFeeViewSet(ReadOnlyModelViewSet):
    serializer_class = PlatformServiceFeeSerializer
    permission_classes = [IsPlatformAdmin]
    queryset = PlatformServiceFee.objects.select_related("pharmacy", "fulfillment__order").order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        try:
            fee = mark_service_fee_paid(fee=self.get_object(), user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(fee).data)


class PlatformRevenueOverviewView(APIView):
    """
    The KPIs-beyond-uptime the mentors flagged as missing: recurring subscription revenue,
    active subscriber count, and service fees collected from platform order requests.
    """

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        active_subs = PharmacySubscription.objects.filter(status=PharmacySubscription.Status.ACTIVE).select_related("plan")
        mrr = sum((sub.plan.monthly_fee for sub in active_subs), Decimal("0"))
        fees = PlatformServiceFee.objects.aggregate(
            collected=Sum("amount", filter=Q(status=PlatformServiceFee.Status.PAID)),
            pending=Sum("amount", filter=Q(status=PlatformServiceFee.Status.PENDING)),
            count=Count("id"),
        )
        return Response(
            {
                "active_subscriptions": active_subs.count(),
                "monthly_recurring_revenue": str(mrr),
                "service_fees_collected": str(fees["collected"] or Decimal("0")),
                "service_fees_pending": str(fees["pending"] or Decimal("0")),
                "service_fee_requests": fees["count"] or 0,
            }
        )
