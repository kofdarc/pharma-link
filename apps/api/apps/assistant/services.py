"""
One turn of the conversation, end to end.

The order of operations here is the security design, so it is worth reading as one piece:
resolve the persona from the authenticated user (never from the request body), route the
message to an intent within that persona's allowlist, run at most one read-only tool through
the allowlist check, and render the reply from the tool result using a template this repo
wrote. Nothing downstream of the parser can widen what was decided upstream of it.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.assistant import composer, personas as persona_module
from apps.assistant import tools
from apps.assistant.intents import get_intent
from apps.assistant.models import AssistantConversation, AssistantMessage
from apps.assistant.parsers.base import ParseResult
from apps.assistant.router import resolve
from apps.assistant.tools.base import ToolContext
from apps.common.location import resolve_origin

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 500
TITLE_CHARS = 120


class ConversationNotFound(Exception):
    """The id presented does not exist, or does not belong to whoever presented it."""


def start_conversation(user, persona) -> AssistantConversation:
    return AssistantConversation.objects.create(user=user if getattr(user, "is_authenticated", False) else None, persona=persona.key)


def load_conversation(conversation_id: str, user) -> AssistantConversation:
    """
    Resume a thread, if it is the caller's to resume.

    For a signed-in caller the owner must match. For an anonymous one the conversation must
    have no owner - so a guest cannot resume a signed-in person's thread even holding its id,
    and a signed-in person cannot adopt a guest thread and inherit its history. The id itself
    is a server-generated UUID4 and is the only handle; it is never derived from anything a
    client supplies.
    """
    try:
        conversation = AssistantConversation.objects.get(id=conversation_id)
    except (AssistantConversation.DoesNotExist, ValueError, TypeError):
        raise ConversationNotFound("No such conversation.") from None

    if getattr(user, "is_authenticated", False):
        if conversation.user_id != user.id:
            raise ConversationNotFound("No such conversation.")
    elif conversation.user_id is not None:
        raise ConversationNotFound("No such conversation.")
    return conversation


def answer(*, user, message: str, conversation: AssistantConversation | None = None, latitude=None, longitude=None) -> dict:
    """
    Take one message and produce one reply, persisting both.

    `latitude`/`longitude` are the device position the client offered with this turn, and are
    the only thing here a caller contributes beyond the message itself. They are search input,
    exactly like the `lat`/`lng` the public search endpoint already accepts - they widen no
    persona, unlock no tool, and name nobody. Everything about *who* this is still comes from
    the auth token. A caller that sends none, or sends nonsense, falls back through
    apps.common.location to whatever the account already has on file, and then to no distance
    at all.
    """
    persona = persona_module.persona_for(user)
    text = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not text:
        raise ValueError("Message is empty.")

    if conversation is None:
        conversation = start_conversation(user, persona)
    elif conversation.persona != persona.key:
        # The thread was started under a different role - the account changed, or somebody is
        # presenting an id from another context. Refusing beats replaying history written for
        # one toolset into a wider one.
        raise ConversationNotFound("No such conversation.")

    parsed = resolve(text, persona)
    intent = get_intent(parsed.intent)
    if intent is None or (parsed.intent not in ("unknown", "clarify") and not persona.allows(parsed.intent)):
        # Belt and braces. Both parsers already filter to the persona's list; this is the
        # assertion that says so out loud at the only point where an intent becomes an action.
        logger.warning("Assistant resolved intent %r outside persona %r", parsed.intent, persona.key)
        intent = get_intent("unknown")
        parsed = ParseResult(intent="unknown", source=parsed.source)

    slots = dict(parsed.slots)
    if parsed.intent == "greeting":
        slots.setdefault("greeting", persona.greeting)

    # Resolved once per turn, before any tool runs, and passed as its own field rather than
    # folded into `slots` - see ToolContext for why the parser must not be able to reach it.
    origin = resolve_origin(user=user, latitude=latitude, longitude=longitude)

    result: dict = {}
    tools_used: list[dict] = []
    if intent.tool:
        try:
            result = tools.execute(
                intent.tool, allowed=frozenset(_allowed_tools(persona)), context=ToolContext(user=user, slots=slots, origin=origin)
            )
            tools_used.append({"name": intent.tool, "slots": slots})
        except tools.ToolNotAllowed:
            logger.warning("Assistant blocked tool %r for persona %r", intent.tool, persona.key)
            intent = get_intent("unknown")

    # The composer only ever runs over data a tool already returned to this exact call - never
    # over an intent with no tool behind it (clinical/emergency/greeting/etc. stay fixed
    # policy text, see apps.assistant.intents), never when there was nothing to describe, and
    # never for an intent that opts out (add_to_cart: its reply must match the action payload
    # word for word). It always has the template as a fallback, so its own failure is
    # invisible to the caller.
    composed = (
        composer.compose(intent=intent, result=result, message=text, persona=persona)
        if intent.tool and intent.compose and result
        else None
    )
    if composed is not None:
        reply = composed
        if tools_used:
            tools_used[0]["composed"] = True
    else:
        reply = intent.render(result, slots)

    # The one turn that hands the client something to do rather than just something to read.
    # It is not an instruction to mutate anything server-side - the cart is browser-local -
    # only the resolved items the widget adds and then offers to undo. Gated on the tool
    # having actually resolved a listing, so a miss produces a plain sentence and no action.
    actions = _cart_actions(result) if intent.name == "add_to_cart" else []
    # `action` stays as the first (or only) resolved item for older clients; `actions` is the
    # full list, which is what a multi-product request ("add x and y") needs.
    action = actions[0] if actions else None

    with transaction.atomic():
        AssistantMessage.objects.create(conversation=conversation, role=AssistantMessage.Role.USER, body=text)
        AssistantMessage.objects.create(
            conversation=conversation,
            role=AssistantMessage.Role.ASSISTANT,
            body=reply,
            tools_used=tools_used,
            provider=parsed.source,
        )
        conversation.last_message_at = timezone.now()
        if not conversation.title:
            conversation.title = text[:TITLE_CHARS]
        conversation.save(update_fields=["last_message_at", "title", "updated_at"])

    return {
        "conversation_id": str(conversation.id),
        "reply": reply,
        "intent": intent.name,
        "persona": persona.key,
        "source": parsed.source,
        "suggestions": list(persona.suggestions),
        "tools_used": [entry["name"] for entry in tools_used],
        # So the widget can say what "near me" meant this turn, and offer to fix it. An
        # answer ranked by distance from an address the person forgot they saved is not
        # wrong, but it is surprising, and silence is what makes it surprising.
        "location_used": origin.describe() if origin is not None else None,
        # Present only on an add_to_cart turn that resolved something; null / [] otherwise.
        "action": action,
        "actions": actions,
    }


def _cart_actions(result: dict) -> list[dict]:
    """
    Shape a resolved cart_add result into the items the web client adds to its basket.

    Handles both shapes cart_add can return: the flat single-product dict, and the
    `{"multi": True, "results": [...]}` one a request naming several products produces.
    """
    rows = result.get("results", []) if result.get("multi") else [result]
    return [_cart_action(row, result) for row in rows if row.get("added")]


def _cart_action(row: dict, outer: dict) -> dict:
    """One resolved listing as an `add_to_basket` action. `outer` carries the shared `basis`."""
    match = row["match"]
    price = match.get("unit_price")
    return {
        "type": "add_to_basket",
        "item": {
            "medicine": match["medicine_id"],
            "name": match["name"],
            "generic": match.get("generic"),
            "image": match.get("image"),
            "quantity": row.get("granted_quantity", row.get("requested_quantity", 1)),
            "requires_prescription": bool(match.get("requires_prescription")),
            "unit_price": float(price) if price is not None else None,
        },
        "meta": {
            "total_listings": row.get("total_listings", 0),
            "basis": row.get("basis", outer.get("basis", "relevance")),
        },
    }


def _allowed_tools(persona) -> set[str]:
    """The tools reachable from this persona's intents - derived, never hand-maintained."""
    names = set()
    for name in persona.intents:
        intent = get_intent(name)
        if intent is not None and intent.tool:
            names.add(intent.tool)
    return names
