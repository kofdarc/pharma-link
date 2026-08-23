from rest_framework import serializers

from apps.messaging.models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(source="sender_user.email", read_only=True, default=None)

    class Meta:
        model = Message
        fields = ["id", "direction", "body", "status", "sender_email", "failure_reason", "created_at"]
        read_only_fields = fields


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4096)


class ConversationSerializer(serializers.ModelSerializer):
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    order_reference = serializers.CharField(source="order_fulfillment.order.reference", read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "order_fulfillment", "order_reference", "pharmacy", "pharmacy_name", "customer_email", "last_message_at", "created_at"]
        read_only_fields = fields
