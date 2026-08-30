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


def _nssf_snapshot(medicine) -> dict:
    return {
        "nssf_covered": medicine.nssf_covered,
        "nssf_reference_price": str(medicine.nssf_reference_price) if medicine.nssf_reference_price is not None else None,
        "nssf_reimbursement_rate": str(medicine.nssf_reimbursement_rate) if medicine.nssf_reimbursement_rate is not None else None,
        "nssf_source_reference": medicine.nssf_source_reference or None,
    }


class AdminMedicineViewSet(ModelViewSet):
    queryset = Medicine.objects.prefetch_related("aliases").order_by("brand_name")
    serializer_class = MedicineSerializer
    permission_classes = [IsPlatformAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ["brand_name", "generic_name", "manufacturer"]

    def get_queryset(self):
        queryset = super().get_queryset()
        covered = self.request.query_params.get("nssf_covered")
        if covered in {"true", "false"}:
            queryset = queryset.filter(nssf_covered=(covered == "true"))
        return queryset

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
        if medicine.nssf_covered:
            write_audit_log(
                actor_user=self.request.user,
                action="medicines.nssf_coverage_updated",
                entity_type="Medicine",
                entity_id=medicine.id,
                summary=f"NSSF coverage set for {medicine}",
                after_data=_nssf_snapshot(medicine),
            )

    def perform_update(self, serializer):
        previous_price = serializer.instance.regulated_price
        previous_nssf = _nssf_snapshot(serializer.instance)
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
        current_nssf = _nssf_snapshot(medicine)
        if current_nssf != previous_nssf:
            write_audit_log(
                actor_user=self.request.user,
                action="medicines.nssf_coverage_updated",
                entity_type="Medicine",
                entity_id=medicine.id,
                summary=f"NSSF coverage for {medicine} changed",
                before_data=previous_nssf,
                after_data=current_nssf,
            )


class MedicineViewSet(ReadOnlyModelViewSet):
    queryset = Medicine.objects.filter(is_active=True).prefetch_related("aliases").order_by("brand_name")
    serializer_class = MedicineSerializer
    permission_classes = [IsAuthenticated]


@api_view(["GET"])
@permission_classes([AllowAny])
def medicine_search(request):
    medicine_id = request.query_params.get("id")
    if medicine_id:
        medicine = Medicine.objects.filter(id=medicine_id, is_active=True).prefetch_related("aliases").first()
        if not medicine:
            return Response(status=404)
        return Response(MedicineSerializer(medicine, context={"request": request}).data)

    query = request.query_params.get("q", "")
    serializer = MedicineSerializer(search_medicines(query, active_only=True), many=True, context={"request": request})
    return Response(serializer.data)
