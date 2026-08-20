from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


class Driver(UUIDTimeStampedModel):
    class Vehicle(models.TextChoices):
        SCOOTER = "SCOOTER", "Scooter"
        CAR = "CAR", "Car"
        BICYCLE = "BICYCLE", "Bicycle"

    user = models.OneToOneField("accounts.User", on_delete=models.CASCADE, related_name="driver_profile")
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=40)
    vehicle_type = models.CharField(max_length=20, choices=Vehicle.choices, default=Vehicle.SCOOTER)
    capacity_units = models.PositiveIntegerField(default=60, help_text="Carrying capacity in item units; caps how much one route may hold.")
    base_latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    base_longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    last_ping_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_online = models.BooleanField(default=False, db_index=True, help_text="Only online drivers enter the planner.")
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_vehicle_type_display()})"

    @property
    def position(self) -> tuple[float, float]:
        """Plan from where the driver actually is, falling back to their base."""
        if self.current_latitude is not None and self.current_longitude is not None:
            return float(self.current_latitude), float(self.current_longitude)
        return float(self.base_latitude), float(self.base_longitude)


class DeliveryRoute(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Proposed"
        OFFERED = "OFFERED", "Offered to driver"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        COMPLETED_WITH_ISSUES = "COMPLETED_WITH_ISSUES", "Completed with issues"
        CANCELLED = "CANCELLED", "Cancelled"

    driver = models.ForeignKey(Driver, null=True, blank=True, on_delete=models.SET_NULL, related_name="routes", db_index=True)
    status = models.CharField(max_length=22, choices=Status.choices, default=Status.PROPOSED, db_index=True)
    planned_distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    planned_duration_minutes = models.PositiveIntegerField(default=0)
    naive_distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Same work done as one dedicated trip per order, for comparison.")
    plan_version = models.PositiveIntegerField(default=1, help_text="Bumped every time the remaining stops are re-optimised.")
    planner_notes = models.TextField(blank=True)
    offered_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Route {str(self.id)[:8]} ({self.status})"

    @property
    def distance_saved_km(self):
        return max(0, float(self.naive_distance_km) - float(self.planned_distance_km))


class RouteStop(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        PICKUP = "PICKUP", "Pickup"
        DROPOFF = "DROPOFF", "Dropoff"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ARRIVED = "ARRIVED", "Arrived"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"
        SKIPPED = "SKIPPED", "Skipped"

    route = models.ForeignKey(DeliveryRoute, on_delete=models.CASCADE, related_name="stops")
    sequence = models.PositiveIntegerField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # A pickup stop points at a pharmacy; a dropoff points at an order's address.
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", null=True, blank=True, on_delete=models.PROTECT, related_name="route_stops")
    order = models.ForeignKey("orders.Order", null=True, blank=True, on_delete=models.PROTECT, related_name="route_stops")
    label = models.CharField(max_length=255)
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    units = models.PositiveIntegerField(default=0)
    planned_arrival = models.DateTimeField(null=True, blank=True)
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["route", "sequence"]
        constraints = [models.UniqueConstraint(fields=["route", "sequence"], name="unique_stop_sequence_per_route")]

    def __str__(self) -> str:
        return f"{self.sequence}. {self.kind} {self.label}"


class RouteStopTask(UUIDTimeStampedModel):
    """
    What to do at a stop, per order. This is the model that makes consolidation visible:
    one pickup stop at a pharmacy can carry tasks for several different customers.
    """

    stop = models.ForeignKey(RouteStop, on_delete=models.CASCADE, related_name="tasks")
    order_fulfillment = models.ForeignKey("orders.OrderFulfillment", on_delete=models.CASCADE, related_name="route_tasks")
    units = models.PositiveIntegerField(default=0)
    is_done = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


class DriverLocationPing(UUIDTimeStampedModel):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="pings")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["-created_at"]


class RouteEvent(UUIDTimeStampedModel):
    route = models.ForeignKey(DeliveryRoute, on_delete=models.CASCADE, related_name="events")
    stop = models.ForeignKey(RouteStop, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
    event = models.CharField(max_length=60)
    detail = models.CharField(max_length=255, blank=True)
    actor_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="route_events")

    class Meta:
        ordering = ["-created_at"]
