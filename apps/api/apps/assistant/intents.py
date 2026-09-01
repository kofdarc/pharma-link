"""
Everything the assistant can be asked, and exactly what it says back.

Two things live here, deliberately together. An intent's *trigger* (the keywords that match
it, the examples shown to the model parser) sits next to its *answer* (a renderer that turns a
tool result into a sentence), because the pair is what needs reviewing as a unit: it is very
easy to widen a trigger without noticing the answer no longer fits the questions it now
catches.

Every renderer returns a fixed string built from tool output. No renderer generates prose, and
none of them is reachable without a tool result to build from. That is the property that makes
the whole thing safe to point at a language model: the model chooses which of these runs, and
it can be wrong about that, but it cannot write the answer, so it cannot invent a stock level,
a price, an expiry date or a dose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from django.conf import settings

from apps.common.geo import describe_distance

Renderer = Callable[[dict, dict], str]


@dataclass(frozen=True)
class Intent:
    name: str
    description: str
    render: Renderer
    tool: str = ""
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    slots: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    # Whether the LLM composer may re-word this intent's answer. Off for intents whose reply
    # carries a client-side action (add_to_cart): the person needs the exact product name and
    # quantity that the widget is about to act on, not a paraphrase of them.
    compose: bool = True


def plural(count: int, one: str, many: str = "") -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _join(parts: list[str]) -> str:
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


# --- static answers ------------------------------------------------------------------------
# These carry no tool and read no data. They exist so that the questions this product must not
# answer have somewhere definite to land, rather than falling through to a generic "I don't
# know" that invites the person to rephrase until something sticks.


def render_clinical(result: dict, slots: dict) -> str:
    return (
        "I can't help with anything about how to take a medicine, whether it suits you, or "
        "whether one product can stand in for another - that needs a pharmacist or your "
        "doctor, who can see your history. I can find you a pharmacy to call if that helps."
    )


def render_emergency(result: dict, slots: dict) -> str:
    number = getattr(settings, "ASSISTANT_EMERGENCY_NUMBER", "")
    call = f"call {number} now" if number else "call your local emergency number now"
    return f"If this is an emergency, stop reading and {call}. I'm not able to help with anything urgent or medical."


def render_handoff(result: dict, slots: dict) -> str:
    return (
        "That needs a person rather than me. Your pharmacy's contact number is on the order, "
        "and anything about an account or a payment goes to HealthConnect support."
    )


def render_greeting(result: dict, slots: dict) -> str:
    return slots.get("greeting", "Hi. What can I look up for you?")


def render_how_it_works(result: dict, slots: dict) -> str:
    return (
        "You search once across every connected pharmacy, and order from whichever has what "
        "you need - delivery or pickup. Prescription-only items need a valid prescription "
        "before checkout completes. Ask me about a specific medicine and I'll check who has it."
    )


def render_sign_in_needed(result: dict, slots: dict) -> str:
    return "I can only look up orders and prescriptions once you're signed in. Sign in and ask me again, and I'll pull it up."


def render_unknown(result: dict, slots: dict) -> str:
    return "I couldn't work out what you're after. I can check stock, look things up in the catalogue, and answer questions about your own records - try one of the suggestions."


def render_clarify(result: dict, slots: dict) -> str:
    options = slots.get("options") or []
    if not options:
        return render_unknown(result, slots)
    return f"I could read that a couple of ways - did you mean {_join(options)}?"


# --- public lookups ------------------------------------------------------------------------


def render_availability(result: dict, slots: dict) -> str:
    rows = result.get("results") or []
    query = result.get("query") or "that"
    if not rows:
        return f"I couldn't find {query} in stock at any connected pharmacy right now. It may be worth trying a different spelling, or asking me for pharmacies near you."

    first = rows[0]
    total = result.get("total_found", len(rows))
    price = f", at {first['unit_price']}" if first.get("unit_price") else ""
    head = f"{first['medicine']} {first['strength']}".strip()
    where = f"{first['pharmacy']} in {first['area']}" if first.get("area") else first["pharmacy"]
    # "Closest" only when the row was actually ranked by distance. Saying it about an
    # alphabetical list would be the one kind of wrong answer a shopper cannot check.
    near = describe_distance(first.get("distance_km"))
    lead = f"{head}: the closest is {where}, {near}" if near else f"{head} is in stock at {where}"
    lead += f"{price} ({first['availability'].lower()}, up to {first['available_up_to']})."
    more = f" {plural(total - 1, 'other pharmacy', 'other pharmacies')} also {'has' if total - 1 == 1 else 'have'} it." if total > 1 else ""
    # Deliberately worded as a warning rather than a footnote. Someone told a pharmacy has a
    # product will otherwise set out for it, and a wasted trip for a prescription-only
    # medicine is the single most predictable disappointment this assistant can prevent.
    rx = " Careful though - it's prescription-only, so bring a valid prescription or you won't be able to collect it." if first.get("requires_prescription") else ""
    hint = "" if result.get("located") else " Share your location and I can tell you which of those is closest to you."
    return lead + more + rx + hint


def render_prescription_required(result: dict, slots: dict) -> str:
    matches = result.get("matches") or []
    query = result.get("query") or "that"
    if not matches:
        return f"I couldn't find {query} in the catalogue, so I can't tell you whether it needs a prescription. Try the brand name as it appears on the box."
    first = matches[0]
    name = f"{first['brand_name']} {first['strength']}".strip()
    if first.get("requires_prescription"):
        return f"{name} is prescription-only. You'll need a valid prescription at checkout - a doctor can issue one through HealthConnect, or you can upload an existing one."
    return f"{name} does not need a prescription. You can order it directly."


def render_find_pharmacies(result: dict, slots: dict) -> str:
    rows = result.get("pharmacies") or []
    area = result.get("area")
    if not rows:
        return f"I couldn't find a connected pharmacy in {area}." if area else "I couldn't find any connected pharmacies to show."
    located = result.get("located")
    lines = []
    for item in rows[:3]:
        far = describe_distance(item.get("distance_km"))
        detail = ", ".join(part for part in (far, f"{item['opens_at']}-{item['closes_at']}", "on call" if item["is_on_call"] else "") if part)
        lines.append(f"{item['name']} ({item['area']}, {detail})")
    where = f" in {area}" if area else ""
    lead = f"{plural(result.get('total_found', len(rows)), 'pharmacy', 'pharmacies')}{where}."
    order = " Nearest first: " if located else " Here are some: "
    tail = "" if located else " Share your location if you want these ordered by how close they are."
    return lead + order + "; ".join(lines) + "." + tail


def render_cart_add(result: dict, slots: dict) -> str:
    """
    Confirms what the widget is about to drop into the browser cart.

    Never composed (see Intent.compose): the product name, price and quantity here have to be
    exactly the ones apps.assistant.services put in the `action` payload, because that is what
    the person is being told they can undo.
    """
    query = result.get("query") or "that"
    if not result.get("added"):
        reason = result.get("reason")
        if reason == "not_orderable":
            return (
                f"I found {query}, but nothing listed for it right now can be ordered online - "
                "it may be out of stock or pickup-only. Try again later or search for an alternative."
            )
        return f"I couldn't find {query} to add. Try the name as it appears on the box."

    match = result["match"]
    name = match["name"]
    granted = result.get("granted_quantity", 1)
    requested = result.get("requested_quantity", granted)
    total = result.get("total_listings", 0)

    lead = f"Added {plural(granted, 'unit')} of {name} to your cart"
    if match.get("unit_price"):
        if result.get("basis") == "price":
            lead += f", the cheapest of {plural(total, 'listing')} at {match['unit_price']} each"
        else:
            lead += f", at {match['unit_price']} each"
    lead += "."

    short = ""
    if granted < requested:
        short = f" You asked for {requested}, but that is all that can be ordered right now."
    rx = ""
    if match.get("requires_prescription"):
        rx = " It's prescription-only, so you'll need a valid prescription at checkout."
    return lead + short + rx + " Open your cart when you're ready to check out."


# --- patient -------------------------------------------------------------------------------


def render_prescription_coverage(result: dict, slots: dict) -> str:
    """
    "Which pharmacy near me has everything on my prescription?"

    Ordered by what changes the person's next ten minutes: whether one trip does it, then
    where, then how far, then the two things that would make the trip fail anyway - a line
    nobody nearby stocks, and the fact that they must physically carry the prescription.
    """
    prescription = result.get("prescription")
    if not prescription:
        if result.get("reason") == "no_email":
            return "I couldn't match any prescriptions to this account. They're matched on the email your doctor recorded, so check that it matches the address you signed up with."
        return "You don't have a valid prescription on file right now. Once your doctor issues one, I can find the pharmacies that stock everything on it."

    code = prescription["code"]
    if not result.get("lines_outstanding"):
        unmatched = result.get("unmatched") or []
        if unmatched:
            names = _join([item["medicine"] for item in unmatched[:3]])
            return f"Prescription {code} lists {names}, which isn't in the HealthConnect catalogue yet, so I can't check stock for it. Any pharmacy can still dispense it from the prescription itself."
        return f"Everything on prescription {code} has already been dispensed, so there's nothing left to source."

    full = result.get("full_coverage") or []
    partial = result.get("partial_coverage") or []
    lines_requested = result.get("lines_outstanding", 0)

    # "nearby" is a claim about distance, and it is only true when a position was used.
    # Without one this searched the whole connected network, so it says so instead.
    scope = " nearby" if result.get("located") else ""

    if full:
        best = full[0]
        far = describe_distance(best.get("distance_km"))
        where = f"{best['pharmacy']['name']} in {best['pharmacy']['area']}"
        lead = f"{where} has all {plural(lines_requested, 'item')} on prescription {code}"
        lead += f", {far}." if far else "."
        others = f" {plural(len(full) - 1, 'other pharmacy', 'other pharmacies')}{scope} can also cover the whole list." if len(full) > 1 else ""
        hours = f" Open {best['pharmacy']['opens_at']}-{best['pharmacy']['closes_at']}."
        controlled = best.get("requires_prescription") or []
    elif partial:
        best = partial[0]
        far = describe_distance(best.get("distance_km"))
        where = f"{best['pharmacy']['name']} in {best['pharmacy']['area']}"
        short = _join([item["medicine"] for item in (best.get("missing") or [])[:3]])
        # Without a position the list is not ordered by distance, so this is the best
        # coverage rather than the closest one - and it must not be described as the closest.
        best_label = "closest" if result.get("located") else "best"
        lead = f"No single pharmacy{scope} has the whole of prescription {code}. The {best_label} match is {where}"
        lead += f", {far}," if far else ","
        lead += f" which covers {best['lines_covered']} of {lines_requested} - it's short on {short}."
        others = ""
        hours = ""
        controlled = best.get("requires_prescription") or []
    else:
        return f"No connected pharmacy{scope} currently lists anything from prescription {code}. It may be worth asking me again later, or calling a pharmacy directly."

    # Always said, and always true of a prescription being filled: it has to be presented.
    # The names are added only when the tool reported which lines are prescription-only - a
    # doctor may well have written an over-the-counter item onto the same script, so
    # "everything on it is prescription-only" would be an overclaim.
    rx = f" Bring prescription {code} with you - the pharmacy needs it to dispense"
    rx += f" {_join(controlled[:3])}." if controlled else "."
    hint = "" if result.get("located") else " Share your location and I can rank these by how close they are to you."
    return lead + others + hours + rx + hint


def render_order_status(result: dict, slots: dict) -> str:
    orders = result.get("orders") or []
    if not orders:
        return "I couldn't find any orders on your account. If you've just placed one, give it a moment and ask me again."
    first = orders[0]
    pharmacies = _join(first.get("pharmacies") or [])
    where = f" from {pharmacies}" if pharmacies else ""
    lead = f"Your most recent order {first['reference']}{where} is {first['status'].lower()}."
    if first.get("cancelled_reason"):
        lead += f" Reason given: {first['cancelled_reason']}."
    tail = f" You have {plural(result.get('total_found', len(orders)), 'order')} in total." if result.get("total_found", 0) > 1 else ""
    return lead + tail


def render_prescription_status(result: dict, slots: dict) -> str:
    scripts = result.get("prescriptions") or []
    if not scripts:
        return "I couldn't find any e-prescriptions issued to your account. They're matched on the email your doctor recorded, so check that it matches this account."
    first = scripts[0]
    if first.get("is_expired"):
        body = f"Your most recent prescription from {first['doctor']} ({first['code']}) has expired."
        return body + " Your doctor can issue a renewal through HealthConnect."
    remaining = sum(line["remaining"] for line in first.get("items") or [])
    left = f", with {plural(remaining, 'unit')} still to dispense" if remaining else ", fully dispensed"
    return f"Your most recent prescription from {first['doctor']} ({first['code']}) is {first['status'].lower()} and valid for another {plural(first['days_left'], 'day')}{left}."


def render_refill_status(result: dict, slots: dict) -> str:
    refills = result.get("refills") or []
    if not refills:
        return "You don't have any repeat refills set up. You can create one from an existing order on the Refills screen."
    active = [item for item in refills if item["is_active"]]
    if not active:
        return f"You have {plural(len(refills), 'repeat refill')}, but none are active right now."
    first = active[0]
    days = first["days_until_next"]
    when = "today" if days == 0 else (f"in {plural(days, 'day')}" if days > 0 else "overdue")
    lead = f"Your \"{first['label']}\" refill runs every {plural(first['interval_days'], 'day')} and is next due {when}."
    return lead + (f" Last attempt reported: {first['last_error']}." if first.get("last_error") else "")


# --- doctor --------------------------------------------------------------------------------


def render_catalogue(result: dict, slots: dict) -> str:
    matches = result.get("matches") or []
    query = result.get("query") or "that"
    if not matches:
        return f"Nothing in the catalogue matches {query}."
    first = matches[0]
    bits = [f"{first['brand_name']} {first['strength']} {first['form']}".strip()]
    if first.get("generic_name"):
        bits.append(f"generic {first['generic_name']}")
    bits.append("prescription-only" if first.get("requires_prescription") else "over the counter")
    if first.get("drug_schedule") and first["drug_schedule"].lower() not in {"none", "not scheduled"}:
        bits.append(f"schedule {first['drug_schedule']}")
    bits.append(first["market_status"].lower())
    return " - ".join(bits) + "."


def render_doctor_prescriptions(result: dict, slots: dict) -> str:
    scripts = result.get("prescriptions") or []
    total = result.get("total_found", len(scripts))
    if not scripts:
        return "I couldn't find any prescriptions matching that."
    lines = [f"{item['patient_name']} ({item['code']}), {item['status'].lower()}, {plural(item['days_left'], 'day')} left" for item in scripts[:3]]
    return f"{plural(total, 'prescription')} matching. Most recent: " + "; ".join(lines) + "."


def render_renewals(result: dict, slots: dict) -> str:
    pending = result.get("pending_count", 0)
    if not pending:
        return "No renewal requests are waiting on you."
    rows = result.get("requests") or []
    lines = [f"{item['patient_name']} ({item['prescription_code']}) from {item['pharmacy']}, waiting {plural(item['waiting_days'], 'day')}" for item in rows[:3]]
    return f"{plural(pending, 'renewal request')} waiting on you. " + "; ".join(lines) + "."


def render_patients(result: dict, slots: dict) -> str:
    patients = result.get("patients") or []
    total = result.get("total_found", len(patients))
    if not patients:
        return "I couldn't find any patients matching that."
    lines = [f"{item['name']} ({plural(item['prescription_count'], 'prescription')})" for item in patients[:3]]
    return f"{plural(total, 'patient')} matching. " + "; ".join(lines) + "."


# --- pharmacy ------------------------------------------------------------------------------


def render_stock_lookup(result: dict, slots: dict) -> str:
    batches = result.get("batches") or []
    query = result.get("query") or "that"
    if not batches:
        return f"Nothing on the shelf matches {query}."
    total = result.get("total_quantity", 0)
    first = batches[0]
    lead = f"{plural(total, 'unit')} of {first['medicine']} across {plural(len(batches), 'batch', 'batches')}."
    expiry = f" Earliest expiry {first['expiry_date']}." if first.get("expiry_date") else ""
    flag = " Below the low-stock threshold." if first.get("is_low_stock") else ""
    return lead + expiry + flag


def render_stock_alerts(result: dict, slots: dict) -> str:
    low = result.get("low_stock_count", 0)
    expiring = result.get("expiring_count", 0)
    if not low and not expiring:
        return "Nothing is low or close to expiry right now."
    parts = []
    if low:
        names = ", ".join(item["medicine"] for item in (result.get("low_stock") or [])[:3])
        parts.append(f"{plural(low, 'line')} running low ({names})")
    if expiring:
        names = ", ".join(item["medicine"] for item in (result.get("expiring_soon") or [])[:3])
        parts.append(f"{plural(expiring, 'line')} expiring soon ({names})")
    return _join(parts).capitalize() + "."


def render_sales_summary(result: dict, slots: dict) -> str:
    sales = result.get("sales") or {}
    days = result.get("days", 30)
    if not sales:
        return f"I couldn't read the sales figures for the last {plural(days, 'day')}."
    transactions = int(sales.get("transactions") or 0)
    if not transactions:
        return f"No completed sales in the last {plural(days, 'day')}."
    bits = [
        plural(transactions, "sale"),
        f"{sales['revenue']} revenue",
        f"{sales['gross_margin_percent']}% gross margin",
        f"{sales['average_basket']} average basket",
    ]
    return f"Over the last {plural(days, 'day')}: " + _join(bits) + "."


def render_insights(result: dict, slots: dict) -> str:
    insights = result.get("insights") or []
    if not insights:
        return "Analytics hasn't flagged anything worth acting on right now."
    lines = [str(item.get("title") or item.get("summary") or "").strip() for item in insights[:3]]
    return "Top findings: " + "; ".join(line for line in lines if line) + "."


def render_incoming_orders(result: dict, slots: dict) -> str:
    count = result.get("waiting_count", 0)
    if not count:
        return "No online orders are waiting on you."
    rows = result.get("waiting") or []
    lines = [f"{item['reference']} ({item['status'].lower()}, {item['fulfillment_type'].lower()})" for item in rows[:3]]
    return f"{plural(count, 'order')} waiting. " + "; ".join(lines) + "."


# --- platform admin ------------------------------------------------------------------------


def render_platform_overview(result: dict, slots: dict) -> str:
    return (
        f"{plural(result.get('pharmacies_active', 0), 'active pharmacy', 'active pharmacies')}, "
        f"{result.get('pharmacies_accepting_orders', 0)} accepting online orders. "
        f"{plural(result.get('orders_today', 0), 'order')} placed today, {result.get('orders_open', 0)} still open. "
        f"{plural(result.get('drivers_online', 0), 'driver')} online. "
        f"{plural(result.get('applications_pending', 0), 'application')} pending review."
    )


def render_pending_applications(result: dict, slots: dict) -> str:
    count = result.get("pending_count", 0)
    if not count:
        return "No pharmacy applications are waiting on review."
    rows = result.get("applications") or []
    lines = [f"{item['pharmacy_name']} ({item['area'] or item['city']}), waiting {plural(item['waiting_days'], 'day')}" for item in rows[:3]]
    return f"{plural(count, 'application')} pending, oldest first: " + "; ".join(lines) + "."


def render_dispatch(result: dict, slots: dict) -> str:
    waiting = result.get("orders_awaiting_driver", 0)
    lead = (
        f"{plural(result.get('routes_active', 0), 'route')} active, "
        f"{result.get('routes_proposed', 0)} proposed, "
        f"{plural(result.get('drivers_online', 0), 'driver')} online, "
        f"{result.get('orders_in_transit', 0)} in transit."
    )
    return lead + (f" {plural(waiting, 'order')} still without a driver." if waiting else "")


def render_recent_activity(result: dict, slots: dict) -> str:
    entries = result.get("entries") or []
    if not entries:
        return "Nothing in the audit trail yet."
    lines = []
    for item in entries[:4]:
        where = f" ({item['pharmacy']})" if item.get("pharmacy") else ""
        lines.append(f"{item['action']}{where}")
    return "Most recent: " + "; ".join(lines) + "."


# --- driver --------------------------------------------------------------------------------


def render_next_stop(result: dict, slots: dict) -> str:
    if not result.get("has_route"):
        return "You don't have an active route right now."
    stop = result.get("stop")
    if stop is None:
        return "That's your last stop done - the route is clear."
    action = "Collect from" if stop["kind_code"] == "PICKUP" else "Deliver to"
    lead = f"{action} {stop['label']}, {stop['address']}."
    codes = stop.get("handover_codes") or []
    code = f" Handover code {', '.join(codes)}." if codes else ""
    left = f" {plural(result.get('remaining', 1) - 1, 'stop')} after this." if result.get("remaining", 0) > 1 else " Last one."
    return lead + code + left


def render_my_route(result: dict, slots: dict) -> str:
    if not result.get("has_route"):
        return "You don't have an active route right now."
    remaining = result.get("remaining", 0)
    if not remaining:
        return f"All {plural(result.get('total_stops', 0), 'stop')} done - the route is clear."
    return f"{plural(remaining, 'stop')} left of {result.get('total_stops', 0)}, about {result.get('planned_duration_minutes', 0)} minutes and {result.get('planned_distance_km')} km planned."


INTENTS: dict[str, Intent] = {
    intent.name: intent
    for intent in (
        Intent(
            name="clinical_question",
            description="Anything about symptoms, diagnosis, dosage, side effects, interactions, or whether one medicine can replace another.",
            render=render_clinical,
            examples=("is it safe to take these together", "what dose should I take", "can I take ibuprofen instead", "what is this rash"),
        ),
        Intent(
            name="emergency",
            description="Someone describing a medical emergency or urgent harm.",
            render=render_emergency,
            examples=("I think I overdosed", "she can't breathe", "chest pain right now"),
        ),
        Intent(
            name="human_handoff",
            description="A complaint, refund, billing dispute, or an explicit request to speak to a person.",
            render=render_handoff,
            required=("complaint", "refund", "human", "agent", "manager", "speak"),
            optional=("talk", "someone", "person", "money", "back", "charged", "wrong"),
            examples=("I want a refund", "let me talk to someone", "I have a complaint"),
        ),
        Intent(
            name="greeting",
            description="A greeting or an open-ended question about what the assistant can do.",
            render=render_greeting,
            required=("hi", "hello", "hey", "help", "salam", "bonjour", "marhaba"),
            optional=("there", "can", "you", "do", "what"),
            examples=("hi", "hello", "what can you do"),
        ),
        Intent(
            name="how_it_works",
            description="How HealthConnect works: ordering, delivery, pickup, joining as a pharmacy or doctor.",
            render=render_how_it_works,
            required=("work", "delivery", "deliver", "shipping", "join", "signup"),
            optional=("how", "does", "this", "up", "pickup", "collect", "long", "explain"),
            examples=("how does delivery work", "how does this work", "how do I join as a pharmacy"),
        ),
        Intent(
            name="sign_in_needed",
            description="A signed-out visitor asking about their own orders, prescriptions or account.",
            render=render_sign_in_needed,
            required=("my",),
            optional=("order", "orders", "prescription", "prescriptions", "account", "refill", "delivery"),
            examples=("where is my order", "my prescription"),
        ),
        Intent(
            name="search_availability",
            description="Whether a named medicine is in stock anywhere, and at which pharmacy or price.",
            render=render_availability,
            tool="search_availability",
            # "medicine"/"drug" earn required status rather than optional: without them,
            # "which is the closest pharmacy to me that has this medicine" scored level with
            # find_pharmacies and the router asked which was meant, on a question that plainly
            # names a product. They cost nothing elsewhere - a message carrying one of these
            # and nothing else is an availability question.
            required=("stock", "available", "availability", "have", "find", "buy", "get", "sell", "price", "cost", "much", "medicine", "medicines", "drug"),
            optional=("anyone", "where", "near", "nearest", "closest", "nearby", "me", "pharmacy", "any", "who", "looking", "anywhere", "far"),
            slots=("query", "area"),
            examples=(
                "who has panadol",
                "is amoxicillin available",
                "how much is augmentin",
                "find paracetamol near me",
                "which is the closest pharmacy to me that has this medicine",
            ),
        ),
        Intent(
            name="prescription_required",
            description="Whether a named product needs a prescription to buy.",
            render=render_prescription_required,
            tool="medicine_details",
            required=("prescription", "otc", "counter", "rx"),
            optional=("need", "require", "required", "do", "i", "without", "over", "buy"),
            slots=("query",),
            examples=("do I need a prescription for augmentin", "is panadol over the counter"),
        ),
        Intent(
            name="find_pharmacies",
            description="Which pharmacies are connected, open, or on call, optionally in a named area.",
            render=render_find_pharmacies,
            tool="find_pharmacies",
            required=("pharmacy", "pharmacies", "pharmacie", "open", "call"),
            optional=("near", "me", "which", "list", "nearby", "area", "tonight", "now", "closest", "nearest", "far", "around"),
            slots=("area",),
            examples=("which pharmacies are near me", "any pharmacy open now", "pharmacies in Hamra", "what is the nearest pharmacy"),
        ),
        Intent(
            name="add_to_cart",
            description=(
                "Put a product in the shopping cart. Resolves a plain name ('add Panadol') or a "
                "'cheapest' request ('order me the cheapest vitamin C') to one specific listing."
            ),
            render=render_cart_add,
            tool="cart_add",
            # Off: the reply names the exact product and quantity the widget is about to add,
            # and a paraphrase of "2 units of X at 4.50" is not something the person can check
            # against the undo button.
            compose=False,
            # "add" / "cart" / "basket" are the whole trigger - one of them must be present or
            # this intent scores zero, so "how much is panadol" and "where is my order" are
            # never at risk. Looser phrasings ("order me the cheapest ibuprofen", "buy me
            # some aspirin") carry none of these words and are left to the model parser, which
            # is shown this intent's examples.
            required=("add", "cart", "basket"),
            optional=(
                "to", "my", "the", "please", "want", "put", "get", "buy", "order",
                "cheapest", "cheap", "lowest", "box", "boxes", "pack", "packs", "for", "me",
            ),
            slots=("query", "quantity", "sort"),
            examples=(
                "add panadol to my cart",
                "add the cheapest vitamin c to my basket",
                "order me the cheapest protein powder",
                "add 2 boxes of amoxicillin to my cart",
            ),
        ),
        Intent(
            name="order_status",
            description="Where the person's own order has got to, or when it will arrive.",
            render=render_order_status,
            tool="my_orders",
            required=("order", "orders", "delivery", "deliver", "package", "parcel", "shipment"),
            optional=("where", "my", "status", "late", "arrive", "arriving", "coming", "track", "when", "is"),
            slots=("reference",),
            examples=("where is my order", "when will my delivery arrive", "track my order"),
        ),
        Intent(
            name="prescription_status",
            description="The status, validity or remaining quantity of the person's own prescriptions.",
            render=render_prescription_status,
            tool="my_prescriptions_patient",
            required=("prescription", "prescriptions", "rx", "script"),
            optional=("my", "expire", "expires", "expiry", "valid", "left", "remaining", "status", "when", "still"),
            examples=("when does my prescription expire", "is my prescription still valid"),
        ),
        Intent(
            name="prescription_coverage",
            description="Which pharmacy near the patient can fill everything on their current prescription in one visit.",
            render=render_prescription_coverage,
            tool="prescription_coverage",
            # "everything" sits in `required` alongside the prescription words so that the
            # coverage question outscores the plain "is my prescription still valid" one when
            # both are readable. "all" was tried here and rejected: it is common enough
            # ("show me all my orders") to pull unrelated messages in.
            required=("prescription", "rx", "script", "everything"),
            optional=(
                "pharmacy", "pharmacies", "near", "nearest", "closest", "nearby", "which", "who", "me",
                "fill", "one", "whole", "have", "carry", "stock", "medicine", "medicines", "trip", "single",
            ),
            slots=("reference",),
            examples=(
                "which pharmacy near me has everything on my prescription",
                "where can I fill my whole prescription",
                "nearest pharmacy that has all the medicine in my prescription",
            ),
        ),
        Intent(
            name="refill_status",
            description="The person's own repeat refills and when the next one is due.",
            render=render_refill_status,
            tool="my_refills",
            required=("refill", "refills", "repeat", "recurring", "subscription"),
            optional=("my", "next", "when", "due", "active", "schedule"),
            examples=("when is my next refill", "my repeat orders"),
        ),
        Intent(
            name="catalogue_lookup",
            description="Registration facts for a product: form, strength, schedule, prescription status.",
            render=render_catalogue,
            tool="catalogue_lookup",
            required=("catalogue", "catalog", "registered", "schedule", "strength", "form", "prescription", "look"),
            optional=("up", "is", "what", "does", "come", "in", "only", "controlled"),
            slots=("query",),
            examples=("is amoxicillin prescription-only", "what strengths does augmentin come in"),
        ),
        Intent(
            name="my_prescriptions",
            description="Prescriptions this doctor has issued, optionally narrowed to a patient or to ones expiring soon.",
            render=render_doctor_prescriptions,
            tool="my_prescriptions_doctor",
            required=("prescription", "prescriptions", "issued", "wrote", "script"),
            optional=("my", "expiring", "expire", "week", "recent", "patient", "how", "many"),
            slots=("query", "expiring_only"),
            examples=("which prescriptions expire this week", "prescriptions I issued"),
        ),
        Intent(
            name="renewal_requests",
            description="Renewal requests pharmacies have raised against this doctor's prescriptions.",
            render=render_renewals,
            tool="renewal_requests",
            required=("renewal", "renewals", "renew"),
            optional=("request", "requests", "pending", "waiting", "how", "many", "approve"),
            examples=("how many renewal requests are waiting", "any renewals pending"),
        ),
        Intent(
            name="my_patients",
            description="People this doctor has prescribed for.",
            render=render_patients,
            tool="my_patients",
            required=("patient", "patients"),
            optional=("my", "list", "how", "many", "find", "search"),
            slots=("query",),
            examples=("how many patients do I have", "find patient Khoury"),
        ),
        Intent(
            name="stock_lookup",
            description="How much of a named product this pharmacy holds, and when it expires.",
            render=render_stock_lookup,
            tool="stock_lookup",
            required=("stock", "have", "shelf", "quantity", "batch", "batches", "many"),
            optional=("we", "do", "how", "much", "left", "of", "in", "got"),
            slots=("query",),
            examples=("how many panadol do we have", "do we have augmentin in stock"),
        ),
        Intent(
            name="stock_alerts",
            description="What is running low or approaching expiry at this pharmacy.",
            render=render_stock_alerts,
            tool="stock_alerts",
            required=("low", "expiring", "expire", "expiry", "running", "alert", "alerts"),
            optional=("what", "is", "out", "soon", "short", "reorder", "restock"),
            examples=("what is running low", "anything expiring soon"),
        ),
        Intent(
            name="sales_summary",
            description="How this pharmacy traded over a recent window.",
            render=render_sales_summary,
            tool="sales_summary",
            required=("sales", "revenue", "trade", "traded", "trading", "turnover", "sold", "takings"),
            optional=("how", "did", "we", "last", "month", "week", "days", "much"),
            slots=("days",),
            examples=("how did we trade over the last 30 days", "sales this month"),
        ),
        Intent(
            name="business_insights",
            description="Ranked findings from this pharmacy's own analytics.",
            render=render_insights,
            tool="business_insights",
            required=("insight", "insights", "analytics", "recommend", "recommendations", "findings"),
            optional=("what", "should", "we", "know", "any", "flag", "flagged"),
            examples=("any insights for us", "what should we know"),
        ),
        Intent(
            name="incoming_orders",
            description="Online orders waiting on this pharmacy to accept or prepare.",
            render=render_incoming_orders,
            tool="incoming_orders",
            required=("order", "orders", "incoming", "online"),
            optional=("waiting", "any", "new", "pending", "accept", "how", "many"),
            examples=("any online orders waiting", "how many orders are pending"),
        ),
        Intent(
            name="platform_overview",
            description="The current shape of the network: pharmacies, orders, drivers.",
            render=render_platform_overview,
            tool="platform_overview",
            required=("overview", "platform", "network", "summary", "summarise", "summarize"),
            optional=("give", "me", "how", "many", "total", "state", "status"),
            examples=("give me a platform overview", "how is the network doing"),
        ),
        Intent(
            name="pending_applications",
            description="Pharmacy applications waiting on review.",
            render=render_pending_applications,
            tool="pending_applications",
            required=("application", "applications", "applicant", "applicants", "signup", "signups"),
            optional=("pending", "waiting", "how", "many", "review", "approve", "new"),
            examples=("how many applications are pending", "any new pharmacy applications"),
        ),
        Intent(
            name="dispatch_snapshot",
            description="Delivery load right now: routes, drivers, unassigned orders.",
            render=render_dispatch,
            tool="dispatch_snapshot",
            required=("dispatch", "route", "routes", "driver", "drivers", "fleet"),
            optional=("look", "like", "how", "many", "now", "active", "online", "unassigned"),
            examples=("what does dispatch look like right now", "how many drivers are online"),
        ),
        Intent(
            name="recent_activity",
            description="The tail of the platform audit trail.",
            render=render_recent_activity,
            tool="recent_activity",
            required=("audit", "activity", "log", "logs", "happened", "recent"),
            optional=("what", "lately", "changes", "trail", "last"),
            examples=("what happened recently", "show me the audit log"),
        ),
        Intent(
            name="next_stop",
            description="The one stop this driver is heading to next.",
            render=render_next_stop,
            tool="next_stop",
            required=("next", "stop"),
            optional=("what", "is", "my", "where", "now", "going", "after"),
            examples=("what is my next stop", "where next"),
        ),
        Intent(
            name="my_route",
            description="This driver's whole current route and how much is left of it.",
            render=render_my_route,
            tool="my_route",
            required=("route", "stops", "left", "remaining", "many"),
            optional=("my", "how", "much", "far", "done", "total"),
            examples=("how many stops are left", "what does my route look like"),
        ),
    )
}

# Reachable from the router without being in any persona's list - these are the two answers
# every persona falls back to, and they read no data at all.
FALLBACK_INTENTS: dict[str, Intent] = {
    "unknown": Intent(name="unknown", description="Nothing matched.", render=render_unknown),
    "clarify": Intent(name="clarify", description="Two readings were equally likely.", render=render_clarify),
}


def get_intent(name: str) -> Intent | None:
    return INTENTS.get(name) or FALLBACK_INTENTS.get(name)
