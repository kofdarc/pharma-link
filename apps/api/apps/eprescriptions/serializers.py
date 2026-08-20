from rest_framework import serializers

from apps.eprescriptions.models import Doctor, Prescription, PrescriptionDispense, PrescriptionItem
from apps.medicines.serializers import MedicineSerializer


class DoctorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = [
            "id",
            "license_number",
            "full_name",
            "specialty",
            "email",
            "phone",
            "clinic_name",
            "clinic_address",
            "clinic_area",
            "is_activated",
            "activated_at",
            "is_active",
        ]
        read_only_fields = fields


class AdminDoctorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Doctor
        fields = [
            "id",
            "license_number",
            "full_name",
            "specialty",
            "email",
            "phone",
            "clinic_name",
            "clinic_address",
            "clinic_area",
            "is_activated",
            "activated_at",
            "is_active",
        ]
        read_only_fields = ["id", "license_number", "full_name", "specialty", "email", "phone", "clinic_name", "clinic_address", "clinic_area", "is_activated", "activated_at"]


class DoctorActivationSerializer(serializers.Serializer):
    license_number = serializers.CharField(max_length=60)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)


class PrescriptionItemSerializer(serializers.ModelSerializer):
    medicine_detail = MedicineSerializer(source="medicine", read_only=True)
    quantity_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = PrescriptionItem
        fields = [
            "id",
            "medicine",
            "medicine_detail",
            "medicine_text",
            "quantity_prescribed",
            "quantity_dispensed",
            "quantity_remaining",
            "unit",
            "dosage_instructions",
            "allow_generic_substitution",
        ]
        read_only_fields = ["id", "medicine_detail", "quantity_dispensed", "quantity_remaining"]


class PrescriptionItemCreateSerializer(serializers.Serializer):
    medicine = serializers.UUIDField(required=False, allow_null=True)
    medicine_text = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity_prescribed = serializers.IntegerField(min_value=1, max_value=1000)
    unit = serializers.CharField(max_length=40, required=False, allow_blank=True)
    dosage_instructions = serializers.CharField(max_length=255, required=False, allow_blank=True)
    allow_generic_substitution = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        if not attrs.get("medicine") and not attrs.get("medicine_text"):
            raise serializers.ValidationError("Pick a catalog medicine or write the item name.")
        return attrs


class PrescriptionDispenseSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = PrescriptionDispense
        fields = ["id", "pharmacy", "pharmacy_name", "pharmacist_name", "pharmacist_license", "contact_phone", "dispensed_at", "notes", "items"]
        read_only_fields = fields

    def get_items(self, obj):
        return [
            {"prescription_item": entry.prescription_item_id, "name": entry.prescription_item.medicine_text, "quantity": entry.quantity, "substituted_with": entry.substituted_with}
            for entry in obj.items.select_related("prescription_item")
        ]


class PrescriptionSerializer(serializers.ModelSerializer):
    items = PrescriptionItemSerializer(many=True, read_only=True)
    dispenses = PrescriptionDispenseSerializer(many=True, read_only=True)
    doctor_name = serializers.CharField(source="doctor.full_name", read_only=True)
    doctor_license = serializers.CharField(source="doctor.license_number", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_consumable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Prescription
        fields = [
            "id",
            "code",
            "doctor",
            "doctor_name",
            "doctor_license",
            "patient_name",
            "patient_email",
            "patient_phone",
            "patient_date_of_birth",
            "diagnosis_note",
            "status",
            "issued_at",
            "valid_until",
            "cancelled_at",
            "cancellation_reason",
            "email_sent_at",
            "is_expired",
            "is_consumable",
            "items",
            "dispenses",
        ]
        read_only_fields = fields


class PrescriptionCreateSerializer(serializers.Serializer):
    patient_name = serializers.CharField(max_length=255)
    patient_email = serializers.EmailField(required=False, allow_blank=True)
    patient_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    patient_date_of_birth = serializers.DateField(required=False, allow_null=True)
    diagnosis_note = serializers.CharField(required=False, allow_blank=True)
    validity_days = serializers.IntegerField(required=False, min_value=1, max_value=365)
    items = PrescriptionItemCreateSerializer(many=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("A prescription needs at least one item.")
        return items


class PublicPrescriptionLookupSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=24)
    key = serializers.CharField(max_length=128, required=False, allow_blank=True)
    pin = serializers.CharField(max_length=12, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("key") and not attrs.get("pin"):
            raise serializers.ValidationError("Scan the QR code or enter the PIN printed with the prescription.")
        return attrs


class PublicDispenseLineSerializer(serializers.Serializer):
    prescription_item = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=0, max_value=1000)
    substituted_with = serializers.CharField(max_length=255, required=False, allow_blank=True)


class PublicDispenseSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    pharmacy_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    pharmacist_name = serializers.CharField(max_length=255)
    pharmacist_license = serializers.CharField(max_length=80, required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = PublicDispenseLineSerializer(many=True)
