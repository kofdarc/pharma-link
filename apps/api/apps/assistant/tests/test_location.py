"""
What must hold once the assistant knows where someone is:
  - "near me" resolves through one documented chain, and never invents a position
  - a position is search input, not identity: it reorders answers and unlocks nothing
  - the intent parser cannot set a location, only the request and the account can
  - "nearest pharmacy with everything on my prescription" reads only the caller's own scripts
  - a pharmacy that cannot cover the whole list is reported as partial, never rounded up
  - the prescription-only warning is stated whenever it applies, distance or not
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import ShopperLocation, UserRole
from apps.assistant import personas, services, tools
from apps.assistant.intents import get_intent
from apps.assistant.parsers.keyword import KeywordIntentParser
from apps.assistant.tools.base import ToolContext
from apps.common.location import coerce, resolve_origin
from apps.eprescriptions.models import Doctor, Prescription, PrescriptionItem
from apps.inventory.services.coverage import pharmacies_covering
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime
from apps.orders.models import DeliveryAddress
from apps.pharmacies.models import Pharmacy

# Two real Beirut areas about 3 km apart, so "nearer" is unambiguous.
HAMRA = (Decimal("33.8971"), Decimal("35.4805"))
ACHRAFIEH = (Decimal("33.8886"), Decimal("35.5175"))


def make_pharmacy(name: str, position, phone: str = "01000000") -> Pharmacy:
    return Pharmacy.objects.create(
        name=name, area="Hamra", city="Beirut", address=f"{name} street", phone=phone, latitude=position[0], longitude=position[1]
    )


def stock(pharmacy, medicine, user, units=20, price="5.00"):
    return create_inventory_batch(
        user=user,
        pharmacy=pharmacy,
        data={"medicine": medicine, "initial_quantity": units, "selling_price": Decimal(price), "expiry_date": timezone.localdate() + timedelta(days=400)},
    )


class CoerceTests(TestCase):
    """Client coordinates are cleaned before they are believed."""

    def test_rejects_unparseable_and_out_of_range_values(self):
        for latitude, longitude in [(None, None), ("", ""), ("abc", "def"), (91, 35), (33, 181), (-91, 0)]:
            self.assertIsNone(coerce(latitude, longitude), (latitude, longitude))

    def test_rejects_null_island(self):
        """(0, 0) is what a half-initialised client sends, and it is never a real fix here."""
        self.assertIsNone(coerce(0, 0))

    def test_accepts_strings_and_decimals(self):
        self.assertEqual(coerce("33.8971", "35.4805"), (33.8971, 35.4805))
        self.assertEqual(coerce(HAMRA[0], HAMRA[1]), (33.8971, 35.4805))


class OriginResolutionTests(TestCase):
    """The fallback chain, in order, and its refusal to guess past the end of it."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_no_position_anywhere_resolves_to_nothing(self):
        self.assertIsNone(resolve_origin(user=self.user))

    def test_anonymous_caller_with_no_coordinates_resolves_to_nothing(self):
        self.assertIsNone(resolve_origin(user=None))

    def test_request_coordinates_win_over_everything_on_file(self):
        ShopperLocation.objects.create(user=self.user, latitude=ACHRAFIEH[0], longitude=ACHRAFIEH[1])
        origin = resolve_origin(user=self.user, latitude=33.8971, longitude=35.4805)
        self.assertEqual(origin.source, "request")
        self.assertAlmostEqual(origin.latitude, 33.8971)

    def test_saved_location_is_used_when_the_request_carries_none(self):
        ShopperLocation.objects.create(user=self.user, latitude=ACHRAFIEH[0], longitude=ACHRAFIEH[1], label="Achrafieh")
        origin = resolve_origin(user=self.user)
        self.assertEqual(origin.source, "saved")
        self.assertIn("Achrafieh", origin.describe())

    def test_default_delivery_address_is_the_last_resort(self):
        DeliveryAddress.objects.create(
            user=self.user, contact_name="A", phone="03000000", address="x", area="Hamra", city="Beirut",
            latitude=HAMRA[0], longitude=HAMRA[1], is_default=True,
        )
        origin = resolve_origin(user=self.user)
        self.assertEqual(origin.source, "address")
        self.assertEqual(origin.describe(), "your default delivery address near Hamra")

    def test_nonsense_request_coordinates_fall_through_rather_than_being_believed(self):
        ShopperLocation.objects.create(user=self.user, latitude=ACHRAFIEH[0], longitude=ACHRAFIEH[1])
        self.assertEqual(resolve_origin(user=self.user, latitude=999, longitude=999).source, "saved")


class ShopperLocationApiTests(APITestCase):
    """Opt-in, overwritable, and genuinely deletable."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.client.force_authenticate(self.user)

    def test_nothing_on_file_reads_as_no_content_rather_than_an_empty_object(self):
        self.assertEqual(self.client.get("/api/shop/location/").status_code, 204)

    def test_put_stores_the_position_and_derives_the_label_server_side(self):
        response = self.client.put("/api/shop/location/", {"latitude": "33.8971", "longitude": "35.4805", "label": "Antarctica"}, format="json")
        self.assertEqual(response.status_code, 200)
        # The client asked for "Antarctica"; the label comes from the coordinates instead.
        self.assertEqual(response.data["label"], "Hamra")

    def test_put_replaces_rather_than_accumulating(self):
        self.client.put("/api/shop/location/", {"latitude": "33.8971", "longitude": "35.4805"}, format="json")
        self.client.put("/api/shop/location/", {"latitude": "33.8886", "longitude": "35.5175"}, format="json")
        self.assertEqual(ShopperLocation.objects.filter(user=self.user).count(), 1)
        self.assertEqual(ShopperLocation.objects.get(user=self.user).label, "Achrafieh")

    def test_a_new_fix_does_not_inherit_the_previous_one_s_accuracy(self):
        self.client.put("/api/shop/location/", {"latitude": "33.8971", "longitude": "35.4805", "accuracy_metres": 40}, format="json")
        response = self.client.put("/api/shop/location/", {"latitude": "33.8886", "longitude": "35.5175"}, format="json")
        self.assertIsNone(response.data["accuracy_metres"])

    def test_delete_forgets_it(self):
        self.client.put("/api/shop/location/", {"latitude": "33.8971", "longitude": "35.4805"}, format="json")
        self.assertEqual(self.client.delete("/api/shop/location/").status_code, 204)
        self.assertFalse(ShopperLocation.objects.filter(user=self.user).exists())

    def test_out_of_range_coordinates_are_rejected(self):
        self.assertEqual(self.client.put("/api/shop/location/", {"latitude": "120", "longitude": "35.4"}, format="json").status_code, 400)

    def test_signed_out_callers_have_no_location_to_read_or_write(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/shop/location/").status_code, 401)


class CoverageServiceTests(TestCase):
    """Whether one pharmacy can cover a whole list, and which one is nearest."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(email="staff@test.test", password="Password123!", role=UserRole.PHARMACY_STAFF)
        self.near = make_pharmacy("Near Pharmacy", HAMRA, "01000001")
        self.far = make_pharmacy("Far Pharmacy", ACHRAFIEH, "01000002")
        self.staff.pharmacy = self.near
        self.staff.save()

        self.otc = Medicine.objects.create(
            brand_name="Panadol", generic_name="Paracetamol", strength="500mg", form="tablet", price_regime=PriceRegime.FREE
        )
        self.rx = Medicine.objects.create(
            brand_name="Augmentin", generic_name="Amoxicillin", strength="1g", form="tablet",
            requires_prescription=True, price_regime=PriceRegime.FREE,
        )

    def test_a_pharmacy_holding_every_line_covers_everything(self):
        stock(self.near, self.otc, self.staff)
        stock(self.near, self.rx, self.staff)
        rows = pharmacies_covering(needs={str(self.otc.id): 2, str(self.rx.id): 2}, latitude=33.8971, longitude=35.4805)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["covers_everything"])
        self.assertEqual(rows[0]["missing"], [])
        self.assertEqual(rows[0]["requires_prescription"], ["Augmentin"])

    def test_a_pharmacy_holding_one_of_two_lines_is_partial_not_full(self):
        stock(self.near, self.otc, self.staff)
        rows = pharmacies_covering(needs={str(self.otc.id): 2, str(self.rx.id): 2}, latitude=33.8971, longitude=35.4805)
        self.assertFalse(rows[0]["covers_everything"])
        self.assertEqual(rows[0]["lines_covered"], 1)
        self.assertEqual([item["medicine"] for item in rows[0]["missing"]], ["Augmentin"])

    def test_holding_fewer_units_than_asked_for_is_short_not_covered(self):
        stock(self.near, self.otc, self.staff, units=1)
        rows = pharmacies_covering(needs={str(self.otc.id): 5}, latitude=33.8971, longitude=35.4805)
        self.assertFalse(rows[0]["covers_everything"])
        self.assertEqual(rows[0]["missing"][0]["reason"], "short")

    def test_full_coverage_outranks_a_nearer_partial_one(self):
        """One trip that works beats a shorter trip that does not."""
        stock(self.near, self.otc, self.staff)
        stock(self.far, self.otc, self.staff)
        stock(self.far, self.rx, self.staff)
        rows = pharmacies_covering(needs={str(self.otc.id): 1, str(self.rx.id): 1}, latitude=33.8971, longitude=35.4805)
        self.assertEqual(rows[0]["pharmacy"]["name"], "Far Pharmacy")
        self.assertTrue(rows[0]["covers_everything"])

    def test_between_two_full_matches_the_nearer_one_wins(self):
        for pharmacy in (self.near, self.far):
            stock(pharmacy, self.otc, self.staff)
        rows = pharmacies_covering(needs={str(self.otc.id): 1}, latitude=33.8971, longitude=35.4805)
        self.assertEqual([row["pharmacy"]["name"] for row in rows], ["Near Pharmacy", "Far Pharmacy"])
        self.assertLess(rows[0]["distance_km"], rows[1]["distance_km"])

    def test_without_a_position_pharmacies_are_still_returned_with_no_distance(self):
        stock(self.near, self.otc, self.staff)
        rows = pharmacies_covering(needs={str(self.otc.id): 1})
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["distance_km"])

    def test_reserved_units_are_not_offered(self):
        batch = stock(self.near, self.otc, self.staff, units=4)
        batch.reserved_quantity = 4
        batch.save(update_fields=["reserved_quantity"])
        self.assertEqual(pharmacies_covering(needs={str(self.otc.id): 1}), [])

    def test_the_public_cap_bounds_what_is_offered(self):
        self.near.public_max_quantity_per_item = 3
        self.near.save(update_fields=["public_max_quantity_per_item"])
        stock(self.near, self.otc, self.staff, units=500)
        rows = pharmacies_covering(needs={str(self.otc.id): 1}, latitude=33.8971, longitude=35.4805)
        self.assertEqual(rows[0]["lines"][0]["available_up_to"], 3)


class PharmacyFinderTests(TestCase):
    """"Which pharmacies are near me" - and what happens to the ones we cannot place."""

    def setUp(self):
        self.located = make_pharmacy("Near Pharmacy", HAMRA, "01000010")
        self.distant = make_pharmacy("Far Pharmacy", ACHRAFIEH, "01000011")
        self.unplaced = Pharmacy.objects.create(
            name="Unplaced Pharmacy", area="Hamra", city="Beirut", address="x", phone="01000012"
        )

    def test_without_a_position_nothing_claims_to_be_ranked_by_distance(self):
        from apps.assistant.tools import public

        result = public.find_pharmacies(ToolContext())
        self.assertFalse(result["located"])
        self.assertTrue(all(row["distance_km"] is None for row in result["pharmacies"]))

    def test_with_a_position_the_nearest_comes_first(self):
        from apps.assistant.tools import public

        result = public.find_pharmacies(ToolContext(origin=resolve_origin(latitude=33.8971, longitude=35.4805)))
        self.assertTrue(result["located"])
        self.assertEqual(result["pharmacies"][0]["name"], "Near Pharmacy")

    def test_a_pharmacy_with_no_coordinates_is_ranked_last_not_hidden(self):
        """Sharing a location must not silently shrink the directory."""
        from apps.assistant.tools import public

        result = public.find_pharmacies(ToolContext(origin=resolve_origin(latitude=33.8971, longitude=35.4805)))
        names = [row["name"] for row in result["pharmacies"]]
        self.assertIn("Unplaced Pharmacy", names)
        self.assertEqual(names[-1], "Unplaced Pharmacy")
        self.assertEqual(result["total_found"], 3)


class PrescriptionCoverageToolTests(TestCase):
    """The patient's own script, and only theirs."""

    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user(email="staff2@test.test", password="Password123!", role=UserRole.PHARMACY_STAFF)
        self.patient = User.objects.create_user(email="patient@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.other_patient = User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.pharmacy = make_pharmacy("Near Pharmacy", HAMRA, "01000003")
        self.staff.pharmacy = self.pharmacy
        self.staff.save()

        self.doctor = Doctor.objects.create(license_number="L1", full_name="Rita Khoury", email="dr@test.test")
        self.medicine = Medicine.objects.create(
            brand_name="Augmentin", generic_name="Amoxicillin", strength="1g", form="tablet",
            requires_prescription=True, price_regime=PriceRegime.FREE,
        )
        stock(self.pharmacy, self.medicine, self.staff)

    def _prescription(self, email: str) -> Prescription:
        prescription = Prescription.objects.create(
            doctor=self.doctor, code=f"RX{email[:4]}", secret_hash="x" * 64, pin_hash="y",
            patient_name="Patient", patient_email=email, valid_until=timezone.now() + timedelta(days=20),
        )
        PrescriptionItem.objects.create(prescription=prescription, medicine=self.medicine, medicine_text="Augmentin 1g", quantity_prescribed=6)
        return prescription

    def test_finds_the_pharmacy_that_covers_the_whole_script(self):
        self._prescription(self.patient.email)
        result = tools.get("prescription_coverage").handler(
            ToolContext(user=self.patient, origin=resolve_origin(user=None, latitude=33.8971, longitude=35.4805))
        )
        self.assertEqual(len(result["full_coverage"]), 1)
        self.assertEqual(result["full_coverage"][0]["pharmacy"]["name"], "Near Pharmacy")
        self.assertTrue(result["located"])

    def test_another_patients_prescription_is_invisible(self):
        self._prescription(self.other_patient.email)
        result = tools.get("prescription_coverage").handler(ToolContext(user=self.patient))
        self.assertIsNone(result["prescription"])
        self.assertEqual(result["reason"], "none_valid")

    def test_a_code_in_the_message_cannot_widen_the_search(self):
        """The code narrows the caller's own scripts; it is never a key into anyone else's."""
        theirs = self._prescription(self.other_patient.email)
        result = tools.get("prescription_coverage").handler(ToolContext(user=self.patient, slots={"reference": theirs.code}))
        self.assertIsNone(result["prescription"])

    def test_an_expired_prescription_is_not_offered(self):
        prescription = self._prescription(self.patient.email)
        prescription.valid_until = timezone.now() - timedelta(days=1)
        prescription.save(update_fields=["valid_until"])
        self.assertIsNone(tools.get("prescription_coverage").handler(ToolContext(user=self.patient))["prescription"])

    def test_a_line_with_no_catalogue_link_is_reported_unmatched_never_substituted(self):
        prescription = self._prescription(self.patient.email)
        PrescriptionItem.objects.create(prescription=prescription, medicine=None, medicine_text="Some compounded cream", quantity_prescribed=1)
        result = tools.get("prescription_coverage").handler(ToolContext(user=self.patient))
        self.assertEqual([item["medicine"] for item in result["unmatched"]], ["Some compounded cream"])

    def test_already_dispensed_units_are_not_sourced_again(self):
        prescription = self._prescription(self.patient.email)
        item = prescription.items.first()
        item.quantity_dispensed = item.quantity_prescribed
        item.save(update_fields=["quantity_dispensed"])
        result = tools.get("prescription_coverage").handler(ToolContext(user=self.patient))
        self.assertEqual(result["lines_outstanding"], 0)

    def test_the_guest_persona_cannot_reach_this_tool(self):
        with self.assertRaises(tools.ToolNotAllowed):
            tools.execute("prescription_coverage", allowed=frozenset({"search_availability"}), context=ToolContext(user=self.patient))


class LocationAwareRenderingTests(TestCase):
    """What the person actually reads: how far, and the warning that saves a wasted trip."""

    def test_availability_states_the_distance_and_warns_about_prescription_only(self):
        reply = get_intent("search_availability").render(
            {
                "query": "augmentin",
                "located": True,
                "total_found": 1,
                "results": [
                    {
                        "medicine": "Augmentin", "strength": "1g", "requires_prescription": True,
                        "pharmacy": "Near Pharmacy", "area": "Hamra", "availability": "Available",
                        "available_up_to": 10, "unit_price": "12.00", "distance_km": 1.4,
                    }
                ],
            },
            {},
        )
        self.assertIn("about 1.4 km away", reply)
        self.assertIn("prescription-only", reply)

    def test_availability_never_claims_nearest_without_a_position(self):
        reply = get_intent("search_availability").render(
            {
                "query": "panadol",
                "located": False,
                "total_found": 1,
                "results": [
                    {
                        "medicine": "Panadol", "strength": "500mg", "requires_prescription": False,
                        "pharmacy": "Near Pharmacy", "area": "Hamra", "availability": "Available",
                        "available_up_to": 10, "unit_price": "5.00", "distance_km": None,
                    }
                ],
            },
            {},
        )
        # It may still offer to do better; what it must not do is present this row as nearest.
        self.assertNotIn("The closest is", reply)
        self.assertIn("Share your location", reply)

    def test_coverage_reply_names_the_pharmacy_the_distance_and_the_script(self):
        reply = get_intent("prescription_coverage").render(
            {
                "prescription": {"code": "RX123", "doctor": "Rita Khoury", "status": "Issued", "valid_until": "", "days_left": 20},
                "located": True,
                "lines_outstanding": 2,
                "matched": [], "unmatched": [],
                "full_coverage": [
                    {
                        "pharmacy": {"name": "Near Pharmacy", "area": "Hamra", "opens_at": "08:00", "closes_at": "21:00"},
                        "distance_km": 0.8, "covers_everything": True, "lines_covered": 2, "missing": [],
                    }
                ],
                "partial_coverage": [],
                "total_found": 1,
            },
            {},
        )
        self.assertIn("Near Pharmacy", reply)
        self.assertIn("under 1 km away", reply)
        self.assertIn("Bring prescription RX123", reply)

    def test_coverage_reply_says_plainly_when_no_single_pharmacy_has_it_all(self):
        reply = get_intent("prescription_coverage").render(
            {
                "prescription": {"code": "RX123", "doctor": "Rita Khoury", "status": "Issued", "valid_until": "", "days_left": 20},
                "located": True,
                "lines_outstanding": 3,
                "matched": [], "unmatched": [],
                "full_coverage": [],
                "partial_coverage": [
                    {
                        "pharmacy": {"name": "Near Pharmacy", "area": "Hamra", "opens_at": "08:00", "closes_at": "21:00"},
                        "distance_km": 0.8, "covers_everything": False, "lines_covered": 2,
                        "missing": [{"medicine": "Augmentin", "requested": 1, "reason": "none"}],
                    }
                ],
                "total_found": 1,
            },
            {},
        )
        self.assertIn("No single pharmacy nearby", reply)
        self.assertIn("Augmentin", reply)


class LocationRoutingTests(TestCase):
    """The phrasings this feature exists to answer have to actually route."""

    def setUp(self):
        self.parser = KeywordIntentParser()

    def test_nearest_pharmacy_with_a_named_medicine_is_an_availability_question(self):
        for message in (
            "which is the closest pharmacy to me that has this medicine",
            "which is the closest pharmacy that has amoxicillin",
            "nearest pharmacy with panadol in stock",
        ):
            result = self.parser.parse(message, personas.PERSONAS[personas.GUEST])
            self.assertIsNotNone(result, message)
            self.assertEqual(result.intent, "search_availability", message)

    def test_whole_prescription_questions_reach_the_coverage_intent(self):
        for message in (
            "which pharmacy near me has everything on my prescription",
            "nearest pharmacy that has all the medicine in my prescription",
        ):
            result = self.parser.parse(message, personas.PERSONAS[personas.CUSTOMER])
            self.assertIsNotNone(result, message)
            self.assertEqual(result.intent, "prescription_coverage", message)

    def test_plain_expiry_questions_still_reach_the_status_intent(self):
        """The new intent must not swallow the prescription question that was already here."""
        result = self.parser.parse("when does my prescription expire", personas.PERSONAS[personas.CUSTOMER])
        self.assertEqual(result.intent, "prescription_status")

    def test_the_guest_persona_cannot_route_to_a_patient_only_intent(self):
        result = self.parser.parse("which pharmacy near me has everything on my prescription", personas.PERSONAS[personas.GUEST])
        self.assertNotEqual(getattr(result, "intent", None), "prescription_coverage")


class ChatLocationTests(APITestCase):
    """Coordinates on the wire are search input, and nothing more."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="shopper2@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_coordinates_are_accepted_and_reported_back(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/assistant/chat/", {"message": "which pharmacies are near me", "latitude": 33.8971, "longitude": 35.4805}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["location_used"], "your current location near Hamra")

    def test_out_of_range_coordinates_are_rejected_by_the_serializer(self):
        response = self.client.post("/api/assistant/chat/", {"message": "hello", "latitude": 500, "longitude": 35.0}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_coordinates_do_not_widen_the_persona(self):
        """A signed-out caller with a precise position is still a guest."""
        response = self.client.post(
            "/api/assistant/chat/", {"message": "where is my order", "latitude": 33.8971, "longitude": 35.4805}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["persona"], personas.GUEST)

    def test_a_message_cannot_set_a_location(self):
        """Only the request field and the account reach `origin` - never the parsed slots."""
        context = ToolContext(user=self.user, slots={"latitude": 0, "longitude": 0, "query": "panadol"})
        self.assertEqual(context.coordinates, (None, None))
