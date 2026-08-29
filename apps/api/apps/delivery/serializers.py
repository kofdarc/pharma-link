from rest_framework import serializers

from apps.delivery.models import DeliveryRoute, Driver, RouteEvent, RouteStop, RouteStopTask


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = [
            "id",
            "full_name",
            "phone",
            "vehicle_type",
            "capacity_units",
            "base_latitude",
            "base_longitude",
            "current_latitude",
            "current_longitude",
            "last_ping_at",
            "is_active",
            "is_online",
            "shift_start",
            "shift_end",
        ]
        read_only_fields = ["id", "current_latitude", "current_longitude", "last_ping_at"]


class RouteStopTaskSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order_fulfillment.order.reference", read_only=True)
    contact_name = serializers.CharField(source="order_fulfillment.order.contact_name", read_only=True)
    contact_phone = serializers.CharField(source="order_fulfillment.order.contact_phone", read_only=True)
    pharmacy_name = serializers.CharField(source="order_fulfillment.pharmacy.name", read_only=True)
    handover_code = serializers.CharField(source="order_fulfillment.handover_code", read_only=True)
    fulfillment_status = serializers.CharField(source="order_fulfillment.status", read_only=True)

    class Meta:
        model = RouteStopTask
        # Deliberately no per-line medicine breakdown: a driver only needs the unit
        # count to verify a handoff, not what the patient was prescribed.
        fields = [
            "id",
            "order_fulfillment",
            "order_reference",
            "contact_name",
            "contact_phone",
            "pharmacy_name",
            "handover_code",
            "fulfillment_status",
            "units",
            "is_done",
        ]
        read_only_fields = fields


class RouteStopSerializer(serializers.ModelSerializer):
    tasks = RouteStopTaskSerializer(many=True, read_only=True)
    orders_served = serializers.SerializerMethodField()

    class Meta:
        model = RouteStop
        fields = [
            "id",
            "sequence",
            "kind",
            "pharmacy",
            "order",
            "label",
            "address",
            "latitude",
            "longitude",
            "units",
            "planned_arrival",
            "window_start",
            "window_end",
            "arrived_at",
            "completed_at",
            "status",
            "failure_reason",
            "orders_served",
            "tasks",
        ]
        read_only_fields = fields

    def get_orders_served(self, obj) -> int:
        return obj.tasks.count()


class DeliveryRouteSerializer(serializers.ModelSerializer):
    stops = RouteStopSerializer(many=True, read_only=True)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True, default="")
    distance_saved_km = serializers.FloatField(read_only=True)
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRoute
        fields = [
            "id",
            "driver",
            "driver_name",
            "status",
            "planned_distance_km",
            "planned_duration_minutes",
            "naive_distance_km",
            "distance_saved_km",
            "plan_version",
            "planner_notes",
            "orders_count",
            "offered_at",
            "accepted_at",
            "started_at",
            "completed_at",
            "created_at",
            "stops",
        ]
        read_only_fields = fields

    def get_orders_count(self, obj) -> int:
        return len({task.order_fulfillment.order_id for stop in obj.stops.all() for task in stop.tasks.all()})


class RouteEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RouteEvent
        fields = ["id", "event", "detail", "stop", "created_at"]
        read_only_fields = fields


class PingSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class PickupCompletionSerializer(serializers.Serializer):
    # fulfillment id -> handover code shown by the pharmacist
    handover_codes = serializers.DictField(child=serializers.CharField(max_length=8), required=False)


class DropoffCompletionSerializer(serializers.Serializer):
    recipient_note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class FailStopSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
