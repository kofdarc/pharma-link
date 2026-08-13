from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.models import User, UserRole
from apps.accounts.permissions import IsPharmacyOwner, IsPlatformAdmin
from apps.accounts.serializers import LoginSerializer, ShopperRegisterSerializer, UserSerializer
from apps.audit.services import write_audit_log


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _created = Token.objects.get_or_create(user=user)
        user.mark_logged_in()
        write_audit_log(
            actor_user=user,
            pharmacy=user.pharmacy,
            action="auth.login",
            entity_type="User",
            entity_id=user.id,
            summary="User logged in",
        )
        return Response({"token": token.key, "user": UserSerializer(user).data})


class ShopperRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ShopperRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _created = Token.objects.get_or_create(user=user)
        write_audit_log(
            actor_user=user,
            action="auth.shopper_registered",
            entity_type="User",
            entity_id=user.id,
            summary=f"Shopper account created for {user.email}",
        )
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminUserViewSet(ModelViewSet):
    queryset = User.objects.select_related("pharmacy").order_by("email")
    serializer_class = UserSerializer
    permission_classes = [IsPlatformAdmin]


class PharmacyStaffViewSet(ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsPharmacyOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(pharmacy=self.request.user.pharmacy, role__in=[UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF]).order_by("email")

    def perform_create(self, serializer):
        serializer.save(pharmacy=self.request.user.pharmacy)

