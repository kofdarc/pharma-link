"""
Basket sourcing: decide WHICH pharmacies fill a shopper's basket.

This is the first half of the delivery problem. Every extra pharmacy on an order adds a
pickup stop, so the cheapest way to keep routes short is to not create the stops in the
first place. The planner therefore treats sourcing as a weighted set-cover: cover all
requested units using the fewest, closest, best-rated pharmacies, and only split a basket
when no single pharmacy can carry it.

Cost model per candidate pharmacy (lower is better):
    STOP_PENALTY                     one-off cost of adding a pickup stop at all
  + DISTANCE_WEIGHT * detour_km      how far off the shopper's doorstep it sits
  + goods cost of the covered units  free-priced items differ between pharmacies
  + RATING_WEIGHT * (5 - rating)     past shopper experience
  + RELIABILITY_WEIGHT * shortfall%  how often this pharmacy fails an accepted order
  + FRESHNESS_WEIGHT * stale hours   how long since a connected POS last confirmed this stock

Greedy set-cover with this cost is a 1+ln(n) approximation, and a drop pass afterwards
removes any pharmacy whose items the others can absorb.

Freshness only penalises pharmacies whose stock is fed by the POS connector: a pharmacy
with no `last_pos_observed_at` on its batches (dashboard-managed, or never yet synced)
is treated as live and pays nothing, since there is no observation to call stale.

Those weights are the platform's own judgement about what a good plan is, and they are
what `plan_basket` uses by default. A shopper may reasonably want a different trade-off,
so `Strategy` re-weighs the same cost model - faster, cheaper, one pharmacy only - and
`fulfillment_options` plans the basket every way at once for them to choose from. Every
option returned is a plan against live stock; a strategy with no answer is left out
rather than shown empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db.models import Min, Sum
from django.utils import timezone

from apps.common.geo import DROPOFF_SERVICE_MINUTES, PICKUP_SERVICE_MINUTES, road_km, travel_minutes
from apps.inventory.models import InventoryBatch
from apps.medicines.models import Medicine
from apps.pharmacies.models import Pharmacy

STOP_PENALTY = Decimal("6.0")
DISTANCE_WEIGHT = Decimal("1.2")
RATING_WEIGHT = Decimal("1.5")
RELIABILITY_WEIGHT = Decimal("0.08")
FRESHNESS_WEIGHT = Decimal("0.15")
STALE_GRACE_HOURS = Decimal("2")
STALE_PENALTY_CAP_HOURS = Decimal("48")
UNRATED_PHARMACY_RATING = Decimal("3.8")

# Every estimate is a range. The upper bound is not padding for its own sake - a
# quoted single number reads as a promise the platform cannot keep.
ETA_SPREAD = Decimal("1.35")


@dataclass(frozen=True)
class Strategy:
    """
    One way of weighing the same live stock.

    The set-cover in `plan_basket` is unchanged between strategies; only what it
    considers expensive moves. `best` is the platform's own judgement and its
    weights are the module constants above, so a plain `plan_basket()` call
    behaves exactly as it always has.

    `goods_weight` is what actually separates `cheapest` from the rest: raising
    it while dropping the stop penalty makes the planner accept another pickup
    stop in exchange for a lower shelf price, which is the trade a shopper
    picking "lowest cost" is asking for.
    """

    key: str
    label: str
    tagline: str
    stop_penalty: Decimal = STOP_PENALTY
    distance_weight: Decimal = DISTANCE_WEIGHT
    goods_weight: Decimal = Decimal("1")
    rating_weight: Decimal = RATING_WEIGHT
    reliability_weight: Decimal = RELIABILITY_WEIGHT
    freshness_weight: Decimal = FRESHNESS_WEIGHT
    # Cost per minute a pharmacy takes to pack an order. Zero everywhere except
    # `fastest`, where it is the whole point.
    preparation_weight: Decimal = Decimal("0")
    # Only consider pharmacies that can carry the entire basket alone.
    single_pharmacy_only: bool = False
    # Take the one-stop shortcut whenever a pharmacy can cover everything, without
    # costing a split against it. True for every strategy except `cheapest`, which
    # exists precisely to find out whether splitting buys a lower price.
    prefer_single_stop: bool = True
    # Source each medicine from whoever sells it cheapest, instead of covering the
    # basket with the fewest good pharmacies. Only `cheapest` does this - see
    # `_cheapest_allocation` for why the set-cover cannot answer this question.
    per_item_lowest_price: bool = False


BEST = Strategy(
    key="best",
    label="Best overall",
    tagline="The quickest way to get everything, at close to the lowest price.",
)

FASTEST = Strategy(
    key="fastest",
    label="Fastest",
    tagline="Pharmacies that can start preparing straight away, and are closest to you.",
    distance_weight=DISTANCE_WEIGHT * 3,
    preparation_weight=Decimal("0.5"),
    # A pharmacy whose connector went quiet may be packing against stock it no
    # longer has, which is the slowest outcome of all.
    freshness_weight=FRESHNESS_WEIGHT * 2,
)

CHEAPEST = Strategy(
    key="cheapest",
    label="Lowest cost",
    tagline="The lowest listed prices, accepting a longer wait and more pickups.",
    stop_penalty=STOP_PENALTY / 4,
    distance_weight=DISTANCE_WEIGHT / 2,
    goods_weight=Decimal("3"),
    rating_weight=Decimal("0"),
    prefer_single_stop=False,
    per_item_lowest_price=True,
)

SINGLE = Strategy(
    key="single",
    label="One pharmacy",
    tagline="Everything from a single pharmacy, if you would rather keep it together.",
    single_pharmacy_only=True,
)

STRATEGIES = [BEST, FASTEST, CHEAPEST, SINGLE]


@dataclass
class Candidate:
    pharmacy: Pharmacy
    distance_km: float
    # medicine_id -> (units it can supply, unit price)
    offer: dict = field(default_factory=dict)
    # Oldest POS confirmation among this pharmacy's batches covering the basket; None if
    # nothing here came from a sync (dashboard-only stock is not "stale", it's live by hand).
    last_observed_at: datetime | None = None

    @property
    def rating(self) -> Decimal:
        if self.pharmacy.rating_count == 0:
            return UNRATED_PHARMACY_RATING
        return Decimal(str(self.pharmacy.rating_average))

    @property
    def stale_hours(self) -> Decimal:
        if self.last_observed_at is None:
            return Decimal("0")
        elapsed_hours = Decimal(str((timezone.now() - self.last_observed_at).total_seconds() / 3600))
        return min(max(Decimal("0"), elapsed_hours - STALE_GRACE_HOURS), STALE_PENALTY_CAP_HOURS)

    def coverage(self, outstanding: dict[str, int]) -> dict[str, int]:
        covered = {}
        for medicine_id, needed in outstanding.items():
            supply = self.offer.get(medicine_id)
            if supply and needed > 0:
                covered[medicine_id] = min(needed, supply[0])
        return {key: value for key, value in covered.items() if value > 0}

    def cost_for(self, covered: dict[str, int], strategy: "Strategy" = None) -> Decimal:
        strategy = strategy or BEST
        goods = sum((self.offer[medicine_id][1] * units for medicine_id, units in covered.items()), Decimal("0"))
        return (
            strategy.stop_penalty
            + strategy.distance_weight * Decimal(str(round(self.distance_km, 3)))
            + strategy.goods_weight * goods
            + strategy.rating_weight * (Decimal("5") - self.rating)
            + strategy.reliability_weight * (Decimal("100") - Decimal(str(self.pharmacy.fulfillment_success_rate)))
            + strategy.freshness_weight * self.stale_hours
            + strategy.preparation_weight * Decimal(str(self.pharmacy.order_preparation_minutes))
        )


def _cheapest_allocation(
    candidates: list[Candidate], outstanding: dict[str, int]
) -> tuple[list[tuple[Candidate, dict[str, int]]], dict[str, int], list[str]]:
    """
    Each medicine from whoever sells it cheapest, however many stops that takes.

    The greedy set-cover in `plan_basket` cannot answer this. It scores a
    candidate on the whole slice it can cover, so a pharmacy holding the entire
    basket always wins on cost-per-unit even when another sells half of it for a
    quarter of the price - the saving is invisible until you look line by line.
    So the cost-led strategy looks line by line.

    Distance still breaks ties, because between two pharmacies charging the same
    the nearer one is strictly better. Regulated medicines are priced identically
    everywhere by law, so for most baskets this lands on the same plan as `best`
    and gets collapsed away.
    """
    picked: dict = {}
    explanation: list[str] = []
    remaining = dict(outstanding)

    for medicine_id, units in outstanding.items():
        offers = sorted(
            (candidate for candidate in candidates if candidate.offer.get(medicine_id, (0, 0))[0] > 0),
            key=lambda candidate: (candidate.offer[medicine_id][1], candidate.distance_km),
        )
        for candidate in offers:
            if remaining[medicine_id] <= 0:
                break
            take = min(remaining[medicine_id], candidate.offer[medicine_id][0])
            picked.setdefault(id(candidate), (candidate, {}))[1][medicine_id] = take
            remaining[medicine_id] -= take

    chosen = list(picked.values())
    if len(chosen) > 1:
        explanation.append(
            f"Split across {len(chosen)} pharmacies so every item comes from whoever lists it cheapest, "
            "which costs an extra pickup."
        )
    elif chosen:
        explanation.append(f"{chosen[0][0].pharmacy.name} lists every item at the lowest price nearby, so one stop covers it.")
    return chosen, remaining, explanation


def public_cap(pharmacy: Pharmacy) -> int:
    return pharmacy.public_max_quantity_per_item or settings.PUBLIC_MAX_QUANTITY_PER_ITEM


def build_candidates(*, medicine_ids: list[str], latitude: float, longitude: float, radius_km: float | None = None) -> list[Candidate]:
    """Everything the network can currently offer for these medicines, within reach of the shopper."""
    today = timezone.localdate()
    radius_km = radius_km or settings.MAX_SOURCING_RADIUS_KM

    rows = (
        InventoryBatch.objects.filter(
            medicine_id__in=medicine_ids,
            pharmacy__is_active=True,
            pharmacy__is_public=True,
            pharmacy__accepts_online_orders=True,
            medicine__is_active=True,
            public_availability_enabled=True,
            is_archived=False,
            current_quantity__gt=0,
        )
        .exclude(expiry_date__lt=today)
        .values("pharmacy_id", "medicine_id")
        .annotate(units=Sum("current_quantity"), held=Sum("reserved_quantity"))
    )

    pharmacy_ids = {row["pharmacy_id"] for row in rows}
    if not pharmacy_ids:
        return []
    pharmacies = {item.id: item for item in Pharmacy.objects.filter(id__in=pharmacy_ids)}

    # Cheapest live price per (pharmacy, medicine); regulated items are identical everywhere by law.
    price_rows = (
        InventoryBatch.objects.filter(pharmacy_id__in=pharmacy_ids, medicine_id__in=medicine_ids, is_archived=False, current_quantity__gt=0)
        .exclude(expiry_date__lt=today)
        .values("pharmacy_id", "medicine_id", "selling_price")
    )
    prices: dict[tuple, Decimal] = {}
    for row in price_rows:
        key = (row["pharmacy_id"], row["medicine_id"])
        price = row["selling_price"]
        if key not in prices or price < prices[key]:
            prices[key] = price

    # Oldest POS confirmation per pharmacy across the batches in play; a pharmacy relying
    # on a connector that has gone quiet should not rank identically to one syncing live.
    freshness_by_pharmacy: dict = {
        row["pharmacy_id"]: row["oldest_observation"]
        for row in (
            InventoryBatch.objects.filter(pharmacy_id__in=pharmacy_ids, medicine_id__in=medicine_ids, is_archived=False, current_quantity__gt=0)
            .exclude(expiry_date__lt=today)
            .values("pharmacy_id")
            .annotate(oldest_observation=Min("last_pos_observed_at"))
        )
        if row["oldest_observation"] is not None
    }

    candidates: dict = {}
    for row in rows:
        pharmacy = pharmacies[row["pharmacy_id"]]
        if pharmacy.latitude is None or pharmacy.longitude is None:
            continue
        distance = road_km(latitude, longitude, float(pharmacy.latitude), float(pharmacy.longitude))
        if distance > radius_km:
            continue
        sellable = max(0, (row["units"] or 0) - (row["held"] or 0))
        visible = min(sellable, public_cap(pharmacy))
        if visible <= 0:
            continue
        candidate = candidates.setdefault(
            pharmacy.id, Candidate(pharmacy=pharmacy, distance_km=distance, last_observed_at=freshness_by_pharmacy.get(pharmacy.id))
        )
        candidate.offer[str(row["medicine_id"])] = (visible, prices.get((pharmacy.id, row["medicine_id"]), Decimal("0")))
    return list(candidates.values())


def plan_basket(
    *,
    items: list[dict],
    latitude: float,
    longitude: float,
    radius_km: float | None = None,
    strategy: Strategy | None = None,
) -> dict:
    """
    items: [{"medicine": uuid-ish, "quantity": int}]
    Returns the allocation, what could not be sourced, and why the plan looks the way it does.

    `strategy` re-weighs what counts as expensive. For every strategy but
    `cheapest` that is all it does - the set-cover is unchanged; `cheapest`
    swaps in a per-item allocation, for the reason given in
    `_cheapest_allocation`. Omitted, `strategy` is BEST, which is the behaviour
    this planner has always had.
    """
    strategy = strategy or BEST
    requested: dict[str, int] = {}
    for entry in items:
        key = str(entry["medicine"])
        requested[key] = requested.get(key, 0) + int(entry["quantity"])
    if not requested:
        return {
            "allocations": [],
            "unfulfilled": [],
            "items_subtotal": Decimal("0"),
            "pharmacy_count": 0,
            "eta_minutes_low": None,
            "eta_minutes_high": None,
            "explanation": [],
        }

    medicines = {str(item.id): item for item in Medicine.objects.filter(id__in=list(requested), is_active=True)}
    candidates = build_candidates(medicine_ids=list(requested), latitude=latitude, longitude=longitude, radius_km=radius_km)

    outstanding = dict(requested)
    chosen: list[tuple[Candidate, dict[str, int]]] = []
    explanation: list[str] = []

    single_stop = [
        candidate
        for candidate in candidates
        if all(candidate.offer.get(medicine_id, (0, 0))[0] >= units for medicine_id, units in requested.items())
    ]
    if strategy.single_pharmacy_only:
        # No pharmacy can carry the whole basket, so this strategy has no answer.
        # Reporting everything as unsourced is honest; inventing a split here
        # would be answering a question the shopper did not ask.
        candidates = single_stop
    if strategy.per_item_lowest_price:
        chosen, outstanding, explanation = _cheapest_allocation(candidates, outstanding)
    elif single_stop and (strategy.prefer_single_stop or strategy.single_pharmacy_only):
        # One stop beats every split: pick the best single pharmacy outright.
        best = min(single_stop, key=lambda candidate: candidate.cost_for(candidate.coverage(requested), strategy))
        chosen.append((best, dict(requested)))
        outstanding = {}
        explanation.append(f"{best.pharmacy.name} covers the whole basket in one stop ({best.distance_km:.1f} km away), so no split was needed.")
    else:
        while any(units > 0 for units in outstanding.values()):
            scored = []
            for candidate in candidates:
                if any(candidate is picked for picked, _ in chosen):
                    continue
                covered = candidate.coverage(outstanding)
                if not covered:
                    continue
                units = sum(covered.values())
                scored.append((candidate.cost_for(covered, strategy) / Decimal(units), candidate, covered))
            if not scored:
                break
            scored.sort(key=lambda entry: entry[0])
            _cost_per_unit, candidate, covered = scored[0]
            chosen.append((candidate, covered))
            for medicine_id, units in covered.items():
                outstanding[medicine_id] -= units
            explanation.append(
                f"{candidate.pharmacy.name} ({candidate.distance_km:.1f} km, rating {candidate.rating:.1f}) "
                f"added for {sum(covered.values())} unit(s): best cost per unit at that point."
            )

        # Drop pass: a pharmacy is redundant if the others can absorb everything it holds.
        for index in range(len(chosen) - 1, -1, -1):
            candidate, covered = chosen[index]
            others = [entry for position, entry in enumerate(chosen) if position != index]
            spare = {}
            for other, other_covered in others:
                for medicine_id, units in covered.items():
                    capacity = other.offer.get(medicine_id, (0, Decimal("0")))[0] - other_covered.get(medicine_id, 0)
                    if capacity > 0:
                        spare[medicine_id] = spare.get(medicine_id, 0) + capacity
            if all(spare.get(medicine_id, 0) >= units for medicine_id, units in covered.items()):
                for medicine_id, units in covered.items():
                    remaining = units
                    for other, other_covered in others:
                        if remaining <= 0:
                            break
                        capacity = other.offer.get(medicine_id, (0, Decimal("0")))[0] - other_covered.get(medicine_id, 0)
                        take = min(capacity, remaining)
                        if take > 0:
                            other_covered[medicine_id] = other_covered.get(medicine_id, 0) + take
                            remaining -= take
                explanation.append(f"Dropped {candidate.pharmacy.name}: the other pharmacies absorbed its items, removing one pickup stop.")
                chosen.pop(index)

    allocations = []
    subtotal = Decimal("0")
    for candidate, covered in chosen:
        lines = []
        pharmacy_subtotal = Decimal("0")
        for medicine_id, units in covered.items():
            medicine = medicines.get(medicine_id)
            unit_price = candidate.offer[medicine_id][1]
            if medicine is not None and medicine.is_price_regulated:
                unit_price = medicine.regulated_price
            line_total = unit_price * units
            pharmacy_subtotal += line_total
            lines.append(
                {
                    "medicine": medicine_id,
                    "medicine_name": str(medicine) if medicine else "",
                    "quantity": units,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "is_price_regulated": bool(medicine and medicine.is_price_regulated),
                }
            )
        subtotal += pharmacy_subtotal
        allocations.append(
            {
                "pharmacy": candidate.pharmacy.id,
                "pharmacy_name": candidate.pharmacy.name,
                "pharmacy_area": candidate.pharmacy.area,
                "distance_km": round(candidate.distance_km, 2),
                "rating": float(candidate.rating),
                "fulfillment_success_rate": float(candidate.pharmacy.fulfillment_success_rate),
                "preparation_minutes": candidate.pharmacy.order_preparation_minutes,
                "subtotal": pharmacy_subtotal,
                "lines": sorted(lines, key=lambda line: line["medicine_name"]),
            }
        )

    unfulfilled = [
        {
            "medicine": medicine_id,
            "medicine_name": str(medicines[medicine_id]) if medicine_id in medicines else "",
            "quantity_short": units,
        }
        for medicine_id, units in outstanding.items()
        if units > 0
    ]
    if unfulfilled:
        explanation.append("Some units could not be sourced nearby; they were recorded as unmet demand for pharmacies in that area.")

    allocations = sorted(allocations, key=lambda entry: entry["distance_km"])
    eta_low, eta_high = delivery_eta_minutes(allocations)
    return {
        "allocations": allocations,
        "unfulfilled": unfulfilled,
        "items_subtotal": subtotal,
        "pharmacy_count": len(allocations),
        "eta_minutes_low": eta_low,
        "eta_minutes_high": eta_high,
        "explanation": explanation,
    }


def fulfillment_options(*, items: list[dict], latitude: float, longitude: float, radius_km: float | None = None) -> list[dict]:
    """
    The same basket planned every way the platform can offer, for the shopper to choose from.

    Two rules keep this honest:

      * A strategy that cannot source the basket at all is dropped, not shown
        empty. `single` is the usual casualty - when no pharmacy stocks
        everything, "one pharmacy" is not an option that exists.
      * Two strategies that land on the identical allocation are collapsed to
        the first. Four cards naming the same pharmacies at four different
        prices would be four different claims about one plan.
      * An option that does not deliver what its label promises is dropped.
        `cheapest` is the one this catches: most of the catalog is MoPH-priced,
        identical at every counter by law, so splitting the basket buys nothing
        and costs a pickup. Offering that as "lowest cost" would be a worse plan
        under a better name.
    """
    delivery_fee = Decimal(str(settings.DELIVERY_BASE_FEE))
    options: list[dict] = []
    seen: set[tuple] = set()
    baseline: Decimal | None = None

    for strategy in STRATEGIES:
        plan = plan_basket(items=items, latitude=latitude, longitude=longitude, radius_km=radius_km, strategy=strategy)
        if not plan["allocations"]:
            continue
        if strategy is BEST:
            baseline = plan["items_subtotal"]
        elif strategy is CHEAPEST and baseline is not None and plan["items_subtotal"] >= baseline:
            continue
        fingerprint = tuple(
            sorted(
                (str(entry["pharmacy"]), line["medicine"], line["quantity"])
                for entry in plan["allocations"]
                for line in entry["lines"]
            )
        )
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        options.append(
            {
                **plan,
                "kind": strategy.key,
                "label": strategy.label,
                "tagline": strategy.tagline,
                "delivery_fee": delivery_fee,
                "total": plan["items_subtotal"] + delivery_fee,
            }
        )
    return options


def delivery_eta_minutes(allocations: list[dict]) -> tuple[int | None, int | None]:
    """
    How long this plan should take, door to door.

    Pharmacies pack in parallel, so the wait before collection is the slowest of
    them, not their total. Travel is then sequential: the driver visits each
    pickup and carries on to the shopper, so every extra pharmacy on a plan costs
    both its distance and a service stop. That is the same fact the stop penalty
    encodes in the cost model, surfaced here as time. Speed and per-stop service
    times are the routing planner's, from apps.common.geo, so the estimate a
    shopper is shown and the one dispatch works to cannot drift apart.
    """
    if not allocations:
        return None, None
    packing = max(float(entry["preparation_minutes"]) for entry in allocations)
    travel = travel_minutes(sum(float(entry["distance_km"]) for entry in allocations))
    service = PICKUP_SERVICE_MINUTES * len(allocations) + DROPOFF_SERVICE_MINUTES
    low = Decimal(str(packing + travel + service))
    return int(low), int(low * ETA_SPREAD)
