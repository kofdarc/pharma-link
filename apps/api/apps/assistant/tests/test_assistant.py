"""
What must hold:
  - the persona comes from the authenticated user's role, never from anything the client sends
  - a persona cannot reach a tool outside its own intent list, even when asked for one directly
  - pharmacy staff see only their own pharmacy's stock; patients see only their own orders
  - a conversation id is not resumable by anyone but the party it was issued to
  - the keyword router answers the phrasings it claims to, and abstains rather than guessing
  - the clinical and emergency redirects are never reachable by stray keyword overlap
  - a model parser proposing an out-of-persona intent is dropped, not obeyed
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.assistant import personas, services, tools
from apps.assistant.intents import get_intent
from apps.assistant.models import AssistantConversation
from apps.assistant.parsers.base import ParseResult
from apps.assistant.parsers.keyword import KeywordIntentParser
from apps.assistant.parsers.openrouter import OpenRouterIntentParser
from apps.assistant.tools.base import ToolContext
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime
from apps.pharmacies.models import Pharmacy

HAMRA = (Decimal("33.8975"), Decimal("35.4790"))


def make_pharmacy(name: str, phone: str) -> Pharmacy:
    return Pharmacy.objects.create(
        name=name, area="Hamra", city="Beirut", address=f"{name} street", phone=phone, latitude=HAMRA[0], longitude=HAMRA[1]
    )


class PersonaResolutionTests(TestCase):
    """The persona is a function of the token and nothing else."""

    def setUp(self):
        self.User = get_user_model()

    def test_anonymous_gets_the_guest_persona(self):
        self.assertEqual(personas.persona_for(None).key, personas.GUEST)

    def test_each_role_maps_to_its_own_persona(self):
        expected = {
            UserRole.CUSTOMER: personas.CUSTOMER,
            UserRole.DOCTOR: personas.DOCTOR,
            UserRole.PHARMACY_OWNER: personas.PHARMACY,
            UserRole.PHARMACY_STAFF: personas.PHARMACY,
            UserRole.PLATFORM_ADMIN: personas.ADMIN,
            UserRole.DRIVER: personas.DRIVER,
        }
        for role, persona_key in expected.items():
            user = self.User.objects.create_user(email=f"{role.lower()}@test.test", password="Password123!", role=role)
            self.assertEqual(personas.persona_for(user).key, persona_key, role)

    def test_personas_only_name_intents_that_exist(self):
        from apps.assistant.intents import INTENTS

        for persona in personas.PERSONAS.values():
            for name in persona.intents:
                self.assertIn(name, INTENTS, f"{persona.key} names unknown intent {name}")

    def test_guest_persona_reaches_no_personal_tool(self):
        guest_tools = services._allowed_tools(personas.PERSONAS[personas.GUEST])
        # cart_add is here too: it reads the public availability view and writes nothing (the
        # cart is browser-local), so it carries no personal data to leak.
        self.assertEqual(guest_tools, {"search_availability", "medicine_details", "find_pharmacies", "cart_add"})


class ToolAllowlistTests(TestCase):
    """The allowlist is enforcement, not documentation."""

    def setUp(self):
        User = get_user_model()
        self.pharmacy = make_pharmacy("Cedar Care", "+961-1-000-000")
        self.owner = User.objects.create_user(email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_customer_persona_cannot_execute_a_pharmacy_tool(self):
        allowed = frozenset(services._allowed_tools(personas.PERSONAS[personas.CUSTOMER]))
        with self.assertRaises(tools.ToolNotAllowed):
            tools.execute("stock_lookup", allowed=allowed, context=ToolContext(user=self.shopper, slots={"query": "panadol"}))

    def test_guest_persona_cannot_execute_a_patient_tool(self):
        allowed = frozenset(services._allowed_tools(personas.PERSONAS[personas.GUEST]))
        with self.assertRaises(tools.ToolNotAllowed):
            tools.execute("my_orders", allowed=allowed, context=ToolContext(user=None, slots={}))

    def test_unknown_tool_name_is_rejected(self):
        with self.assertRaises(tools.ToolNotAllowed):
            tools.execute("drop_everything", allowed=frozenset({"drop_everything"}), context=ToolContext(user=self.owner, slots={}))


class TenantScopingTests(TestCase):
    """Every handler anchors on the caller before it considers anything they typed."""

    def setUp(self):
        User = get_user_model()
        self.pharmacy = make_pharmacy("Cedar Care", "+961-1-000-000")
        self.other = make_pharmacy("Rival Pharmacy", "+961-1-000-001")
        self.owner = User.objects.create_user(email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.rival = User.objects.create_user(email="owner@rival.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.other)
        self.medicine = Medicine.objects.create(
            brand_name="Panadol", generic_name="Paracetamol", strength="500mg", form="tablet",
            price_regime=PriceRegime.REGULATED, regulated_price=Decimal("5.00"),
        )
        create_inventory_batch(
            user=self.rival,
            pharmacy=self.other,
            data={"medicine": self.medicine, "initial_quantity": 99, "selling_price": Decimal("5.00"), "expiry_date": timezone.localdate() + timedelta(days=400)},
        )

    def test_pharmacy_stock_lookup_cannot_see_another_pharmacy(self):
        from apps.assistant.tools import pharmacy as pharmacy_tools

        result = pharmacy_tools.stock_lookup(ToolContext(user=self.owner, slots={"query": "Panadol"}))
        self.assertEqual(result["batches"], [])
        self.assertEqual(result["total_quantity"], 0)

        rival_result = pharmacy_tools.stock_lookup(ToolContext(user=self.rival, slots={"query": "Panadol"}))
        self.assertEqual(rival_result["total_quantity"], 99)

    def test_patient_order_lookup_is_anchored_on_the_caller(self):
        from apps.assistant.tools import customer as customer_tools

        User = get_user_model()
        shopper = User.objects.create_user(email="a@test.test", password="Password123!", role=UserRole.CUSTOMER)
        result = customer_tools.my_orders(ToolContext(user=shopper, slots={"reference": "HC-"}))
        self.assertEqual(result["orders"], [])


class KeywordRouterTests(TestCase):
    """Precision matters more than recall here: abstaining is free, being wrong is not."""

    def setUp(self):
        self.parser = KeywordIntentParser()

    def assert_intent(self, message: str, persona_key: str, expected: str):
        result = self.parser.parse(message, personas.PERSONAS[persona_key])
        self.assertIsNotNone(result, f"{message!r} matched nothing")
        self.assertEqual(result.intent, expected, f"{message!r} -> {result.intent}")

    def test_patient_phrasings(self):
        self.assert_intent("where is my order", personas.CUSTOMER, "order_status")
        self.assert_intent("when does my prescription expire", personas.CUSTOMER, "prescription_status")
        self.assert_intent("when is my next refill", personas.CUSTOMER, "refill_status")

    def test_pharmacy_phrasings(self):
        self.assert_intent("what is running low", personas.PHARMACY, "stock_alerts")
        self.assert_intent("how many panadol do we have in stock", personas.PHARMACY, "stock_lookup")
        self.assert_intent("how did we trade over the last 30 days", personas.PHARMACY, "sales_summary")

    def test_admin_and_driver_phrasings(self):
        self.assert_intent("how many applications are pending", personas.ADMIN, "pending_applications")
        self.assert_intent("what is my next stop", personas.DRIVER, "next_stop")

    def test_signed_out_visitor_asking_about_their_order_is_told_to_sign_in(self):
        self.assert_intent("where is my order", personas.GUEST, "sign_in_needed")

    def test_medicine_name_survives_as_a_slot(self):
        result = self.parser.parse("how many panadol do we have in stock", personas.PERSONAS[personas.PHARMACY])
        self.assertEqual(result.slots.get("query"), "panadol")

    def test_duration_becomes_a_days_slot(self):
        result = self.parser.parse("how did we trade over the last 2 weeks", personas.PERSONAS[personas.PHARMACY])
        self.assertEqual(result.slots.get("days"), 14)

    def test_it_abstains_rather_than_guessing(self):
        for persona_key, message in (
            (personas.CUSTOMER, "asdfgh"),
            (personas.CUSTOMER, "thanks!"),
            (personas.CUSTOMER, "the weather is nice today"),
            (personas.PHARMACY, "ok"),
            (personas.GUEST, "lorem ipsum dolor"),
        ):
            self.assertIsNone(self.parser.parse(message, personas.PERSONAS[persona_key]), message)

    def test_every_suggestion_chip_routes(self):
        """
        A chip is a promise. Offering one that comes back "I couldn't work out what you're
        after" is worse than offering nothing, so the suggested phrasings are held to the
        router rather than written for the reader alone.
        """
        for persona in personas.PERSONAS.values():
            for chip in persona.suggestions:
                result = self.parser.parse(chip, persona)
                got = result.intent if result else "ABSTAIN"
                self.assertNotIn(got, ("ABSTAIN", "unknown", "clarify"), f"{persona.key} chip {chip!r} -> {got}")

    def test_routing_table(self):
        """The phrasings each persona is expected to handle, in one reviewable place."""
        for persona_key, message, expected in (
            (personas.GUEST, "how much is panadol", "search_availability"),
            (personas.GUEST, "who has augmentin", "search_availability"),
            (personas.GUEST, "is amoxicillin available anywhere", "search_availability"),
            (personas.GUEST, "do I need a prescription for augmentin", "prescription_required"),
            (personas.GUEST, "is panadol over the counter", "prescription_required"),
            (personas.GUEST, "any pharmacy open now", "find_pharmacies"),
            (personas.GUEST, "how does delivery work", "how_it_works"),
            (personas.CUSTOMER, "when will my delivery arrive", "order_status"),
            (personas.CUSTOMER, "track my order", "order_status"),
            (personas.CUSTOMER, "is my prescription still valid", "prescription_status"),
            (personas.CUSTOMER, "how much is panadol", "search_availability"),
            (personas.CUSTOMER, "add panadol to my cart", "add_to_cart"),
            (personas.CUSTOMER, "add the cheapest vitamin c to my basket", "add_to_cart"),
            (personas.GUEST, "add panadol to my cart", "add_to_cart"),
            (personas.PHARMACY, "anything expiring soon", "stock_alerts"),
            (personas.PHARMACY, "sales this month", "sales_summary"),
            (personas.PHARMACY, "any online orders waiting", "incoming_orders"),
            (personas.DOCTOR, "how many patients do I have", "my_patients"),
            (personas.ADMIN, "how many drivers are online", "dispatch_snapshot"),
            (personas.ADMIN, "what happened recently", "recent_activity"),
            (personas.DRIVER, "how many stops are left", "my_route"),
        ):
            self.assert_intent(message, persona_key, expected)

    def test_clinical_questions_reach_the_redirect_without_a_model(self):
        for message in ("what dose should I take", "is it safe to take with panadol", "can I take ibuprofen instead"):
            self.assert_intent(message, personas.CUSTOMER, "clinical_question")

    def test_emergencies_reach_the_emergency_redirect(self):
        for message in ("I think I overdosed", "she can't breathe", "he has chest pain"):
            self.assert_intent(message, personas.CUSTOMER, "emergency")

    def test_emergencies_are_caught_in_arabic_and_french_without_a_model(self):
        """
        Regression: an Arabic overdose message reached the emergency redirect only via the
        paid OpenRouter fallback in a live check - the free keyword tier missed it, because
        the phrase lists were English-only. If that fallback is ever off, unset, or down, a
        non-English emergency must not silently fall through to "unknown".
        """
        for message in (
            "أعتقد أنني تناولت جرعة زائدة، ماذا أفعل الآن؟",  # "I think I overdosed, what do I do now?"
            "هو فاقد الوعي ولا يستطيع التنفس",  # "he is unconscious and can't breathe"
            "je pense que j'ai fait une overdose",  # "I think I overdosed"
            "elle est inconsciente et ne peut pas respirer",  # "she is unconscious and can't breathe"
        ):
            self.assert_intent(message, personas.CUSTOMER, "emergency")

    def test_clinical_questions_are_caught_in_arabic_and_french_without_a_model(self):
        for message in (
            "كم الجرعة التي يجب أن آخذها؟",  # "what dose should I take?"
            "هل يمكنني أخذ هذا وأنا حامل؟",  # "can I take this while pregnant?"
            "quelle dose de paracétamol dois-je prendre?",  # "what dose of paracetamol should I take?"
            "puis-je prendre ceci si je suis enceinte?",  # "can I take this if I'm pregnant?"
        ):
            self.assert_intent(message, personas.CUSTOMER, "clinical_question")

    def test_a_clinical_phrase_outranks_a_product_lookup(self):
        # Names a product the catalogue would happily answer, but asks a dosage question.
        self.assert_intent("what dose of panadol should I take", personas.GUEST, "clinical_question")

    def test_a_bare_greeting_is_understood(self):
        for message in ("hi", "hello", "hey there"):
            self.assert_intent(message, personas.GUEST, "greeting")

    def test_a_persona_never_matches_another_personas_intent(self):
        result = self.parser.parse("what is running low", personas.PERSONAS[personas.CUSTOMER])
        if result is not None:
            self.assertIn(result.intent, personas.PERSONAS[personas.CUSTOMER].intents + ("unknown", "clarify"))


class ModelParserTests(TestCase):
    """The model chooses a name from a list; anything else it says is dropped."""

    def setUp(self):
        self.parser = OpenRouterIntentParser()

    def _read(self, content: str, persona_key: str):
        return self.parser._read({"content": content}, personas.PERSONAS[persona_key])

    def test_in_persona_intent_is_accepted(self):
        result = self._read('{"intent": "order_status", "slots": {}, "confidence": 0.9}', personas.CUSTOMER)
        self.assertEqual(result.intent, "order_status")

    def test_out_of_persona_intent_is_dropped(self):
        self.assertIsNone(self._read('{"intent": "stock_lookup", "slots": {}}', personas.CUSTOMER))

    def test_invented_intent_is_dropped(self):
        self.assertIsNone(self._read('{"intent": "delete_all_orders", "slots": {}}', personas.PHARMACY))

    def test_markdown_fenced_json_is_tolerated(self):
        result = self._read('```json\n{"intent": "order_status", "slots": {}}\n```', personas.CUSTOMER)
        self.assertEqual(result.intent, "order_status")

    def test_undeclared_slots_are_stripped(self):
        result = self._read('{"intent": "order_status", "slots": {"reference": "HC-1", "pharmacy_id": "other"}}', personas.CUSTOMER)
        self.assertEqual(result.slots, {"reference": "HC-1"})

    def test_oversized_slot_is_truncated(self):
        result = self._read('{"intent": "stock_lookup", "slots": {"query": "%s"}}' % ("x" * 500), personas.PHARMACY)
        self.assertLessEqual(len(result.slots["query"]), 80)


class ConversationOwnershipTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(email="alice@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.bob = User.objects.create_user(email="bob@test.test", password="Password123!", role=UserRole.CUSTOMER)

    def test_another_user_cannot_resume_a_thread(self):
        conversation = AssistantConversation.objects.create(user=self.alice, persona=personas.CUSTOMER)
        with self.assertRaises(services.ConversationNotFound):
            services.load_conversation(str(conversation.id), self.bob)

    def test_a_guest_cannot_resume_a_signed_in_thread(self):
        conversation = AssistantConversation.objects.create(user=self.alice, persona=personas.CUSTOMER)
        with self.assertRaises(services.ConversationNotFound):
            services.load_conversation(str(conversation.id), None)

    def test_a_signed_in_user_cannot_adopt_a_guest_thread(self):
        conversation = AssistantConversation.objects.create(user=None, persona=personas.GUEST)
        with self.assertRaises(services.ConversationNotFound):
            services.load_conversation(str(conversation.id), self.alice)

    def test_a_thread_started_under_another_persona_is_refused(self):
        conversation = AssistantConversation.objects.create(user=self.alice, persona=personas.PHARMACY)
        with self.assertRaises(services.ConversationNotFound):
            services.answer(user=self.alice, message="where is my order", conversation=conversation)


class ChatEndpointTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=True)

    def test_anonymous_visitor_gets_the_guest_persona(self):
        response = self.client.get("/api/assistant/session/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["persona"], personas.GUEST)
        self.assertFalse(response.data["signed_in"])

    def test_signed_in_shopper_gets_the_customer_persona(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.get("/api/assistant/session/")
        self.assertEqual(response.data["persona"], personas.CUSTOMER)

    def test_a_chat_turn_persists_both_messages_and_returns_a_conversation_id(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post("/api/assistant/chat/", {"message": "where is my order"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["reply"])
        self.assertEqual(response.data["intent"], "order_status")
        conversation = AssistantConversation.objects.get(id=response.data["conversation_id"])
        self.assertEqual(conversation.user_id, self.shopper.id)
        self.assertEqual(conversation.messages.count(), 2)

    def test_a_persona_field_in_the_body_is_ignored(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post("/api/assistant/chat/", {"message": "what is running low", "persona": "pharmacy", "role": "PHARMACY_OWNER"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["persona"], personas.CUSTOMER)
        self.assertNotIn("stock_alerts", response.data["tools_used"])

    def test_resuming_someone_elses_conversation_is_a_404(self):
        other = AssistantConversation.objects.create(user=None, persona=personas.GUEST)
        self.client.force_authenticate(self.shopper)
        response = self.client.post("/api/assistant/chat/", {"message": "hello", "conversation_id": str(other.id)}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_an_empty_message_is_rejected(self):
        response = self.client.post("/api/assistant/chat/", {"message": "   "}, format="json")
        self.assertEqual(response.status_code, 400)


class CartAddTests(TestCase):
    """
    The one assistant turn that hands the client an action rather than only a sentence.

    It still writes nothing server-side - the cart is browser-local - so what is under test is
    the resolution: a plain name or a "cheapest" request becomes exactly one orderable listing,
    or nothing, and the `action` payload the widget adds mirrors the sentence the person read.
    """

    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="cart@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.cheap = make_pharmacy("Budget Pharmacy", "+961-1-111-111")
        self.dear = make_pharmacy("Premium Pharmacy", "+961-1-222-222")
        self.vitamin = Medicine.objects.create(
            brand_name="Reviton", generic_name="Multivitamin", strength="30 tablets", form="tablet", price_regime=PriceRegime.FREE
        )
        self.antibiotic = Medicine.objects.create(
            brand_name="Zinnat", generic_name="Cefuroxime", strength="500mg", form="tablet",
            price_regime=PriceRegime.FREE, requires_prescription=True,
        )
        for pharmacy, price in ((self.cheap, Decimal("8.00")), (self.dear, Decimal("12.50"))):
            create_inventory_batch(
                user=self.shopper,  # actor for the audit row only; the handler never scopes on it
                pharmacy=pharmacy,
                data={
                    "medicine": self.vitamin,
                    "initial_quantity": 40,
                    "selling_price": price,
                    "expiry_date": timezone.localdate() + timedelta(days=400),
                },
            )
        create_inventory_batch(
            user=self.shopper,
            pharmacy=self.dear,
            data={
                "medicine": self.antibiotic,
                "initial_quantity": 20,
                "selling_price": Decimal("15.00"),
                "expiry_date": timezone.localdate() + timedelta(days=400),
            },
        )

    def answer(self, message: str) -> dict:
        return services.answer(user=self.shopper, message=message)

    def test_cheapest_resolves_to_the_lower_priced_listing(self):
        payload = self.answer("add the cheapest reviton to my basket")
        self.assertEqual(payload["intent"], "add_to_cart")
        action = payload["action"]
        self.assertEqual(action["type"], "add_to_basket")
        self.assertEqual(action["item"]["medicine"], str(self.vitamin.id))
        self.assertEqual(action["item"]["unit_price"], 8.0)
        self.assertEqual(action["item"]["quantity"], 1)
        self.assertEqual(action["meta"]["basis"], "price")
        self.assertIn("8", payload["reply"])
        self.assertNotIn("12.5", payload["reply"])

    def test_quantity_is_read_and_capped_to_what_can_be_ordered(self):
        within = self.answer("add 3 reviton to my cart")
        self.assertEqual(within["action"]["item"]["quantity"], 3)

        capped = self.answer("add 15 reviton to my cart")
        self.assertEqual(capped["action"]["item"]["quantity"], 10)  # PUBLIC_MAX_QUANTITY_PER_ITEM
        self.assertIn("all that can be ordered", capped["reply"])

    def test_a_prescription_only_item_is_added_but_flagged(self):
        payload = self.answer("add zinnat to my cart")
        self.assertTrue(payload["action"]["item"]["requires_prescription"])
        self.assertIn("prescription", payload["reply"].lower())

    def test_an_unknown_product_adds_nothing(self):
        payload = self.answer("add florbleezinol to my cart")
        self.assertIsNone(payload["action"])
        self.assertEqual(payload["intent"], "add_to_cart")
        self.assertIn("couldn't find", payload["reply"].lower())

    def test_several_products_in_one_message_each_resolve(self):
        payload = self.answer("add reviton and zinnat to my cart")
        self.assertEqual(payload["intent"], "add_to_cart")
        actions = payload["actions"]
        self.assertEqual(len(actions), 2)
        added = {action["item"]["medicine"] for action in actions}
        self.assertEqual(added, {str(self.vitamin.id), str(self.antibiotic.id)})
        # `action` still carries the first, for older clients.
        self.assertEqual(payload["action"]["item"]["medicine"], actions[0]["item"]["medicine"])
        self.assertIn("Reviton", payload["reply"])
        self.assertIn("Zinnat", payload["reply"])
        # The prescription-only caveat still lands, once, naming only the item it applies to.
        self.assertIn("prescription-only", payload["reply"])

    def test_a_multi_add_reports_the_ones_it_could_not_find(self):
        payload = self.answer("add reviton and florbleezinol to my basket")
        actions = payload["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["item"]["medicine"], str(self.vitamin.id))
        self.assertIn("couldn't find florbleezinol", payload["reply"].lower())

    def test_a_multi_add_that_resolves_nothing_carries_no_action(self):
        payload = self.answer("add florbleezinol and glorbnix to my cart")
        self.assertEqual(payload["actions"], [])
        self.assertIsNone(payload["action"])
        self.assertIn("couldn't find", payload["reply"].lower())

    def test_cheapest_applies_across_every_product_named(self):
        payload = self.answer("add the cheapest reviton and zinnat to my basket")
        for action in payload["actions"]:
            self.assertEqual(action["meta"]["basis"], "price")
        reviton = next(a for a in payload["actions"] if a["item"]["medicine"] == str(self.vitamin.id))
        self.assertEqual(reviton["item"]["unit_price"], 8.0)

    def test_the_keyword_parser_splits_a_multi_product_message(self):
        parsed = KeywordIntentParser().parse("add creatine, redoxon and magnesium to my cart", personas.PERSONAS[personas.GUEST])
        self.assertEqual(parsed.intent, "add_to_cart")
        self.assertEqual(parsed.slots["queries"], ["creatine", "redoxon", "magnesium"])
        self.assertEqual(parsed.slots["query"], "creatine")

    def test_a_single_product_message_still_has_no_queries_slot(self):
        parsed = KeywordIntentParser().parse("add panadol to my cart", personas.PERSONAS[personas.GUEST])
        self.assertEqual(parsed.slots.get("query"), "panadol")
        self.assertNotIn("queries", parsed.slots)

    def test_the_reply_is_never_composed(self):
        intent = get_intent("add_to_cart")
        self.assertFalse(intent.compose)

    def test_a_pharmacy_persona_cannot_reach_the_cart_tool(self):
        allowed = frozenset(services._allowed_tools(personas.PERSONAS[personas.PHARMACY]))
        with self.assertRaises(tools.ToolNotAllowed):
            tools.execute("cart_add", allowed=allowed, context=ToolContext(user=self.shopper, slots={"query": "reviton"}))


class CartAddEndpointTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(
            email="cartapi@test.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=True
        )
        pharmacy = make_pharmacy("Corner Pharmacy", "+961-1-333-333")
        medicine = Medicine.objects.create(
            brand_name="Sunblock", generic_name="Octocrylene", strength="SPF50", form="cream", price_regime=PriceRegime.FREE
        )
        create_inventory_batch(
            user=self.shopper,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "initial_quantity": 25,
                "selling_price": Decimal("19.90"),
                "expiry_date": timezone.localdate() + timedelta(days=400),
            },
        )

    def test_the_chat_endpoint_returns_the_add_to_basket_action(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post("/api/assistant/chat/", {"message": "add sunblock to my cart"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["intent"], "add_to_cart")
        action = response.data["action"]
        self.assertEqual(action["type"], "add_to_basket")
        self.assertEqual(action["item"]["name"], "Sunblock SPF50")
        self.assertEqual(action["item"]["unit_price"], 19.9)

    def test_a_plain_question_carries_no_action(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post("/api/assistant/chat/", {"message": "where is my order"}, format="json")
        self.assertIsNone(response.data["action"])
