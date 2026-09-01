from __future__ import annotations

from dataclasses import dataclass

from apps.accounts.models import UserRole

GUEST = "guest"
CUSTOMER = "customer"
DOCTOR = "doctor"
PHARMACY = "pharmacy"
ADMIN = "admin"
DRIVER = "driver"


@dataclass(frozen=True)
class Persona:
    """
    One role's assistant: who it is talking to, and the complete list of things it is able to
    answer.

    `intents` is the whole of a persona's reach, and it is enforcement rather than
    description. The router only ever scores intents from this tuple, and the model parser is
    only ever shown this tuple, so a persona cannot reach an intent - and therefore cannot
    reach the tool behind it - that it does not name here. Everything else in this module
    (greeting, suggestions) is presentation.

    Access control deliberately does not live in any prompt text. A prompt is a suggestion; a
    tuple membership test is not.
    """

    key: str
    label: str
    # A short phrase naming who this is, for the composer's system prompt (apps.assistant.
    # composer) - framing only, never an access grant. What the persona may actually read is
    # governed entirely by `intents` below, independently of what this says.
    audience: str
    intents: tuple[str, ...]
    greeting: str
    suggestions: tuple[str, ...] = ()

    def allows(self, intent_name: str) -> bool:
        return intent_name in self.intents


# Available to every persona, signed in or not.
#
# The first two are the docs/PRD.md non-goals turned into ordinary intents. That is the whole
# trick: "no diagnosis, no treatment advice, no substitution recommendation" is not a rule the
# model is asked to respect, it is a destination the model can only route to, whose answer is
# a fixed string this repo controls. A parser that misclassifies a clinical question as
# something else still cannot produce clinical advice, because no intent renders free text.
UNIVERSAL_INTENTS = ("clinical_question", "emergency", "human_handoff", "greeting")

PERSONAS: dict[str, Persona] = {
    GUEST: Persona(
        key=GUEST,
        label="HealthConnect help",
        audience="a visitor who is not signed in",
        intents=UNIVERSAL_INTENTS
        + ("search_availability", "prescription_required", "find_pharmacies", "add_to_cart", "how_it_works", "sign_in_needed"),
        greeting="Hi. I can check which pharmacies near you have a medicine in stock, or explain how ordering works. What are you looking for?",
        suggestions=(
            "Who has Panadol in stock?",
            "How much is Augmentin?",
            "Which is the closest pharmacy that has amoxicillin?",
            "Find paracetamol near me",
            "Add Panadol to my cart",
            "Do I need a prescription for Augmentin?",
            "Is Panadol over the counter?",
            "What is the nearest pharmacy to me?",
            "Any pharmacy open now?",
            "How does delivery work?",
            "How does this work?",
        ),
    ),
    CUSTOMER: Persona(
        key=CUSTOMER,
        label="Your assistant",
        audience="a signed-in patient, about their own account",
        intents=UNIVERSAL_INTENTS
        + (
            "search_availability",
            "prescription_required",
            "find_pharmacies",
            "add_to_cart",
            "how_it_works",
            "order_status",
            "prescription_status",
            "prescription_coverage",
            "refill_status",
        ),
        greeting="Hi. I can check on your orders, your prescriptions, or find which pharmacy near you has what you need.",
        suggestions=(
            "Where is my latest order?",
            "When will my delivery arrive?",
            "Track my order",
            "When does my prescription expire?",
            "Which pharmacy near me has everything on my prescription?",
            "Where can I fill my whole prescription?",
            "When is my next refill?",
            "Add Panadol to my cart",
            "Add the cheapest vitamin C to my basket",
            "Find paracetamol near me",
            "Which is the closest pharmacy that has Augmentin?",
            "Is Panadol over the counter?",
        ),
    ),
    DOCTOR: Persona(
        key=DOCTOR,
        label="Practice assistant",
        audience="a doctor, about their own prescribing workload",
        intents=UNIVERSAL_INTENTS + ("catalogue_lookup", "my_prescriptions", "renewal_requests", "my_patients"),
        greeting="Hi. I can pull up your prescriptions, renewal requests, or look something up in the catalogue.",
        suggestions=(
            "How many renewal requests are waiting?",
            "Any renewals pending?",
            "Which prescriptions expire this week?",
            "Prescriptions I issued",
            "How many patients do I have?",
            "Find patient Khoury",
            "Is amoxicillin prescription-only?",
            "Is Augmentin registered?",
        ),
    ),
    PHARMACY: Persona(
        key=PHARMACY,
        label="Pharmacy assistant",
        audience="a pharmacy owner or staff member, about their own pharmacy",
        intents=UNIVERSAL_INTENTS + ("stock_lookup", "stock_alerts", "sales_summary", "business_insights", "incoming_orders"),
        greeting="Hi. I can check stock, flag what is expiring, or summarise how the last few weeks traded.",
        suggestions=(
            "What is running low?",
            "Anything expiring soon?",
            "How many Panadol do we have?",
            "Do we have Augmentin in stock?",
            "How did we trade over the last 30 days?",
            "Sales this month",
            "Any insights for us?",
            "Any analytics findings?",
            "Any online orders waiting?",
            "How many orders are pending?",
        ),
    ),
    ADMIN: Persona(
        key=ADMIN,
        label="Operations assistant",
        audience="a HealthConnect platform administrator",
        intents=UNIVERSAL_INTENTS + ("platform_overview", "pending_applications", "dispatch_snapshot", "recent_activity"),
        greeting="Hi. I can summarise the network, pending applications, or what dispatch looks like right now.",
        suggestions=(
            "Give me a platform overview",
            "How is the network doing?",
            "How many applications are pending?",
            "Any new pharmacy applications?",
            "What does dispatch look like right now?",
            "How many drivers are online?",
            "What happened recently?",
            "Show me the audit log",
        ),
    ),
    DRIVER: Persona(
        key=DRIVER,
        label="Route assistant",
        audience="a delivery driver, currently on their route",
        intents=UNIVERSAL_INTENTS + ("next_stop", "my_route"),
        greeting="Hi. I can tell you what is next on your route.",
        suggestions=(
            "What is my next stop?",
            "Where next?",
            "How many stops are left?",
            "What does my route look like?",
        ),
    ),
}

ROLE_PERSONAS: dict[str, str] = {
    UserRole.CUSTOMER: CUSTOMER,
    UserRole.DOCTOR: DOCTOR,
    UserRole.PHARMACY_OWNER: PHARMACY,
    UserRole.PHARMACY_STAFF: PHARMACY,
    UserRole.PLATFORM_ADMIN: ADMIN,
    UserRole.DRIVER: DRIVER,
}


def persona_for(user) -> Persona:
    """
    Which assistant a request gets, derived from the authenticated user and nothing else.

    The client never names a persona - if it could, picking `pharmacy` would be the whole
    attack. Anonymous requests, and any role without an assistant of its own, fall back to the
    guest persona, which reaches no personal record at all.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return PERSONAS[GUEST]
    return PERSONAS.get(ROLE_PERSONAS.get(user.role, GUEST), PERSONAS[GUEST])


def get_persona(key: str) -> Persona:
    try:
        return PERSONAS[key]
    except KeyError:
        raise ValueError(f"Unknown assistant persona '{key}'.") from None
