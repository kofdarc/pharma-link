"""
What must hold:
  - a shopper registering gets an unverified account and a verification email
  - checkout is blocked until that email is verified, and unblocked once it is
  - password reset always answers the same way whether or not the email exists
  - a valid reset token actually changes the password and kills existing sessions
  - a tampered/expired token is rejected
"""

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole


class RegistrationVerificationTests(APITestCase):
    def test_registering_creates_an_unverified_account_and_sends_a_link(self):
        response = self.client.post(
            "/api/auth/register/", {"email": "new@shopper.test", "password": "Str0ngPassphrase!"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["user"]["email_verified"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("new@shopper.test", mail.outbox[0].to)

    def test_verifying_with_a_valid_link_flips_the_flag(self):
        User = get_user_model()
        user = User.objects.create_user(email="pending@shopper.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.post("/api/auth/verify-email/", {"uid": uid, "token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

    def test_a_tampered_token_is_rejected(self):
        User = get_user_model()
        user = User.objects.create_user(email="pending2@shopper.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=False)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        response = self.client.post("/api/auth/verify-email/", {"uid": uid, "token": "not-a-real-token"}, format="json")

        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)


class CheckoutVerificationGateTests(APITestCase):
    def setUp(self):
        from decimal import Decimal

        from apps.inventory.services.stock import create_inventory_batch
        from apps.medicines.models import Medicine
        from apps.pharmacies.models import Pharmacy
        from django.utils import timezone

        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal("33.8975"), longitude=Decimal("35.4790"),
        )
        owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine, "initial_quantity": 10,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"), "selling_price": Decimal("2.25"),
            },
        )
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=False)
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="1", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal("33.8991"), longitude=Decimal("35.4772"), is_default=True,
        )

    def test_unverified_shopper_cannot_check_out(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post(
            "/api/shop/orders/", {"items": [{"medicine": str(self.medicine.id), "quantity": 1}], "address": str(self.address.id)}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_verified_shopper_can_check_out(self):
        self.shopper.email_verified = True
        self.shopper.save(update_fields=["email_verified"])
        self.client.force_authenticate(self.shopper)
        response = self.client.post(
            "/api/shop/orders/", {"items": [{"medicine": str(self.medicine.id), "quantity": 1}], "address": str(self.address.id)}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)


class PasswordResetTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="shopper@test.test", password="OldPassword123!", role=UserRole.CUSTOMER)

    def test_request_answers_the_same_way_whether_or_not_the_account_exists(self):
        known = self.client.post("/api/auth/password-reset/", {"email": "shopper@test.test"}, format="json")
        unknown = self.client.post("/api/auth/password-reset/", {"email": "nobody@test.test"}, format="json")

        self.assertEqual(known.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(known.data["detail"], unknown.data["detail"])
        self.assertEqual(len(mail.outbox), 1)  # only the real account gets an email

    def test_a_valid_token_resets_the_password_and_kills_existing_sessions(self):
        token_obj = Token.objects.create(user=self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "BrandNewPassphrase1!"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(pk=token_obj.pk).exists())
        login = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "BrandNewPassphrase1!"}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_an_invalid_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.post("/api/auth/password-reset/confirm/", {"uid": uid, "token": "garbage", "password": "BrandNewPassphrase1!"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPassword123!"))


class RoleChangeAuditTests(APITestCase):
    def test_promoting_a_user_writes_an_audit_log(self):
        from apps.audit.models import AuditLog

        User = get_user_model()
        admin = User.objects.create_user(email="admin@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        target = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.client.force_authenticate(admin)

        response = self.client.patch(f"/api/admin/users/{target.id}/", {"is_active": False}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(AuditLog.objects.filter(action="accounts.user_updated", entity_id=str(target.id)).exists())

    def test_no_op_update_does_not_write_an_audit_log(self):
        from apps.audit.models import AuditLog

        User = get_user_model()
        admin = User.objects.create_user(email="admin2@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        target = User.objects.create_user(email="shopper2@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.client.force_authenticate(admin)

        response = self.client.patch(f"/api/admin/users/{target.id}/", {"first_name": "Same"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action="accounts.user_updated", entity_id=str(target.id)).exists())
