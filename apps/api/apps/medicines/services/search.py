from __future__ import annotations

from difflib import SequenceMatcher
import re

from django.db.models import Q

from apps.medicines.models import Medicine


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


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
    candidates = qs.exclude(id__in=seen).prefetch_related("aliases")[:500]
    scored = []
    for medicine in candidates:
        names = [medicine.brand_name, medicine.generic_name, *[alias.alias for alias in medicine.aliases.all()]]
        best = max((SequenceMatcher(None, normalized, normalize_name(name)).ratio() for name in names if name), default=0)
        if best >= 0.68:
            scored.append((best, medicine))
    scored.sort(key=lambda item: item[0], reverse=True)
    return results + [medicine for _score, medicine in scored[: max(0, limit - len(results))]]


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

    candidates = list(Medicine.objects.filter(is_active=True).prefetch_related("aliases")[:1000])
    best_score = 0
    best = None
    for medicine in candidates:
        names = [medicine.brand_name, medicine.generic_name, *[alias.alias for alias in medicine.aliases.all()]]
        score = max((SequenceMatcher(None, normalized, normalize_name(name)).ratio() for name in names if name), default=0)
        if score > best_score:
            best_score = score
            best = medicine
    if best_score >= 0.78:
        return best, round(best_score, 2)
    return None, round(best_score, 2)

