from decimal import Decimal

from rest_framework import serializers

from apps.common.geo import area_coordinates
from apps.medicines.serializers import MedicineSerializer
from apps.medicines.models import Medicine
from apps.orders.models import DeliveryAddress, Order, OrderFulfillment, OrderLine, PharmacyReview, RecurringOrder
from apps.payments.models import Payment
from apps.payments.serializers import PaymentSerializer


class DeliveryAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryAddress
        fields = [
            "id",
            "label",
            "contact_name",
            "phone",
            "address",
            "area",
            "city",
            "building_notes",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        # Sourcing needs coordinates, but nobody can type their own latitude.
        # When a client sends none, they are resolved from the area below.
        extra_kwargs = {"latitude": {"required": False}, "longitude": {"required": False}}

    def validate(self, attrs):
        has_coordinates = attrs.get("latitude") is not None and attrs.get("longitude") is not None
        if has_coordinates:
            return attrs
        instance_has = self.instance is not None and self.instance.latitude is not None
        # An edit that doesn't touch the area keeps whatever coordinates the
        # address already has - re-deriving them would discard a real map pin.
        if instance_has and "area" not in attrs:
            return attrs
        area = attrs.get("area", getattr(self.instance, "area", ""))
        city = attrs.get("city", getattr(self.instance, "city", ""))
        latitude, longitude = area_coordinates(area, city)
        attrs["latitude"] = Decimal(str(latitude))
        attrs["longitude"] = Decimal(str(longitude))
        return attrs


class OrderLineSerializer(serializers.ModelSerializer):
    medicine_detail = MedicineSerializer(source="medicine", read_only=True)

    class Meta:
        model = OrderLine
        fields = ["id", "medicine", "medicine_detail", "quantity", "unit_price", "line_total", "is_price_regulated"]
        read_only_fields = fields


class OrderFulfillmentSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)
    pharmacy_area = serializers.CharField(source="pharmacy.area", read_only=True)
    pharmacy_phone = serializers.CharField(source="pharmacy.phone", read_only=True)

    class Meta:
        model = OrderFulfillment
        fields = [
            "id",
            "pharmacy",
            "pharmacy_name",
            "pharmacy_area",
            "pharmacy_phone",
            "status",
            "subtotal",
            "accepted_at",
            "ready_at",
            "picked_up_at",
            "completed_at",
            "rejection_reason",
            "sale",
            "lines",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    fulfillments = OrderFulfillmentSerializer(many=True, read_only=True)
    window_start = serializers.DateTimeField(read_only=True)
    window_end = serializers.DateTimeField(read_only=True)
    payment = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "reference",
            "status",
            "fulfillment_type",
            "source",
            "prescription",
            "contact_name",
            "contact_phone",
            "address",
            "area",
            "city",
            "latitude",
            "longitude",
            "delivery_notes",
            "scheduled_for",
            "window_minutes",
            "window_start",
            "window_end",
            "items_subtotal",
            "delivery_fee",
            "total",
            "notes",
            "cancelled_reason",
            "fulfillments",
            "payment",
            "review",
            "created_at",
        ]
        read_only_fields = fields

    def get_payment(self, obj):
        payment = getattr(obj, "payment", None)
        return PaymentSerializer(payment).data if payment else None

    def get_review(self, obj):
        """
        The shopper's own review, so their order history can show what they said
        without a second request. Hidden reviews are moderated out of the
        pharmacy's public rating but remain visible to the person who wrote them.
        """
        review = obj.reviews.order_by("-created_at").first()
        if review is None:
            return None
        return {"rating": review.rating, "comment": review.comment, "pharmacy": str(review.pharmacy_id)}


class PharmacyOrderFulfillmentSerializer(OrderFulfillmentSerializer):
    """What a pharmacy sees: its own slice, plus only the delivery context it needs."""

    order_reference = serializers.CharField(source="order.reference", read_only=True)
    order_status = serializers.CharField(source="order.status", read_only=True)
    order_area = serializers.CharField(source="order.area", read_only=True)
    contact_name = serializers.CharField(source="order.contact_name", read_only=True)
    scheduled_for = serializers.DateTimeField(source="order.scheduled_for", read_only=True)
    fulfillment_type = serializers.CharField(source="order.fulfillment_type", read_only=True)
    is_shared_order = serializers.SerializerMethodField()

    class Meta(OrderFulfillmentSerializer.Meta):
        fields = OrderFulfillmentSerializer.Meta.fields + [
            "order",
            "order_reference",
            "order_status",
            "order_area",
            "contact_name",
            "scheduled_for",
            "fulfillment_type",
            "handover_code",
            "is_shared_order",
        ]
        read_only_fields = fields

    def get_is_shared_order(self, obj) -> bool:
        return obj.order.fulfillments.count() > 1


class BasketItemSerializer(serializers.Serializer):
    medicine = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=100)


class BasketQuoteSerializer(serializers.Serializer):
    items = BasketItemSerializer(many=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    radius_km = serializers.FloatField(required=False, min_value=0.5, max_value=50)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one item.")
        return items


class OrderCreateSerializer(serializers.Serializer):
    items = BasketItemSerializer(many=True)
    address = serializers.UUIDField(required=False, allow_null=True)
    fulfillment_type = serializers.ChoiceField(choices=Order.FulfillmentType.choices, default=Order.FulfillmentType.DELIVERY)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    window_minutes = serializers.IntegerField(required=False, min_value=30, max_value=480, default=120)
    notes = serializers.CharField(required=False, allow_blank=True)
    prescription_code = serializers.CharField(required=False, allow_blank=True, max_length=24)
    payment_method = serializers.ChoiceField(choices=Payment.Provider.choices, default=Payment.Provider.CASH_ON_DELIVERY)
    insurance_policy = serializers.UUIDField(required=False, allow_null=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one item.")
        return items


class RecurringOrderSerializer(serializers.ModelSerializer):
    items = BasketItemSerializer(many=True)
    item_details = serializers.SerializerMethodField()
    prescription_code = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=24)
    prescription_code_value = serializers.CharField(source="prescription.code", read_only=True, default="")

    class Meta:
        model = RecurringOrder
        fields = [
            "id",
            "label",
            "address",
            "items",
            "item_details",
            "prescription",
            "prescription_code",
            "prescription_code_value",
            "interval_days",
            "preferred_hour",
            "next_run_at",
            "last_run_at",
            "occurrences_created",
            "is_active",
            "last_error",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "item_details",
            "prescription",
            "prescription_code_value",
            "last_run_at",
            "occurrences_created",
            "last_error",
            "created_at",
        ]

    def get_item_details(self, obj) -> list:
        """
        `items` is a JSON list of medicine ids, so a client showing a schedule
        would otherwise have to look each one up to name it.
        """
        medicines = {
            str(medicine.id): medicine
            for medicine in Medicine.objects.filter(id__in=[entry.get("medicine") for entry in obj.items or []])
        }
        details = []
        for entry in obj.items or []:
            medicine = medicines.get(str(entry.get("medicine")))
            if medicine is None:
                continue
            details.append(
                {
                    "medicine": str(medicine.id),
                    "name": str(medicine),
                    "generic_name": medicine.generic_name,
                    "quantity": entry.get("quantity", 1),
                    "requires_prescription": medicine.requires_prescription,
                }
            )
        return details

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one item to repeat.")
        return [{"medicine": str(entry["medicine"]), "quantity": entry["quantity"]} for entry in items]


class PharmacyReviewSerializer(serializers.ModelSerializer):
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = PharmacyReview
        fields = ["id", "order", "pharmacy", "customer_email", "rating", "comment", "was_complete", "is_hidden", "hidden_reason", "created_at"]
        read_only_fields = ["id", "customer_email", "is_hidden", "hidden_reason", "created_at"]


class RejectFulfillmentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class HandoverSerializer(serializers.Serializer):
    handover_code = serializers.CharField(max_length=8, required=False, allow_blank=True)
    collected_in_store = serializers.BooleanField(required=False, default=False)
