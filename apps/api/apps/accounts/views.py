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
from apps.accounts.models import NotificationPreferences, ShopperLocation, User, UserRole
from apps.accounts.permissions import IsPharmacyOwner, IsPlatformAdmin
from apps.accounts.serializers import (
    EmailVerificationConfirmSerializer,
    LoginSerializer,
    NotificationPreferencesSerializer,
    OwnProfileSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendVerificationSerializer,
    ShopperLocationSerializer,
    ShopperRegisterSerializer,
    UserSerializer,
)
from apps.accounts.services import send_password_reset_email, send_verification_email
from apps.audit.services import write_audit_log
from apps.common.geo import nearest_area


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

    def patch(self, request):
        """Name and contact number only - see OwnProfileSerializer for why."""
        serializer = OwnProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class NotificationPreferencesView(APIView):
    """The signed-in user's own notification settings. Created on first read."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(NotificationPreferencesSerializer(NotificationPreferences.for_user(request.user)).data)

    def patch(self, request):
        preferences = NotificationPreferences.for_user(request.user)
        serializer = NotificationPreferencesSerializer(preferences, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


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



class ShopperLocationView(APIView):
    """
    Where the signed-in person has told us they are. Opt-in, overwritable, deletable.

    PUT replaces it, DELETE forgets it, GET returns 204 when there is nothing on file rather
    than an empty object - "never shared" and "shared, then cleared" are the same state here
    and both mean the platform holds no position for this account.

    Sharing a location is never a precondition for anything: every surface that reads this
    falls back through `apps.common.location.resolve_origin`, so deleting it degrades the
    ranking of search results and nothing else. That is what makes DELETE a real option
    rather than a button that quietly breaks the product.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        location = getattr(request.user, "shopper_location", None)
        if location is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ShopperLocationSerializer(location).data)

    def put(self, request):
        serializer = ShopperLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        location, _created = ShopperLocation.objects.update_or_create(
            user=request.user,
            defaults={
                "latitude": data["latitude"],
                "longitude": data["longitude"],
                # Spelled out rather than splatted from `data`, because an omitted optional
                # field is simply absent from `validated_data` - and on an update that would
                # leave the previous fix's accuracy attached to a new position. Every field
                # is written on every PUT, so the row always describes one single fix.
                "accuracy_metres": data.get("accuracy_metres"),
                "source": data.get("source", ShopperLocation.Source.DEVICE),
                # Resolved here, once, from the coordinates actually stored - see the
                # serializer for why this is not a client-supplied field.
                "label": nearest_area(float(data["latitude"]), float(data["longitude"])),
            },
        )
        return Response(ShopperLocationSerializer(location).data)

    def delete(self, request):
        ShopperLocation.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
