from rest_framework import filters
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPlatformAdmin
from apps.audit.services import write_audit_log
from apps.medicines.models import Medicine
from apps.medicines.serializers import MedicineSerializer
from apps.medicines.services.search import search_medicines


class AdminMedicineViewSet(ModelViewSet):
    queryset = Medicine.objects.prefetch_related("aliases").order_by("brand_name")
    serializer_class = MedicineSerializer
    permission_classes = [IsPlatformAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["brand_name", "generic_name", "manufacturer"]

    def perform_create(self, serializer):
        medicine = serializer.save()
        if medicine.regulated_price is not None:
            write_audit_log(
                actor_user=self.request.user,
                action="medicines.price_updated",
                entity_type="Medicine",
                entity_id=medicine.id,
                summary=f"Regulated price set for {medicine}",
                after_data={"regulated_price": str(medicine.regulated_price)},
            )

    def perform_update(self, serializer):
        previous_price = serializer.instance.regulated_price
        medicine = serializer.save()
        if medicine.regulated_price != previous_price:
            write_audit_log(
                actor_user=self.request.user,
                action="medicines.price_updated",
                entity_type="Medicine",
                entity_id=medicine.id,
                summary=f"Regulated price for {medicine} changed",
                before_data={"regulated_price": str(previous_price) if previous_price is not None else None},
                after_data={"regulated_price": str(medicine.regulated_price) if medicine.regulated_price is not None else None},
            )


class MedicineViewSet(ReadOnlyModelViewSet):
    queryset = Medicine.objects.filter(is_active=True).prefetch_related("aliases").order_by("brand_name")
    serializer_class = MedicineSerializer
    permission_classes = [IsAuthenticated]


@api_view(["GET"])
@permission_classes([AllowAny])
def medicine_search(request):
    query = request.query_params.get("q", "")
    serializer = MedicineSerializer(search_medicines(query, active_only=True), many=True)
    return Response(serializer.data)

