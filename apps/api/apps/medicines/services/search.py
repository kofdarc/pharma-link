from __future__ import annotations

from difflib import SequenceMatcher
import re

from django.db import connection
from django.db.models import Q

from apps.medicines.models import Medicine

# Fuzzy-scan fallback: unindexed catalogs won't grow past this before the
# Postgres trigram path (below) takes over, so an O(n) Python scan stays cheap.
FUZZY_SCAN_LIMIT = 500
FUZZY_MATCH_THRESHOLD = 0.68
BEST_MATCH_SCAN_LIMIT = 1000
BEST_MATCH_THRESHOLD = 0.78


def normalize_name(value: str) -> str:
    """
    Lowercase and collapse punctuation/whitespace, keeping any Unicode letters
    or digits intact — not just ASCII. `\\w` is Unicode-aware in Python 3, so
    this preserves Arabic script (e.g. "بنادول") and accented Latin (e.g.
    French drug names) instead of stripping them to an empty, unmatchable
    string, which the old `[^a-z0-9]+` pattern did.
    """
    return re.sub(r"[^\w]+", " ", (value or "").lower(), flags=re.UNICODE).strip()


def _uses_postgres_trigram() -> bool:
    return connection.vendor == "postgresql"


def _fuzzy_scan(normalized: str, candidates, threshold: float):
    """Python fallback fuzzy match, used on any backend without pg_trgm (e.g. the sqlite dev DB)."""
    scored = []
    for medicine in candidates:
        names = [medicine.brand_name, medicine.generic_name, *[alias.alias for alias in medicine.aliases.all()]]
        best = max((SequenceMatcher(None, normalized, normalize_name(name)).ratio() for name in names if name), default=0)
        if best >= threshold:
            scored.append((best, medicine))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _trigram_search(qs, query: str, seen: set, limit: int):
    """
    Postgres-only fast path: trigram similarity over indexed columns instead
    of an in-Python scan (see migration 0006_trigram_search_indexes). Falls
    back to the caller's Python scan on any other backend.
    """
    from django.contrib.postgres.search import TrigramSimilarity

    scored = (
        qs.exclude(id__in=seen)
        .annotate(
            similarity=TrigramSimilarity("brand_name", query)
            + TrigramSimilarity("generic_name", query)
        )
        .filter(similarity__gte=FUZZY_MATCH_THRESHOLD)
        .order_by("-similarity")
    )
    return list(scored[:limit])


def search_medicines(query: str, *, active_only: bool = True, limit: int = 25):
    normalized = normalize_name(query)
    qs = Medicine.objects.prefetch_related("aliases").all()
    if active_only:
        qs = qs.filter(is_active=True)
    if not normalized:
        return qs.order_by("brand_name")[:limit]
    direct = qs.filter(
        Q(brand_name__icontains=query)
        | Q(generic_name__icontains=query)
        | Q(aliases__alias__icontains=query)
    ).distinct()
    results = list(direct[:limit])
    if len(results) >= limit:
        return results

    seen = {m.id for m in results}
    remaining = limit - len(results)
    if _uses_postgres_trigram():
        return results + _trigram_search(qs, query, seen, remaining)

    candidates = qs.exclude(id__in=seen).prefetch_related("aliases")[:FUZZY_SCAN_LIMIT]
    scored = _fuzzy_scan(normalized, candidates, FUZZY_MATCH_THRESHOLD)
    return results + [medicine for _score, medicine in scored[:remaining]]


def best_catalog_match(raw_name: str):
    normalized = normalize_name(raw_name)
    if not normalized:
        return None, 0

    exact = (
        Medicine.objects.filter(is_active=True)
        .filter(Q(brand_name__iexact=raw_name) | Q(generic_name__iexact=raw_name) | Q(aliases__alias__iexact=raw_name))
        .distinct()
        .first()
    )
    if exact:
        return exact, 1

    if _uses_postgres_trigram():
        # Trigram fast path covers brand_name/generic_name at catalog scale.
        # Fuzzy alias matching (e.g. a locally-known brand not yet aliased)
        # still falls back to the Python scan below on every backend — the
        # aggregate-across-related-rows trigram query is a known follow-up,
        # not silently solved here.
        from django.contrib.postgres.search import TrigramSimilarity

        best = (
            Medicine.objects.filter(is_active=True)
            .annotate(similarity=TrigramSimilarity("brand_name", raw_name) + TrigramSimilarity("generic_name", raw_name))
            .order_by("-similarity")
            .first()
        )
        if best is not None and best.similarity >= BEST_MATCH_THRESHOLD:
            return best, round(best.similarity, 2)

    candidates = list(Medicine.objects.filter(is_active=True).prefetch_related("aliases")[:BEST_MATCH_SCAN_LIMIT])
    best_score = 0
    best = None
    for medicine in candidates:
        names = [medicine.brand_name, medicine.generic_name, *[alias.alias for alias in medicine.aliases.all()]]
        score = max((SequenceMatcher(None, normalized, normalize_name(name)).ratio() for name in names if name), default=0)
        if score > best_score:
            best_score = score
            best = medicine
    if best_score >= BEST_MATCH_THRESHOLD:
        return best, round(best_score, 2)
    return None, round(best_score, 2)

