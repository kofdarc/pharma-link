from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.sales.models import Sale
from apps.sales.serializers import SaleCreateSerializer, SaleSerializer
from apps.sales.services.create_sale import create_sale


class SaleViewSet(ModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Sale.objects.filter(pharmacy=self.request.user.pharmacy).prefetch_related("items__medicine", "items__inventory_batch")
        invoice = self.request.query_params.get("invoice")
        if invoice:
            qs = qs.filter(invoice_number__icontains=invoice)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            sale = create_sale(user=request.user, pharmacy=request.user.pharmacy, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(sale).data, status=status.HTTP_201_CREATED)

