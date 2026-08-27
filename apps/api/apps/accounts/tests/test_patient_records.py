"""
The records a patient owns about themselves.

These back the account screens, which used to keep all of this in the browser's
localStorage - meaning a patient's saved cards, contact number and notification
choices existed only on the device that entered them. What must hold now:

  - a patient can change their own name and phone, and nothing else about the
    account the platform decides (role, pharmacy, verification, email)
  - saved payment methods are the patient's own and never another patient's
  - there is exactly one default payment method, however the edits arrive
  - saved cards carry no payment credentials
"""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import NotificationPreferences, UserRole
from apps.payments.models import SavedPaymentMethod


class OwnProfileTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(
            email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER, first_name="Rana", last_name="Aoun"
        )
        self.client.force_authenticate(self.shopper)

    def test_a_patient_can_change_their_own_name_and_phone(self):
        response = self.client.patch("/api/auth/me/", {"first_name": "Rana", "phone": "+961-3-111-222"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.shopper.refresh_from_db()
        self.assertEqual(self.shopper.phone, "+961-3-111-222")
        self.assertEqual(response.data["phone"], "+961-3-111-222")

    def test_a_patient_cannot_promote_themselves_or_verify_their_own_email(self):
        # These are decisions the platform makes about an account, not decisions
        # the account holder makes - so the serializer must not accept them even
        # though UserSerializer exposes them for admins.
        self.client.patch(
            "/api/auth/me/",
            {"role": UserRole.PLATFORM_ADMIN, "email_verified": True, "email": "someone.else@test.local"},
            format="json",
        )

        self.shopper.refresh_from_db()
        self.assertEqual(self.shopper.role, UserRole.CUSTOMER)
        self.assertFalse(self.shopper.email_verified)
        self.assertEqual(self.shopper.email, "shopper@test.local")


class NotificationPreferenceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.client.force_authenticate(self.shopper)

    def test_preferences_exist_on_first_read_without_having_been_set(self):
        response = self.client.get("/api/auth/notification-preferences/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["order_updates"])
        # The only marketing flag here, so it must be opt-in rather than opt-out.
        self.assertFalse(response.data["product_news"])

    def test_a_preference_can_be_turned_off_and_stays_off(self):
        self.client.patch("/api/auth/notification-preferences/", {"refill_reminders": False}, format="json")

        self.assertFalse(NotificationPreferences.for_user(self.shopper).refill_reminders)
        self.assertFalse(self.client.get("/api/auth/notification-preferences/").data["refill_reminders"])


class SavedPaymentMethodTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.other = User.objects.create_user(email="other@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.client.force_authenticate(self.shopper)

    def add(self, **overrides):
        payload = {"kind": "CARD", "brand": "Visa", "last4": "4242", "expiry": "08/29", **overrides}
        return self.client.post("/api/shop/saved-payment-methods/", payload, format="json")

    def test_the_first_method_saved_becomes_the_default(self):
        # An account holding methods but no default has nothing to pre-select at
        # checkout, so the first one saved is the default whether asked for or not.
        response = self.add(is_default=False)

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["is_default"])

    def test_only_one_method_is_ever_the_default(self):
        self.add()
        second = self.add(brand="Mastercard", last4="1111", is_default=True)

        defaults = SavedPaymentMethod.objects.filter(user=self.shopper, is_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(str(defaults.first().id), second.data["id"])

    def test_removing_the_default_promotes_another_method(self):
        default = self.add()
        self.add(kind="CASH")

        self.client.delete(f"/api/shop/saved-payment-methods/{default.data['id']}/")

        self.assertEqual(SavedPaymentMethod.objects.filter(user=self.shopper, is_default=True).count(), 1)

    def test_a_card_must_be_recognisable_or_it_is_not_worth_saving(self):
        response = self.add(brand="", last4="", expiry="")

        self.assertEqual(response.status_code, 400)

    def test_a_card_stores_four_digits_and_nothing_that_could_charge_it(self):
        self.add()

        saved = SavedPaymentMethod.objects.get(user=self.shopper)
        self.assertEqual(saved.last4, "4242")
        self.assertEqual(saved.provider_token, "", "no gateway is connected, so there is nothing to charge against")

    def test_cash_carries_no_card_detail_even_if_some_is_sent(self):
        self.add(kind="CASH", brand="Visa", last4="9999", expiry="01/30")

        saved = SavedPaymentMethod.objects.get(user=self.shopper, kind=SavedPaymentMethod.Kind.CASH)
        self.assertEqual((saved.brand, saved.last4, saved.expiry), ("", "", ""))

    def test_one_patient_never_sees_or_touches_another_patients_methods(self):
        mine = self.add()
        self.client.force_authenticate(self.other)

        listed = self.client.get("/api/shop/saved-payment-methods/")
        fetched = self.client.get(f"/api/shop/saved-payment-methods/{mine.data['id']}/")

        self.assertEqual(listed.data["results"], [])
        self.assertEqual(fetched.status_code, 404)
