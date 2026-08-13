"""
What must hold:
  - logging in returns a token that authenticates subsequent requests
  - an expired token is rejected, and deleted so it cannot be replayed
  - logging in again after expiry issues a fresh, working token rather than the dead one
  - repeated login attempts are rate limited
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole


class TokenExpiryTests(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_login_issues_a_working_token(self):
        response = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "Password123!"}, format="json")
        self.assertEqual(response.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_expired_token_is_rejected_and_deleted(self):
        token = Token.objects.create(user=self.user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(hours=25))

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_login_after_expiry_reissues_a_fresh_token(self):
        stale = Token.objects.create(user=self.user)
        Token.objects.filter(pk=stale.pk).update(created=timezone.now() - timedelta(hours=25))

        response = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "Password123!"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["token"], stale.key)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    @override_settings(AUTH_TOKEN_TTL_HOURS=24)
    def test_a_fresh_token_is_not_treated_as_expired(self):
        response = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "Password123!"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)


class LoginThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_repeated_login_attempts_are_throttled(self):
        for _ in range(10):
            response = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "wrong"}, format="json")
            self.assertEqual(response.status_code, 400)

        throttled = self.client.post("/api/auth/login/", {"email": self.user.email, "password": "wrong"}, format="json")
        self.assertEqual(throttled.status_code, 429)
