from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import DjangoUnicodeDecodeError, force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.accounts.authentication import is_token_expired
from apps.accounts.models import User, UserRole
from apps.accounts.permissions import IsPharmacyOwner, IsPlatformAdmin
from apps.accounts.serializers import (
    EmailVerificationConfirmSerializer,
    LoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendVerificationSerializer,
    ShopperRegisterSerializer,
    UserSerializer,
)
from apps.accounts.services import send_password_reset_email, send_verification_email
from apps.audit.services import write_audit_log


def _user_from_uid(uid: str) -> User | None:
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
    except (TypeError, ValueError, OverflowError, DjangoUnicodeDecodeError):
        return None
    return User.objects.filter(pk=user_id).first()


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class AccountRecoveryThrottle(AnonRateThrottle):
    scope = "account_recovery"


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, created = Token.objects.get_or_create(user=user)
        if not created and is_token_expired(token):
            token.delete()
            token = Token.objects.create(user=user)
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
        send_verification_email(user)
        return Response({"token": token.key, "user": UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class PasswordResetRequestView(APIView):
    """Always answers the same way regardless of whether the email exists, so this endpoint
    cannot be used to enumerate accounts."""

    permission_classes = [AllowAny]
    throttle_classes = [AccountRecoveryThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user is not None:
            send_password_reset_email(user)
        return Response({"detail": _("If an account exists for that email, a reset link has been sent.")})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AccountRecoveryThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user_from_uid(serializer.validated_data["uid"])
        if user is None or not default_token_generator.check_token(user, serializer.validated_data["token"]):
            return Response({"detail": _("This reset link is invalid or has expired.")}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data["password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()  # a password reset ends every existing session
        write_audit_log(actor_user=user, action="auth.password_reset", entity_type="User", entity_id=user.id, summary="Password reset via emailed link")
        return Response({"detail": _("Password updated. You can now log in.")})


class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AccountRecoveryThrottle]

    def post(self, request):
        serializer = ResendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True, email_verified=False).first()
        if user is not None:
            send_verification_email(user)
        return Response({"detail": _("If that account needs verification, a new link has been sent.")})


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AccountRecoveryThrottle]

    def post(self, request):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _user_from_uid(serializer.validated_data["uid"])
        if user is None or not default_token_generator.check_token(user, serializer.validated_data["token"]):
            return Response({"detail": _("This verification link is invalid or has expired.")}, status=status.HTTP_400_BAD_REQUEST)
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=["email_verified"])
            write_audit_log(actor_user=user, action="auth.email_verified", entity_type="User", entity_id=user.id, summary="Email verified")
        return Response({"detail": _("Email verified.")})


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

    def perform_create(self, serializer):
        user = serializer.save(email_verified=True)
        write_audit_log(
            actor_user=self.request.user,
            pharmacy=user.pharmacy,
            action="accounts.user_created",
            entity_type="User",
            entity_id=user.id,
            summary=f"Created {user.email} ({user.role})",
            after_data={"role": user.role, "pharmacy": str(user.pharmacy_id) if user.pharmacy_id else None, "is_active": user.is_active},
        )

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role, "pharmacy": str(serializer.instance.pharmacy_id) if serializer.instance.pharmacy_id else None, "is_active": serializer.instance.is_active}
        user = serializer.save()
        after = {"role": user.role, "pharmacy": str(user.pharmacy_id) if user.pharmacy_id else None, "is_active": user.is_active}
        if before != after:
            write_audit_log(
                actor_user=self.request.user,
                pharmacy=user.pharmacy,
                action="accounts.user_updated",
                entity_type="User",
                entity_id=user.id,
                summary=f"Updated {user.email}",
                before_data=before,
                after_data=after,
            )


class PharmacyStaffViewSet(ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsPharmacyOwner]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return User.objects.filter(pharmacy=self.request.user.pharmacy, role__in=[UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF]).order_by("email")

    def perform_create(self, serializer):
        user = serializer.save(pharmacy=self.request.user.pharmacy, email_verified=True)
        write_audit_log(
            actor_user=self.request.user,
            pharmacy=self.request.user.pharmacy,
            action="accounts.staff_added",
            entity_type="User",
            entity_id=user.id,
            summary=f"Added staff {user.email} ({user.role})",
            after_data={"role": user.role, "is_active": user.is_active},
        )

    def perform_update(self, serializer):
        before = {"role": serializer.instance.role, "is_active": serializer.instance.is_active}
        user = serializer.save()
        after = {"role": user.role, "is_active": user.is_active}
        if before != after:
            write_audit_log(
                actor_user=self.request.user,
                pharmacy=self.request.user.pharmacy,
                action="accounts.staff_updated",
                entity_type="User",
                entity_id=user.id,
                summary=f"Updated staff {user.email}",
                before_data=before,
                after_data=after,
            )

