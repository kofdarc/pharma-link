from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.analytics.services import insights, kpis, narrative


def _int_param(request, name: str, default: int, *, maximum: int = 365) -> int:
    try:
        return max(1, min(maximum, int(request.query_params.get(name, default))))
    except (TypeError, ValueError):
        return default


class AnalyticsOverviewView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        return Response(kpis.overview(request.user.pharmacy))


class AnalyticsInventoryView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        pharmacy = request.user.pharmacy
        days = _int_param(request, "days", 90)
        return Response(
            {
                "stock": kpis.stock_snapshot(pharmacy),
                "turnover": kpis.turnover_metrics(pharmacy, days=days),
                "movement": kpis.movement_classification(pharmacy, days=days),
            }
        )


class AnalyticsSalesView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        pharmacy = request.user.pharmacy
        days = _int_param(request, "days", 30)
        return Response(
            {
                "sales": kpis.sales_snapshot(pharmacy, days=days),
                "series": kpis.revenue_timeseries(pharmacy, days=days),
                "movement": kpis.movement_classification(pharmacy, days=days, limit=15),
            }
        )


class AnalyticsReplenishmentView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        return Response(
            kpis.replenishment_plan(
                request.user.pharmacy,
                days=_int_param(request, "days", 60),
                lead_time_days=_int_param(request, "lead_time_days", kpis.DEFAULT_LEAD_TIME_DAYS, maximum=60),
            )
        )


class AnalyticsDemandView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        return Response(kpis.demand_signals(request.user.pharmacy, days=_int_param(request, "days", 30)))


class AnalyticsInsightsView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        return Response({"insights": insights.generate_insights(request.user.pharmacy)})


class AnalyticsDigestThrottle(UserRateThrottle):
    scope = "analytics_digest"


class AnalyticsDigestView(APIView):
    """
    Narrative prose over the same numbers AnalyticsInsightsView already returns - see
    apps.analytics.services.narrative. Unlike every other view in this module, this one can
    call an external provider, hence the dedicated throttle: the rest are pure DB reads with
    no per-request cost.
    """

    permission_classes = [IsPharmacyUserWithActivePharmacy]
    throttle_classes = [AnalyticsDigestThrottle]

    def get(self, request):
        return Response(narrative.generate_digest(request.user.pharmacy, locale=request.LANGUAGE_CODE))
