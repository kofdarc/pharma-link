"""Confirms Accept-Language actually switches translated API responses, not just that
the translation files exist and compile."""

from django.test import TestCase


class I18nSmokeTest(TestCase):
    def test_error_message_translates_to_french(self):
        response = self.client.post(
            "/api/auth/login/", {"email": "x@x.com", "password": "wrong"}, content_type="application/json", HTTP_ACCEPT_LANGUAGE="fr"
        )
        self.assertEqual(response.json()["non_field_errors"], ["E-mail ou mot de passe invalide."])

    def test_error_message_translates_to_arabic(self):
        response = self.client.post(
            "/api/auth/login/", {"email": "x@x.com", "password": "wrong"}, content_type="application/json", HTTP_ACCEPT_LANGUAGE="ar"
        )
        self.assertEqual(response.json()["non_field_errors"], ["البريد الإلكتروني أو كلمة المرور غير صحيحة."])

    def test_default_language_is_english(self):
        response = self.client.post("/api/auth/login/", {"email": "x@x.com", "password": "wrong"}, content_type="application/json")
        self.assertEqual(response.json()["non_field_errors"], ["Invalid email or password."])
