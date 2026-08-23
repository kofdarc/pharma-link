from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsActivatedDoctor, IsPharmacyUserWithActivePharmacy, IsPlatformAdmin, IsShopper
from apps.customers.models import Client
from apps.insurance.models import InsuranceClaim, InsurancePlan, InsuranceProvider, PatientInsurancePolicy
from apps.insurance.serializers import (
    ClaimStatusUpdateSerializer,
    InsuranceClaimSerializer,
    InsurancePlanSerializer,
    InsuranceProviderSerializer,
    PatientInsurancePolicySerializer,
    PublicInsurancePlanSerializer,
)
from apps.insurance.services import InsuranceError, update_claim_status


class AdminInsuranceProviderViewSet(ModelViewSet):
    queryset = InsuranceProvider.objects.all()
    serializer_class = InsuranceProviderSerializer
    permission_classes = [IsPlatformAdmin]


class AdminInsurancePlanViewSet(ModelViewSet):
    queryset = InsurancePlan.objects.select_related("provider").all()
    serializer_class = InsurancePlanSerializer
    permission_classes = [IsPlatformAdmin]


class AdminInsuranceClaimViewSet(ReadOnlyModelViewSet):
    queryset = InsuranceClaim.objects.select_related("pharmacy", "policy__plan__provider", "order_fulfillment__order", "sale")
    serializer_class = InsuranceClaimSerializer
    permission_classes = [IsPlatformAdmin]


class ShopInsurancePolicyViewSet(ModelViewSet):
    serializer_class = PatientInsurancePolicySerializer
    permission_classes = [IsShopper]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return PatientInsurancePolicy.objects.filter(customer_user=self.request.user).select_related("plan__provider")

    def perform_create(self, serializer):
        serializer.save(customer_user=self.request.user)


class PharmacyInsurancePolicyViewSet(ModelViewSet):
    serializer_class = PatientInsurancePolicySerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        qs = PatientInsurancePolicy.objects.filter(client__pharmacy=self.request.user.pharmacy).select_related("plan__provider", "client")
        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def create(self, request, *args, **kwargs):
        client_id = request.data.get("client")
        client = Client.objects.filter(id=client_id, pharmacy=request.user.pharmacy).first()
        if client is None:
            return Response({"detail": "Client not found for this pharmacy."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(client=client)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PharmacyInsuranceClaimViewSet(ReadOnlyModelViewSet):
    serializer_class = InsuranceClaimSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return InsuranceClaim.objects.filter(pharmacy=self.request.user.pharmacy).select_related(
            "policy__plan__provider", "order_fulfillment__order", "sale"
        )

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, pk=None):
        serializer = ClaimStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claim = update_claim_status(claim=self.get_object(), user=request.user, **serializer.validated_data)
        except InsuranceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(claim).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_insurance_plans(request):
    plans = InsurancePlan.objects.filter(is_active=True, provider__is_active=True).select_related("provider")
    return Response(PublicInsurancePlanSerializer(plans, many=True).data)


@api_view(["GET"])
@permission_classes([IsActivatedDoctor])
def doctor_formulary_lookup(request):
    """
    "Formulary Services" (PrescribeIT), adapted to what this platform actually has: no
    per-medicine coverage dataset exists (see InsurancePlan's docstring), so this surfaces the
    plan-level coverage % / copay floor for whichever insurance plan the named patient is
    known to hold, so a doctor can gauge affordability before prescribing. Only plan-level
    coverage is returned - no client/pharmacy identifying details - since a doctor isn't
    scoped to any one pharmacy's client records.
    """
    email = request.query_params.get("patient_email", "").strip()
    phone = request.query_params.get("patient_phone", "").strip()
    if not email and not phone:
        return Response({"detail": "Provide patient_email or patient_phone."}, status=status.HTTP_400_BAD_REQUEST)

    policies = PatientInsurancePolicy.objects.filter(is_active=True).select_related("plan__provider")
    q = None
    if email:
        q = Q(customer_user__email__iexact=email) | Q(client__email__iexact=email)
    if phone:
        phone_q = Q(client__phone=phone)
        q = phone_q if q is None else (q | phone_q)
    policies = policies.filter(q).distinct()
    plans = InsurancePlan.objects.filter(id__in=policies.values_list("plan_id", flat=True))
    return Response(PublicInsurancePlanSerializer(plans, many=True).data)
