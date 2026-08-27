import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    PLATFORM_ADMIN = "PLATFORM_ADMIN", "Platform admin"
    PHARMACY_OWNER = "PHARMACY_OWNER", "Pharmacy owner"
    PHARMACY_STAFF = "PHARMACY_STAFF", "Pharmacy staff"
    DOCTOR = "DOCTOR", "Doctor"
    CUSTOMER = "CUSTOMER", "Customer"
    DRIVER = "DRIVER", "Delivery driver"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", UserRole.PLATFORM_ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(max_length=32, choices=UserRole.choices)
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", null=True, blank=True, on_delete=models.PROTECT, related_name="users")
    phone = models.CharField(max_length=40, blank=True, help_text="Contact number for deliveries. Not used for sign-in or verification.")
    email_verified = models.BooleanField(
        default=False, help_text="Shoppers must verify before checkout; other roles are created by staff and pre-verified."
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def mark_logged_in(self):
        self.last_login_at = timezone.now()
        self.last_login = self.last_login_at
        self.save(update_fields=["last_login_at", "last_login"])

    @property
    def is_platform_admin(self) -> bool:
        return self.role == UserRole.PLATFORM_ADMIN

    @property
    def is_pharmacy_user(self) -> bool:
        return self.role in {UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF}

    @property
    def is_pharmacy_owner(self) -> bool:
        return self.role == UserRole.PHARMACY_OWNER


class NotificationPreferences(models.Model):
    """
    Which notifications a shopper has asked to receive.

    A row per user rather than a JSON blob on User: each of these gates a
    different sending path (order lifecycle, dispatch, prescription expiry,
    refill due, marketing), and those queries need to filter on the individual
    flag. Absence of a row means "never chosen" and is read as the defaults
    below - see `for_user`.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="notification_preferences")
    order_updates = models.BooleanField(default=True)
    delivery_updates = models.BooleanField(default=True)
    prescription_reminders = models.BooleanField(default=True)
    refill_reminders = models.BooleanField(default=True)
    # Opt-in, not opt-out: the only one here that is marketing rather than
    # transactional, so it must never default to on.
    product_news = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def for_user(cls, user) -> "NotificationPreferences":
        preferences, _ = cls.objects.get_or_create(user=user)
        return preferences

    def __str__(self) -> str:
        return f"Notification preferences for {self.user.email}"
