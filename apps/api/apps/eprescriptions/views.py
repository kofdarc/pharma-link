from django.core import signing
from django.http import HttpResponse
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsActivatedDoctor, IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.audit.services import write_audit_log
from apps.eprescriptions.models import Doctor, Prescription
from apps.eprescriptions.serializers import (
    AdminDoctorSerializer,
    DoctorActivationSerializer,
    DoctorSerializer,
    PrescriptionCreateSerializer,
    PrescriptionSerializer,
    PublicDispenseSerializer,
    PublicPrescriptionLookupSerializer,
)
from apps.eprescriptions.services import tokens
from apps.eprescriptions.services.access import PrescriptionAuthError, authenticate
from apps.eprescriptions.services.activation import ActivationError, activate_doctor
from apps.eprescriptions.services.dispense import DispenseError, dispense_prescription
from apps.eprescriptions.services.issue import IssueError, cancel_prescription, issue_prescription
from apps.eprescriptions.services.qr import prescription_qr_svg, prescription_url
from apps.pharmacies.models import Pharmacy


class PrescriptionLookupThrottle(AnonRateThrottle):
    scope = "rx_lookup"


class PrescriptionDispenseThrottle(AnonRateThrottle):
    scope = "rx_dispense"


class DoctorActivationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PrescriptionLookupThrottle]

    def post(self, request):
        serializer = DoctorActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            doctor = activate_doctor(**serializer.validated_data)
        except ActivationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(DoctorSerializer(doctor).data, status=status.HTTP_201_CREATED)


class DoctorProfileView(APIView):
    permission_classes = [IsActivatedDoctor]

    def get(self, request):
        return Response(DoctorSerializer(request.user.doctor_profile).data)


class AdminDoctorViewSet(ModelViewSet):
    """Lets a platform admin suspend a doctor's ability to issue/dispense against prescriptions."""

    queryset = Doctor.objects.order_by("full_name")
    serializer_class = AdminDoctorSerializer
    permission_classes = [IsPlatformAdmin]
    http_method_names = ["get", "patch", "head", "options"]

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        doctor = serializer.save()
        if doctor.is_active != was_active:
            write_audit_log(
                actor_user=self.request.user,
                action="eprescriptions.doctor_active_changed",
                entity_type="Doctor",
                entity_id=doctor.id,
                summary=f"Dr. {doctor.full_name} {'reactivated' if doctor.is_active else 'deactivated'}",
                before_data={"is_active": was_active},
                after_data={"is_active": doctor.is_active},
            )


class DoctorPrescriptionViewSet(ModelViewSet):
    serializer_class = PrescriptionSerializer
    permission_classes = [IsActivatedDoctor]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = Prescription.objects.filter(doctor=self.request.user.doctor_profile).prefetch_related("items__medicine", "dispenses__items__prescription_item")
        patient = self.request.query_params.get("patient")
        if patient:
            qs = qs.filter(patient_name__icontains=patient)
        state = self.request.query_params.get("status")
        if state:
            qs = qs.filter(status=state)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = PrescriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        items = payload.pop("items")
        validity_days = payload.pop("validity_days", None)
        diagnosis_note = payload.pop("diagnosis_note", "")
        try:
            prescription, secret, pin = issue_prescription(
                doctor=request.user.doctor_profile,
                patient=payload,
                items=items,
                diagnosis_note=diagnosis_note,
                validity_days=validity_days,
            )
        except IssueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        data = PrescriptionSerializer(prescription).data
        # Shown to the issuing doctor once: neither value can be retrieved later.
        data["one_time_secrets"] = {
            "pin": pin,
            "qr_url": prescription_url(prescription.code, secret),
            "qr_svg": prescription_qr_svg(prescription.code, secret),
        }
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            prescription = cancel_prescription(prescription=self.get_object(), reason=request.data.get("reason", ""))
        except IssueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(prescription).data)


def public_prescription_payload(prescription: Prescription, ticket: str) -> dict:
    """What a dispensing pharmacy is allowed to see. Patient contact details are withheld."""
    return {
        "code": prescription.code,
        "status": prescription.status,
        "issued_at": prescription.issued_at,
        "valid_until": prescription.valid_until,
        "is_expired": prescription.is_expired,
        "is_consumable": prescription.is_consumable,
        "patient_name": prescription.patient_name,
        "patient_date_of_birth": prescription.patient_date_of_birth,
        "doctor": {
            "full_name": prescription.doctor.full_name,
            "license_number": prescription.doctor.license_number,
            "specialty": prescription.doctor.specialty,
            "clinic_name": prescription.doctor.clinic_name,
        },
        "diagnosis_note": prescription.diagnosis_note,
        "items": [
            {
                "id": item.id,
                "medicine_text": item.medicine_text,
                "medicine_id": item.medicine_id,
                "quantity_prescribed": item.quantity_prescribed,
                "quantity_dispensed": item.quantity_dispensed,
                "quantity_remaining": item.quantity_remaining,
                "unit": item.unit,
                "dosage_instructions": item.dosage_instructions,
                "allow_generic_substitution": item.allow_generic_substitution,
            }
            for item in prescription.items.all()
        ],
        "dispense_history": [
            {"pharmacy_name": entry.pharmacy_name, "dispensed_at": entry.dispensed_at, "units": sum(line.quantity for line in entry.items.all())}
            for entry in prescription.dispenses.all()
        ],
        "dispense_ticket": ticket,
        "ticket_expires_in_seconds": tokens.DISPENSE_TICKET_MAX_AGE_SECONDS,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PrescriptionLookupThrottle])
def public_prescription_lookup(request):
    """Open to the world: any pharmacy can read a prescription it holds the QR key or PIN for."""
    serializer = PublicPrescriptionLookupSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        prescription, method = authenticate(
            code=serializer.validated_data["code"],
            key=serializer.validated_data.get("key", ""),
            pin=serializer.validated_data.get("pin", ""),
            request=request,
        )
    except PrescriptionAuthError as exc:
        return Response({"detail": str(exc)}, status=exc.status)
    ticket = tokens.issue_dispense_ticket(prescription.id, method=method)
    return Response(public_prescription_payload(prescription, ticket))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PrescriptionDispenseThrottle])
def public_prescription_dispense(request):
    serializer = PublicDispenseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    payload = dict(serializer.validated_data)
    try:
        claims = tokens.read_dispense_ticket(payload.pop("ticket"))
    except signing.SignatureExpired:
        return Response({"detail": _("This session expired. Scan the prescription again.")}, status=status.HTTP_401_UNAUTHORIZED)
    except signing.BadSignature:
        return Response({"detail": _("Invalid session. Scan the prescription again.")}, status=status.HTTP_401_UNAUTHORIZED)

    prescription = Prescription.objects.filter(id=claims["prescription_id"]).first()
    if prescription is None:
        return Response({"detail": _("Prescription not found.")}, status=status.HTTP_404_NOT_FOUND)

    lines = payload.pop("items")
    # A signed-in PharmaLink pharmacy is attributed automatically; walk-in pharmacies self-declare.
    pharmacy = request.user.pharmacy if getattr(request.user, "is_authenticated", False) and getattr(request.user, "pharmacy_id", None) else None
    if pharmacy is None and not payload.get("pharmacy_name"):
        return Response({"detail": _("Enter the pharmacy name.")}, status=status.HTTP_400_BAD_REQUEST)
    payload["method"] = claims.get("method", "")
    try:
        dispense = dispense_prescription(prescription=prescription, lines=lines, pharmacy_details=payload, pharmacy=pharmacy, request=request)
    except DispenseError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

    prescription.refresh_from_db()
    return Response(
        {
            "dispense_id": dispense.id,
            "prescription_status": prescription.status,
            "dispensed_at": dispense.dispensed_at,
            "pharmacy_name": dispense.pharmacy_name,
            "remaining": [
                {"id": item.id, "medicine_text": item.medicine_text, "quantity_remaining": item.quantity_remaining}
                for item in prescription.items.all()
            ],
        },
        status=status.HTTP_201_CREATED,
    )


class PharmacyPrescriptionScanView(APIView):
    """Same capability from inside a pharmacy workspace, attributed to the signed-in pharmacy."""

    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def post(self, request):
        serializer = PublicPrescriptionLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prescription, method = authenticate(
                code=serializer.validated_data["code"],
                key=serializer.validated_data.get("key", ""),
                pin=serializer.validated_data.get("pin", ""),
                request=request,
            )
        except PrescriptionAuthError as exc:
            return Response({"detail": str(exc)}, status=exc.status)
        ticket = tokens.issue_dispense_ticket(prescription.id, method=method)
        payload = public_prescription_payload(prescription, ticket)
        payload["pharmacy"] = {"id": request.user.pharmacy_id, "name": request.user.pharmacy.name}
        return Response(payload)


@api_view(["GET"])
@permission_classes([IsActivatedDoctor])
def prescription_qr(request, pk):
    """Re-renders the QR only while the doctor still supplies the key; the key is never stored."""
    prescription = Prescription.objects.filter(id=pk, doctor=request.user.doctor_profile).first()
    if prescription is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    key = request.query_params.get("k", "")
    if not key:
        return Response({"detail": "The QR key is only available at issue time. Re-issue the prescription if it was lost."}, status=status.HTTP_400_BAD_REQUEST)
    return HttpResponse(prescription_qr_svg(prescription.code, key), content_type="image/svg+xml")


@api_view(["GET"])
@permission_classes([AllowAny])
def public_pharmacy_directory(request):
    """Lets a walk-in pharmacy pick itself by name so dispenses can still be attributed."""
    query = request.query_params.get("q", "")
    qs = Pharmacy.objects.filter(is_active=True)
    if query:
        qs = qs.filter(name__icontains=query)
    return Response([{"id": item.id, "name": item.name, "area": item.area, "city": item.city} for item in qs.order_by("name")[:20]])
