from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.customers.models import Client
from apps.sales.models import Sale
from apps.sales.serializers import SaleCreateSerializer, SaleSerializer
from apps.sales.services.create_sale import create_sale


class SaleViewSet(ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Sale.objects.filter(pharmacy=self.request.user.pharmacy).select_related("client").prefetch_related("items__medicine", "items__inventory_batch")
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_number__icontains=invoice)
        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        client_id = payload.pop("client", None)
        client = None
        if client_id:
            client = Client.objects.filter(id=client_id, pharmacy=request.user.pharmacy).first()
            if client is None:
                return Response({"detail": "Client not found for this pharmacy."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            sale = create_sale(user=request.user, pharmacy=request.user.pharmacy, client=client, **payload)
        except (ValueError, DjangoValidationError) as exc:
            return Response({"detail": exc.messages[0] if isinstance(exc, DjangoValidationError) else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)

