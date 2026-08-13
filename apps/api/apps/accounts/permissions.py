from rest_framework.permissions import BasePermission

from apps.accounts.models import UserRole


def has_active_pharmacy(user) -> bool:
    return bool(getattr(user, "pharmacy_id", None) and user.pharmacy and user.pharmacy.is_active)


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.role == UserRole.PLATFORM_ADMIN)


class IsPharmacyUserWithActivePharmacy(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_pharmacy_user and has_active_pharmacy(request.user))


class IsPharmacyOwner(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.role == UserRole.PHARMACY_OWNER and has_active_pharmacy(request.user))


class IsActivatedDoctor(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated or user.role != UserRole.DOCTOR:
            return False
        doctor = getattr(user, "doctor_profile", None)
        return bool(doctor and doctor.is_activated and doctor.is_active)


class IsShopper(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.role == UserRole.CUSTOMER)


class IsActiveDriver(BasePermission):
    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated or user.role != UserRole.DRIVER:
            return False
        driver = getattr(user, "driver_profile", None)
        return bool(driver and driver.is_active)


class IsAdminOrPharmacyUser(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == UserRole.PLATFORM_ADMIN:
            return True
        return bool(request.user.is_pharmacy_user and has_active_pharmacy(request.user))

