from rest_framework import serializers

from apps.prescriptions.models import PrescriptionRecord


class PrescriptionRecordSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    file_name = serializers.CharField(source="file_original_name", read_only=True)
    download_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = PrescriptionRecord
        fields = [
            "id",
            "pharmacy",
            "sale",
            "patient_name",
            "patient_phone",
            "doctor_name",
            "prescription_date",
            "valid_until",
            "is_expired",
            "file",
            "file_name",
            "file_mime_type",
            "file_size",
            "notes",
            "created_by",
            "created_by_email",
            "download_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "pharmacy",
            "is_expired",
            "file_name",
            "file_mime_type",
            "file_size",
            "created_by",
            "created_by_email",
            "download_url",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True, "required": False}}

    def get_download_url(self, obj):
        return f"/api/pharmacy/prescriptions/{obj.id}/download/" if obj.file else None

