"""
The free parser: weighted keyword overlap, no model, no network, no cost.

It runs first on every message and answers the phrasings people actually repeat - "where is my
order", "what is running low", "any renewals pending". When it is not confident it says so by
returning None, and the message falls through to whatever parser is configured behind it. It
never guesses, because a wrong confident answer here is worse than no answer: the person can
rephrase, but they cannot tell that the stock figure they were given is for the wrong drug.
"""

from __future__ import annotations

import re

from apps.assistant.intents import INTENTS
from apps.assistant.parsers.base import IntentParser, ParseResult

# Enough of a stemmer for keyword matching and no more. A real stemmer is the wrong tool: it
# would collapse pairs this table deliberately keeps apart, and it cannot be read at a glance
# by whoever next wonders why "expiring" matched but "expired" did not.
LEMMAS = {
    "has": "have", "had": "have", "having": "have", "got": "have", "gets": "get",
    "sells": "sell", "selling": "sell", "sold": "sell", "costs": "cost", "prices": "price",
    "orders": "order", "ordering": "order", "ordered": "order",
    "prescriptions": "prescription", "scripts": "script", "rxs": "rx",
    "pharmacies": "pharmacy", "pharmacie": "pharmacy", "pharmacien": "pharmacy",
    "expires": "expire", "expiring": "expire", "expired": "expire", "expiry": "expire",
    "refills": "refill", "repeats": "repeat", "renewals": "renewal", "renewing": "renew", "renews": "renew",
    "patients": "patient", "applications": "application", "applicants": "applicant",
    "drivers": "driver", "routes": "route", "stops": "stop", "batches": "batch",
    "deliveries": "delivery", "delivered": "deliver", "delivering": "deliver", "delivers": "deliver",
    "works": "work", "working": "work", "insights": "insight", "logs": "log", "alerts": "alert",
    "running": "run", "remaining": "remain", "summarize": "summary", "summarise": "summary",
    "available": "availability", "traded": "trade", "trading": "trade",
}

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do", "does", "did",
    "i", "me", "my", "we", "our", "us", "you", "your", "it", "its", "this", "that", "these",
    "to", "of", "in", "on", "at", "for", "from", "with", "and", "or", "but", "if", "so",
    "can", "could", "would", "should", "will", "shall", "may", "might", "please", "just",
    "what", "which", "who", "when", "where", "how", "why", "any", "some", "there", "here",
    "much", "many", "got", "get", "tell", "show", "give", "find", "know", "want", "need",
}

TOKEN_RE = re.compile(r"[a-z0-9؀-ۿ]+")
DURATION_RE = re.compile(r"(\d+)\s*(day|days|week|weeks|month|months)\b")
# Splits "add creatine, redoxon and vitamin d" into its products. Deliberately literal - a
# comma, an ampersand, or a standalone "and"/"plus" between names. A name that itself contains
# "and" ("vitamin a and d") is a rare miss the person can fix by adding it on its own line.
PRODUCT_SPLIT_RE = re.compile(r"\s*(?:,|;|&|\+|\band\b|\bplus\b)\s*", re.IGNORECASE)

# A match needs a required keyword plus corroboration; a winner needs to be clearly ahead of
# the runner-up. Below either bar the parser abstains rather than picking the taller of two
# shrugs.
# One required keyword clears the bar on its own - "how much is panadol" carries exactly one
# and is a perfectly clear question. Precision is protected by the margin rather than by the
# bar: two intents that each catch one keyword tie, and a tie asks instead of guessing.
REQUIRED_WEIGHT = 3
CONFIDENT_SCORE = 3
CONFIDENT_MARGIN = 2
# A message whose every meaningful word is one intent's vocabulary is that intent, even when
# it is too short to clear the score bar on its own. "hi" and "stock" are whole questions.
EXACT_COVER_BONUS = 2

# Checked as substrings, before any scoring, and they win outright.
#
# These two lists are the reason the clinical and emergency redirects are reachable at all
# without a model behind the router. Token overlap is the wrong instrument for them - the
# signal is a phrase, not a bag of words - so they get literal phrase matching instead, and
# they are deliberately allowed to be over-eager. Being wrong in this direction costs someone
# an unnecessary "ask a pharmacist"; being wrong in the other direction costs them a shrug
# where the product should have handed them to a human. Neither can produce clinical advice,
# because no intent in this app renders any.
#
# Arabic and French phrases are included here too, undiacritized to match how people actually
# type - not because this parser understands either language, but because these two redirects
# are the one place where "the free tier missed it" and "the free tier misrouted it" are not
# equally cheap mistakes. A missed stock question just gets rephrased; a missed emergency in a
# language the phrase list didn't cover falls through to a shrug instead of a redirect, and
# that gap is real: it is exactly what caught the Arabic overdose message in testing before
# these were added (the OpenRouter fallback caught it that time, but the free tier - the one
# still running if that fallback is ever off or down - did not). Coverage here is deliberately
# not exhaustive translation of every English entry - it is the core, most-likely-to-be-typed
# phrasing per language, including a couple of colloquial Lebanese variants alongside the
# formal ones since that is this product's primary market.
EMERGENCY_PHRASES = (
    "overdose", "overdosed", "od'd", "can't breathe", "cant breathe", "not breathing",
    "chest pain", "unconscious", "passed out", "collapsed", "bleeding", "poisoned",
    "poisoning", "allergic reaction", "anaphyla", "emergency", "ambulance", "suicide",
    # Arabic
    "جرعة زائدة", "جرعة زايدة", "تناولت جرعة زائدة", "ما بيقدر يتنفس", "مش قادر يتنفس",
    "لا يستطيع التنفس", "توقف عن التنفس", "ألم في الصدر", "فاقد الوعي", "إغماء", "أغمي عليه",
    "نزيف", "تسمم", "تسمم دوائي", "رد فعل تحسسي", "حساسية شديدة", "طوارئ", "إسعاف", "انتحار",
    # French
    "overdose", "surdose", "ne peut pas respirer", "ne peut plus respirer",
    "arrêt respiratoire", "douleur thoracique", "douleur à la poitrine", "inconscient",
    "évanoui", "effondré", "saignement abondant", "empoisonnement", "réaction allergique",
    "choc anaphylactique", "urgence", "ambulance", "suicide",
)
CLINICAL_PHRASES = (
    "dose", "dosage", "how much should i take", "how many should i take", "side effect",
    "side-effect", "interaction", "interact with", "safe to take", "safe to use",
    "can i take", "should i take", "instead of", "substitute for", "replace it with",
    "symptom", "diagnos", "is it bad", "will it help", "good for", "cure", "treat my",
    "am i allergic", "pregnan", "breastfeed",
    # Arabic
    "جرعة", "كم الجرعة", "كم يجب أن آخذ", "قديش لازم آخذ", "آثار جانبية", "أعراض جانبية",
    "تداخل دوائي", "آمن مع", "هل يمكنني أخذ", "بديل عن", "بدلاً من", "أعراض", "تشخيص",
    "هل هذا خطير", "حامل", "حبلى", "رضاعة", "مرضعة",
    # French
    "dose", "dosage", "combien dois-je prendre", "quelle dose", "effet secondaire",
    "effets secondaires", "interaction médicamenteuse", "sans danger avec",
    "puis-je prendre", "dois-je prendre", "au lieu de", "remplacer par", "symptôme",
    "diagnostic", "enceinte", "allaitement",
)


def lemma(token: str) -> str:
    return LEMMAS.get(token, token)


def tokenize(message: str) -> list[str]:
    return [lemma(token) for token in TOKEN_RE.findall(message.lower())]


def _lemmatised(words: tuple[str, ...]) -> frozenset[str]:
    return frozenset(lemma(word.lower()) for word in words)


# Built once at import. Keyword lists in intents.py are written for a human to read, in
# whatever form came naturally; matching happens against their lemmatised form so that a list
# saying "orders" still matches someone who typed "order".
_REQUIRED = {name: _lemmatised(intent.required) for name, intent in INTENTS.items()}
_OPTIONAL = {name: _lemmatised(intent.optional) for name, intent in INTENTS.items()}


def _score(name: str, tokens: set[str], meaningful: set[str]) -> int:
    required = _REQUIRED[name] & tokens
    if not required:
        return 0
    score = REQUIRED_WEIGHT * len(required) + len(_OPTIONAL[name] & tokens)
    if meaningful and meaningful <= (_REQUIRED[name] | _OPTIONAL[name]):
        score += EXACT_COVER_BONUS
    return score


def safety_intent(message: str) -> str | None:
    """An emergency or clinical phrase anywhere in the message, checked before scoring."""
    lowered = message.lower()
    if any(phrase in lowered for phrase in EMERGENCY_PHRASES):
        return "emergency"
    if any(phrase in lowered for phrase in CLINICAL_PHRASES):
        return "clinical_question"
    return None


def extract_duration_days(message: str) -> int | None:
    match = DURATION_RE.search(message.lower())
    if not match:
        return None
    count, unit = int(match.group(1)), match.group(2)
    if unit.startswith("week"):
        return count * 7
    if unit.startswith("month"):
        return count * 30
    return count


def extract_slots(message: str, intent_name: str, tokens: list[str]) -> dict:
    """
    Pull the free-text subject out of a matched message.

    Whatever is left once the intent's own keywords and the stopwords are removed is the
    subject - "how many panadol do we have" leaves "panadol". That remainder is handed to
    `search_medicines`, which already does trigram and difflib matching, so misspellings are
    somebody else's solved problem rather than a table of variants maintained here.
    """
    intent = INTENTS[intent_name]
    slots: dict = {}

    if "days" in intent.slots:
        days = extract_duration_days(message)
        if days is not None:
            slots["days"] = days
    if "expiring_only" in intent.slots and ({"expire", "soon", "week"} & set(tokens)):
        slots["expiring_only"] = True

    if "quantity" in intent.slots:
        count = re.search(r"\b(\d{1,2})\b", message)
        if count:
            slots["quantity"] = int(count.group(1))
    if "sort" in intent.slots and re.search(r"cheap|lowest|least expensive|best price|most affordable", message.lower()):
        slots["sort"] = "price"

    claimed = _REQUIRED[intent_name] | _OPTIONAL[intent_name] | STOPWORDS

    # "add creatine and vitamin d to my cart" - one intent, several products. Split on the raw
    # message (the connectors are stopwords, so they are gone by the time `tokens` is built),
    # then strip each fragment down to its product name the same way the single-query path does.
    if "queries" in intent.slots:
        fragments = []
        for fragment in PRODUCT_SPLIT_RE.split(message.lower()):
            words = [word for word in tokenize(fragment) if word not in claimed and not word.isdigit()]
            if words:
                fragments.append(" ".join(words))
        if len(fragments) > 1:
            slots["queries"] = fragments
            slots["query"] = fragments[0]
            return slots

    text_slot = next((name for name in ("query", "area", "reference") if name in intent.slots), None)
    if text_slot:
        # A bare number is a quantity, never part of the product name ("add 2 panadol").
        remainder = [token for token in tokens if token not in claimed and not token.isdigit()]
        if remainder:
            slots[text_slot] = " ".join(remainder)
    return slots


def _most_explained(scored: list[tuple[int, str]], best_score: int, meaningful: set[str]) -> str | None:
    """
    Break a tie by which reading accounts for more of what was actually said, or give up.

    Scoring counts how many of an intent's keywords the message hit. It cannot see the
    opposite - how much of the message the intent leaves unexplained - and that is exactly
    where near-ties come from. "which is the closest pharmacy that has amoxicillin" hits one
    required keyword plus two optional ones for both `find_pharmacies` ("pharmacy",
    "closest", "which") and `search_availability` ("has", "closest", "pharmacy"), so they
    tie, even though only one of them accounts for the word "has" - and "has <something>" is
    the whole question.

    So the tiebreak is coverage: of the meaningful words in the message, what fraction does
    each reading claim? A reading that explains three of four words beats one that explains
    two. Returns None unless exactly one contender is strictly ahead, so a real ambiguity
    still reaches the clarify path rather than being resolved by a coin toss.

    This only ever runs on messages already headed for "did you mean" - it can turn a shrug
    into an answer, never a confident answer into a different one.
    """
    if not meaningful:
        return None
    contenders = [name for score, name in scored if best_score - score < CONFIDENT_MARGIN]
    if len(contenders) < 2:
        return None

    claimed = {name: len(meaningful & (_REQUIRED[name] | _OPTIONAL[name])) for name in contenders}
    ranked = sorted(claimed.items(), key=lambda item: -item[1])
    if ranked[0][1] <= ranked[1][1]:
        return None
    return ranked[0][0]


class KeywordIntentParser(IntentParser):
    code = "keyword"

    def parse(self, message: str, persona) -> ParseResult | None:
        tokens = tokenize(message)
        if not tokens:
            return None
        token_set = set(tokens)
        meaningful = token_set - STOPWORDS

        # The two redirects outrank everything. A message mentioning a dose is a clinical
        # question even when it also names a product the catalogue would happily look up.
        safety = safety_intent(message)
        if safety is not None and persona.allows(safety):
            return ParseResult(intent=safety, confidence=1.0, source=self.code)

        # Only the persona's own intents are ever scored. An unauthorised intent is not
        # rejected later - it is never a candidate in the first place.
        scored = sorted(
            (
                (_score(name, token_set, meaningful), name)
                for name in persona.intents
                if name in INTENTS
            ),
            reverse=True,
        )
        if not scored or scored[0][0] < CONFIDENT_SCORE:
            return None

        best_score, best_name = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0
        if best_score - runner_up < CONFIDENT_MARGIN:
            settled = _most_explained(scored, best_score, meaningful)
            if settled is None:
                # Two readings are genuinely close. Asking is cheaper than being wrong, and it
                # gives the person the vocabulary the router actually recognises.
                options = tuple(INTENTS[name].description.rstrip(".").lower() for _, name in scored[:2])
                return ParseResult(intent="clarify", slots={"options": list(options)}, confidence=0.4, source=self.code, options=options)
            best_name = settled

        return ParseResult(
            intent=best_name,
            slots=extract_slots(message, best_name, tokens),
            confidence=min(1.0, best_score / 8),
            source=self.code,
        )
