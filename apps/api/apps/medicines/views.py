from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPlatformAdmin
from apps.medicines.models import Medicine
from apps.medicines.serializers import MedicineSerializer
from apps.medicines.services.search import search_medicines


class AdminMedicineViewSet(ModelViewSet):
    queryset = Medicine.objects.prefetch_related("aliases").order_by("brand_name")
    serializer_class = MedicineSerializer
    permission_classes = [IsPlatformAdmin]


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

