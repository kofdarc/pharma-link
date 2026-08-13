from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer


class AdminAuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor_user", "pharmacy").order_by("-created_at")
    serializer_class = AuditLogSerializer
    permission_classes = [IsPlatformAdmin]


class PharmacyAuditLogViewSet(ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return AuditLog.objects.filter(pharmacy=self.request.user.pharmacy).select_related("actor_user", "pharmacy")

