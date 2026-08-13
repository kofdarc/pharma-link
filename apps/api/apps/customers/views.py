from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.audit.services import write_audit_log
from apps.customers.models import Client, ClientLedgerEntry
from apps.customers.serializers import ClientLedgerEntrySerializer, ClientSerializer
from apps.customers.services import client_history


class ClientViewSet(ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Client.objects.filter(pharmacy=self.request.user.pharmacy)
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(Q(full_name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search))
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(is_active=True)
        return qs

    def perform_create(self, serializer):
        client = serializer.save(pharmacy=self.request.user.pharmacy, created_by=self.request.user)
        write_audit_log(
            actor_user=self.request.user,
            pharmacy=self.request.user.pharmacy,
            action="customers.client_created",
            entity_type="Client",
            entity_id=client.id,
            summary=f"Created client {client.full_name}",
        )

    def perform_update(self, serializer):
        before = {"full_name": serializer.instance.full_name, "phone": serializer.instance.phone, "is_active": serializer.instance.is_active}
        client = serializer.save()
        write_audit_log(
            actor_user=self.request.user,
            pharmacy=self.request.user.pharmacy,
            action="customers.client_updated",
            entity_type="Client",
            entity_id=client.id,
            summary=f"Updated client {client.full_name}",
            before_data=before,
            after_data={"full_name": client.full_name, "phone": client.phone, "is_active": client.is_active},
        )

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        return Response(client_history(self.get_object()))

    @action(detail=True, methods=["get", "post"], url_path="ledger")
    def ledger(self, request, pk=None):
        client = self.get_object()
        if request.method == "GET":
            entries = client.ledger_entries.select_related("created_by")
            return Response(ClientLedgerEntrySerializer(entries, many=True).data)
        serializer = ClientLedgerEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = ClientLedgerEntry.objects.create(client=client, created_by=request.user, **serializer.validated_data)
        write_audit_log(
            actor_user=request.user,
            pharmacy=request.user.pharmacy,
            action="customers.ledger_entry_posted",
            entity_type="ClientLedgerEntry",
            entity_id=entry.id,
            summary=f"{entry.entry_type} of {entry.amount} for {client.full_name}",
            after_data={"amount": str(entry.amount), "entry_type": entry.entry_type},
        )
        return Response(ClientLedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)
