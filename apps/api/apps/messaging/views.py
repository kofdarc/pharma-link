from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsActivatedDoctor, IsPharmacyUserWithActivePharmacy, IsShopper
from apps.eprescriptions.models import Prescription
from apps.messaging.models import Conversation, Message
from apps.messaging.serializers import MessageCreateSerializer, MessageSerializer
from apps.messaging.services import get_or_create_conversation, ingest_delivery_status, ingest_inbound, send_message
from apps.orders.models import OrderFulfillment


class _FulfillmentMessagesView(APIView):
    """
    Shared shape for both sides of a chat thread: list messages on an OrderFulfillment's
    Conversation (creating none if the thread hasn't started) and post a new one (creating
    the Conversation lazily on first send). Ownership is enforced entirely through the
    OrderFulfillment lookup filter in `_get_fulfillment`, the same way every other
    pharmacy/customer-scoped endpoint in this codebase restricts access via get_queryset -
    a fulfillment that doesn't belong to the caller simply 404s.
    """

    def _get_fulfillment(self, request, pk):
        raise NotImplementedError

    def get(self, request, pk):
        fulfillment = self._get_fulfillment(request, pk)
        conversation = Conversation.objects.filter(order_fulfillment=fulfillment).first()
        messages = conversation.messages.all() if conversation else Message.objects.none()
        return Response(MessageSerializer(messages, many=True).data)

    def post(self, request, pk):
        fulfillment = self._get_fulfillment(request, pk)
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = get_or_create_conversation(order_fulfillment=fulfillment)
        message = send_message(conversation=conversation, sender=request.user, body=serializer.validated_data["body"])
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


class ShopperFulfillmentMessagesView(_FulfillmentMessagesView):
    permission_classes = [IsShopper]

    def _get_fulfillment(self, request, pk):
        return get_object_or_404(OrderFulfillment.objects.select_related("order", "pharmacy"), pk=pk, order__customer=request.user)


class PharmacyFulfillmentMessagesView(_FulfillmentMessagesView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def _get_fulfillment(self, request, pk):
        return get_object_or_404(OrderFulfillment.objects.select_related("order", "pharmacy"), pk=pk, pharmacy=request.user.pharmacy)


class _PrescriptionMessagesView(APIView):
    """Same shape as _FulfillmentMessagesView, anchored to a Prescription instead - see
    apps.eprescriptions.models.Prescription.target_pharmacy for when this applies."""

    def _get_prescription(self, request, pk):
        raise NotImplementedError

    def get(self, request, pk):
        prescription = self._get_prescription(request, pk)
        conversation = Conversation.objects.filter(prescription=prescription).first()
        messages = conversation.messages.all() if conversation else Message.objects.none()
        return Response(MessageSerializer(messages, many=True).data)

    def post(self, request, pk):
        prescription = self._get_prescription(request, pk)
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = get_or_create_conversation(prescription=prescription)
        message = send_message(conversation=conversation, sender=request.user, body=serializer.validated_data["body"])
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


class DoctorPrescriptionMessagesView(_PrescriptionMessagesView):
    permission_classes = [IsActivatedDoctor]

    def _get_prescription(self, request, pk):
        return get_object_or_404(Prescription.objects.select_related("target_pharmacy", "doctor"), pk=pk, doctor=request.user.doctor_profile)


class PharmacyPrescriptionMessagesView(_PrescriptionMessagesView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def _get_prescription(self, request, pk):
        return get_object_or_404(Prescription.objects.select_related("target_pharmacy", "doctor"), pk=pk, target_pharmacy=request.user.pharmacy)


def _signature_valid(body: bytes, header: str) -> bool:
    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        # No secret configured (console/dev mode) - nothing to verify against.
        return True
    if not header:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


class WhatsAppWebhookView(APIView):
    """Meta Cloud API webhook: verification handshake (GET) and inbound message delivery (POST)."""

    permission_classes = [AllowAny]

    def get(self, request):
        if request.query_params.get("hub.verify_token") == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
            return Response(int(request.query_params.get("hub.challenge", 0)))
        return Response(status=status.HTTP_403_FORBIDDEN)

    def post(self, request):
        if not _signature_valid(request.body, request.headers.get("X-Hub-Signature-256", "")):
            return Response(status=status.HTTP_403_FORBIDDEN)
        for entry in request.data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                to_phone = value.get("metadata", {}).get("display_phone_number", "")
                for incoming in value.get("messages", []):
                    body = incoming.get("text", {}).get("body", "")
                    if body:
                        ingest_inbound(from_phone=incoming.get("from", ""), to_phone=to_phone, body=body)
                for delivery in value.get("statuses", []):
                    errors = delivery.get("errors") or []
                    reason = (errors[0].get("title") or errors[0].get("message") or "") if errors else ""
                    ingest_delivery_status(
                        provider_message_id=delivery.get("id", ""),
                        provider_status=delivery.get("status", ""),
                        failure_reason=reason,
                    )
        return Response(status=status.HTTP_200_OK)
