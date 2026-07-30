from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsActiveDriver, IsPlatformAdmin
from apps.delivery.models import DeliveryRoute, Driver, RouteStop
from apps.delivery.serializers import (
    DeliveryRouteSerializer,
    DriverSerializer,
    DropoffCompletionSerializer,
    FailStopSerializer,
    PickupCompletionSerializer,
    PingSerializer,
    RouteEventSerializer,
)
from apps.delivery.services.dispatch import build_jobs, build_vehicles, marginal_cost_for_driver, plan_and_persist, reoptimise_remaining
from apps.delivery.services.operations import (
    OperationError,
    accept_route,
    arrive_at_stop,
    complete_dropoff,
    complete_pickup,
    fail_stop,
    record_ping,
)
from apps.delivery.services.routing import summarise
from apps.orders.models import Order

ROUTE_PREFETCH = ("stops__tasks__order_fulfillment__lines__medicine", "stops__tasks__order_fulfillment__pharmacy", "stops__tasks__order_fulfillment__order")


class AdminDriverViewSet(ModelViewSet):
    queryset = Driver.objects.select_related("user").all()
    serializer_class = DriverSerializer
    permission_classes = [IsPlatformAdmin]


class DispatchBoardView(APIView):
    """Operations view: what is waiting, who is online, and what the plan would look like."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        jobs, _context = build_jobs()
        vehicles, _lookup = build_vehicles()
        routes = (
            DeliveryRoute.objects.exclude(status=DeliveryRoute.Status.CANCELLED)
            .select_related("driver")
            .prefetch_related(*ROUTE_PREFETCH)
            .order_by("-created_at")[:20]
        )
        return Response(
            {
                "pending_jobs": len(jobs),
                "drivers_online": len(vehicles),
                "routes": DeliveryRouteSerializer(routes, many=True).data,
                "totals": {
                    "planned_km": sum(float(route.planned_distance_km) for route in routes if route.status != DeliveryRoute.Status.COMPLETED),
                    "naive_km": sum(float(route.naive_distance_km) for route in routes if route.status != DeliveryRoute.Status.COMPLETED),
                },
            }
        )


class DispatchPlanView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        return Response(plan_and_persist(user=request.user))


class DispatchPreviewView(APIView):
    """
    Dry run: same solver, nothing written. Handy to demonstrate the saving against the
    naive one-trip-per-order baseline without committing routes.
    """

    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        from apps.delivery.services import routing

        jobs, _context = build_jobs()
        vehicles, _lookup = build_vehicles()
        if not jobs or not vehicles:
            return Response({"detail": "Need at least one dispatchable order and one online driver.", "summary": None})
        plan = routing.solve(jobs, vehicles)
        return Response(
            {
                "summary": summarise(plan, jobs, vehicles),
                "routes": [
                    {
                        "driver": route.vehicle.vehicle_id,
                        "distance_km": round(route.distance_km(), 2),
                        "orders": sorted(route.job_ids),
                        "stops": [
                            {
                                "kind": stop.kind,
                                "location": stop.location.key,
                                "orders_served": len(stop.job_units),
                                "units": stop.units,
                                "arrival_minute": round(stop.arrival_minute, 1),
                            }
                            for stop in route.stops
                        ],
                    }
                    for route in plan.routes
                    if route.stops
                ],
                "unassigned": [job.job_id for job in plan.unassigned],
            }
        )


class OrderOfferView(APIView):
    """Marginal cost of one order for every online driver: the basis of the offer flow."""

    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk):
        order = Order.objects.filter(id=pk).first()
        if order is None:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        offers = []
        for driver in Driver.objects.filter(is_active=True, is_online=True):
            offer = marginal_cost_for_driver(driver=driver, order=order)
            if offer:
                offers.append(offer)
        offers.sort(key=lambda entry: entry["marginal_distance_km"])
        return Response({"order": order.reference, "offers": offers})


class RouteReoptimiseView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        route = DeliveryRoute.objects.filter(id=pk).first()
        if route is None:
            return Response({"detail": "Route not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(reoptimise_remaining(route=route, user=request.user))


class DriverRouteViewSet(ReadOnlyModelViewSet):
    """The driver's console: their own routes only."""

    serializer_class = DeliveryRouteSerializer
    permission_classes = [IsActiveDriver]

    def get_queryset(self):
        return (
            DeliveryRoute.objects.filter(driver=self.request.user.driver_profile)
            .prefetch_related(*ROUTE_PREFETCH)
            .order_by("-created_at")
        )

    def _driver(self):
        return self.request.user.driver_profile

    def _handle(self, operation, **kwargs):
        try:
            return operation(**kwargs), None
        except OperationError as exc:
            return None, Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return None, Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def current(self, request):
        route = self.get_queryset().filter(status__in=[DeliveryRoute.Status.ACTIVE, DeliveryRoute.Status.OFFERED, DeliveryRoute.Status.PROPOSED]).first()
        if route is None:
            return Response({"route": None, "detail": "No route assigned yet."})
        return Response({"route": self.get_serializer(route).data})

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        result, error = self._handle(accept_route, route=self.get_object(), driver=self._driver())
        return error or Response(self.get_serializer(result).data)

    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        return Response(RouteEventSerializer(self.get_object().events.all()[:50], many=True).data)

    @action(detail=True, methods=["post"], url_path="reoptimise")
    def reoptimise(self, request, pk=None):
        return Response(reoptimise_remaining(route=self.get_object(), user=request.user))


class DriverStopActionView(APIView):
    permission_classes = [IsActiveDriver]

    def _stop(self, request, pk):
        return RouteStop.objects.filter(id=pk, route__driver=request.user.driver_profile).select_related("route").first()

    def post(self, request, pk, verb):
        stop = self._stop(request, pk)
        if stop is None:
            return Response({"detail": "Stop not found."}, status=status.HTTP_404_NOT_FOUND)
        driver = request.user.driver_profile
        try:
            if verb == "arrive":
                stop = arrive_at_stop(stop=stop, driver=driver)
            elif verb == "pickup":
                serializer = PickupCompletionSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                stop = complete_pickup(stop=stop, driver=driver, handover_codes=serializer.validated_data.get("handover_codes", {}))
            elif verb == "deliver":
                serializer = DropoffCompletionSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                stop = complete_dropoff(stop=stop, driver=driver, recipient_note=serializer.validated_data.get("recipient_note", ""))
            elif verb == "fail":
                serializer = FailStopSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                stop = fail_stop(stop=stop, driver=driver, reason=serializer.validated_data["reason"])
            else:
                return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
        except OperationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        from apps.delivery.serializers import RouteStopSerializer

        return Response(RouteStopSerializer(stop).data)


class DriverSelfView(APIView):
    permission_classes = [IsActiveDriver]

    def get(self, request):
        return Response(DriverSerializer(request.user.driver_profile).data)

    def patch(self, request):
        driver = request.user.driver_profile
        if "is_online" in request.data:
            driver.is_online = bool(request.data["is_online"])
            driver.save(update_fields=["is_online", "updated_at"])
        return Response(DriverSerializer(driver).data)


class DriverPingView(APIView):
    permission_classes = [IsActiveDriver]

    def post(self, request):
        serializer = PingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver = record_ping(driver=request.user.driver_profile, **serializer.validated_data)
        return Response(DriverSerializer(driver).data)
