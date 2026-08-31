"""
Give the demo pharmacies a trading history, so the Analytics screens and the
assistant have something real to describe.

`seed_poc` builds the catalog, stock and a handful of platform orders, but it
records almost no counter sales - which leaves the Analytics tabs (revenue
sparkline, ABC classification, reorder plan, Smart Insights) and the "how did we
trade" / "any insights for us" assistant answers empty or trivial.

This command fills that gap for the pharmacies a demo actually signs into. For
each target pharmacy it:

  - tops up stock with backdated wholesaler batches so the window can be sold
    through without running dry, then deliberately shapes a few SKUs into the
    states the insights look for (near expiry, at reorder point, never sold);
  - writes ~`--days` of counter sales through the real `create_sale` service -
    FEFO stock allocation, invoice numbering, ledger entries and all - then
    backdates each sale and its stock movements across the window;
  - draws baskets from a long-tailed popularity curve, so ABC/Pareto has clear
    A, B and C classes rather than a flat line;
  - records nearby unmet-demand signals, so the Demand tab and the
    "opportunity" insights have something to show.

Everything it writes is tagged `[seed:demo-sales]` in `Sale.notes`, so a re-run
with `--wipe` can remove exactly what it added and nothing else. Idempotent
without `--wipe` too: it refuses a pharmacy that already has seeded sales.

Counter sales are OTC medicines and supplements plus a small set of common
chronic medicines (sold against a backdated prescription record, the same way
the counter would). Antibiotics and the other acute prescription-only lines are
left out of the counter history on purpose - they read as slow movers, which is
what they are.

    python manage.py seed_demo_sales                 # demo login pharmacies, 90 days
    python manage.py seed_demo_sales --days 120
    python manage.py seed_demo_sales --all-pharmacies
    python manage.py seed_demo_sales --pharmacy "Cedar Care" --wipe
"""

from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.customers.models import Client, ClientLedgerEntry
from apps.inventory.models import InventoryBatch, StockMovement
from apps.inventory.services.stock import adjust_stock, create_inventory_batch
from apps.medicines.models import MarketStatus, Medicine
from apps.orders.models import UnmetDemandSignal
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord
from apps.sales.models import Sale
from apps.sales.services.create_sale import create_sale

SEED_TAG = "[seed:demo-sales]"

# Chronic prescription-only lines that a pharmacy dispenses week in, week out.
# These are sold at the counter in the demo history (against a backdated
# prescription record); every other Rx line is left as an occasional mover.
CHRONIC_RX_GENERICS = (
    "Metformin",
    "Atorvastatin",
    "Rosuvastatin",
    "Amlodipine",
    "Bisoprolol",
    "Losartan",
    "Valsartan",
    "Ramipril",
)

# Basket-size distribution (items per sale) and per-line quantity distribution.
BASKET_SIZES = ((1, 0.46), (2, 0.34), (3, 0.15), (4, 0.05))
LINE_QUANTITIES = ((1, 0.70), (2, 0.22), (3, 0.08))

# Payment mix. ON_ACCOUNT needs a client on the sale; it falls back to CASH when
# the pharmacy has no clients.
PAYMENT_MIX = (
    (Sale.PaymentMethod.CASH, 0.60),
    (Sale.PaymentMethod.CARD, 0.28),
    (Sale.PaymentMethod.ON_ACCOUNT, 0.12),
)
CHANNEL_MIX = (
    (Sale.Channel.COUNTER, 0.86),
    (Sale.Channel.PLATFORM_ORDER, 0.11),
    (Sale.Channel.INTEGRATION, 0.03),
)

# Weekday -> footfall multiplier (Mon=0 .. Sun=6). Saturday busy, Sunday quiet.
WEEKDAY_FACTOR = {0: 1.0, 1: 1.0, 2: 0.98, 3: 1.02, 4: 1.12, 5: 1.28, 6: 0.5}

BUSINESS_HOURS = (9, 19)
DISCOUNT_PROBABILITY = 0.12
CANCEL_PROBABILITY = 0.03
CLIENT_ATTACH_PROBABILITY = 0.35

DEMO_CLIENT_NAMES = (
    ("Georges Haddad", "+961-3-201-455"),
    ("Maya Chidiac", "+961-3-778-112"),
    ("Hassan Fakih", "+961-3-664-901"),
    ("Rana Bitar", "+961-3-540-338"),
    ("Nabil Aoun", "+961-3-119-706"),
)


class Command(BaseCommand):
    help = "Seed a counter-sales history for the demo pharmacies so Analytics and the assistant have real data."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90, help="Days of history to generate (default: 90).")
        parser.add_argument(
            "--pharmacy",
            action="append",
            default=[],
            metavar="NAME",
            help="Restrict to pharmacies whose name contains this (repeatable). Default: pharmacies with an owner/staff login.",
        )
        parser.add_argument("--all-pharmacies", action="store_true", help="Seed every pharmacy, not just the demo login ones.")
        parser.add_argument("--wipe", action="store_true", help="Delete this command's own previously seeded sales first.")
        parser.add_argument("--daily-base", type=int, default=13, help="Baseline transactions per day before seasonality (default: 13).")
        parser.add_argument("--seed", type=int, default=1234, help="RNG seed for a reproducible history (default: 1234).")

    def handle(self, *args, **options):
        days = max(14, options["days"])
        pharmacies = self._targets(options["pharmacy"], options["all_pharmacies"])
        if not pharmacies:
            raise CommandError("No matching pharmacies. Run `seed_poc` first, or widen --pharmacy / use --all-pharmacies.")

        self.stdout.write(f"Target pharmacies: {', '.join(p.name for p in pharmacies)}")
        for index, pharmacy in enumerate(pharmacies):
            self._seed_pharmacy(
                pharmacy,
                days=days,
                daily_base=options["daily_base"],
                wipe=options["wipe"],
                rng=random.Random(options["seed"] + index * 101),
            )
        self.stdout.write(self.style.SUCCESS("\nDemo sales history seeded."))

    # ------------------------------------------------------------------ targets
    def _targets(self, name_filters, all_pharmacies) -> list[Pharmacy]:
        qs = Pharmacy.objects.all().order_by("name")
        if name_filters:
            from django.db.models import Q

            query = Q()
            for fragment in name_filters:
                query |= Q(name__icontains=fragment)
            return list(qs.filter(query))
        if all_pharmacies:
            return list(qs)
        with_login = qs.filter(users__role__in=[UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF]).distinct()
        return list(with_login)

    def _staff_user(self, pharmacy):
        user = (
            pharmacy.users.filter(role=UserRole.PHARMACY_STAFF).first()
            or pharmacy.users.filter(role=UserRole.PHARMACY_OWNER).first()
        )
        if user is None:
            raise CommandError(f"{pharmacy.name} has no owner or staff user - run `seed_poc` first.")
        return user

    # --------------------------------------------------------------- per pharmacy
    @transaction.atomic
    def _seed_pharmacy(self, pharmacy, *, days, daily_base, wipe, rng):
        self.stdout.write(f"\n{pharmacy.name} ({pharmacy.area})")
        staff = self._staff_user(pharmacy)

        if wipe:
            self._wipe(pharmacy)
        elif pharmacy.sales.filter(notes__contains=SEED_TAG).exists():
            self.stdout.write(self.style.WARNING("  already has seeded sales - skipping (use --wipe to redo)."))
            return

        clients = self._ensure_clients(pharmacy, staff)

        sellable = self._sellable_medicines(pharmacy)
        if len(sellable) < 4:
            self.stdout.write(self.style.WARNING("  not enough stocked OTC/supplement lines to build a history - skipping."))
            return

        # Long-tailed popularity: a few clear class-A movers, a long C tail.
        rng.shuffle(sellable)
        weights = self._popularity_weights(len(sellable), rng)
        popularity = dict(zip((m.id for m in sellable), weights))

        # Rough expected demand per medicine over the window, used to size the
        # backdated wholesaler batches so nothing runs dry mid-window.
        avg_tx = daily_base * 0.97 * 1.08  # seasonality x trend, averaged
        expected_line_units = avg_tx * days * 1.8 * 1.38  # mean basket size x mean qty
        weight_total = sum(weights)
        expected_units = {
            mid: expected_line_units * (popularity[mid] / weight_total) for mid in popularity
        }

        never_sold = self._open_stock(pharmacy, staff, sellable, expected_units, days, rng)
        for mid in never_sold:
            popularity.pop(mid, None)
        sellable = [m for m in sellable if m.id in popularity]
        rx_ids = {m.id for m in sellable if m.requires_prescription}

        pool = [m for m in sellable for _ in range(max(1, int(popularity[m.id] * 100)))]

        created = 0
        revenue = Decimal("0")
        start = timezone.localdate() - timedelta(days=days - 1)
        for offset in range(days):
            day = start + timedelta(days=offset)
            trend = 1.0 + 0.16 * (offset / max(1, days - 1))
            count = daily_base * WEEKDAY_FACTOR[day.weekday()] * trend * rng.uniform(0.78, 1.22)
            for seq in range(1, int(round(count)) + 1):
                sale = self._one_sale(
                    pharmacy=pharmacy,
                    staff=staff,
                    day=day,
                    seq=seq,
                    pool=pool,
                    rx_ids=rx_ids,
                    clients=clients,
                    rng=rng,
                )
                if sale is None:
                    continue
                created += 1
                revenue += sale.total

        self._final_shaping(pharmacy, staff, sellable, expected_units, days, rng)
        self._unmet_demand(pharmacy, sellable, rng)

        movers = (
            Sale.objects.filter(pharmacy=pharmacy, notes__contains=SEED_TAG)
            .order_by("-sale_datetime")
            .values_list("sale_datetime", flat=True)
        )
        span = f"{movers.last():%Y-%m-%d} to {movers.first():%Y-%m-%d}" if created else "none"
        self.stdout.write(f"  sales: {created}  revenue: {revenue.quantize(Decimal('0.01'))}  span: {span}")

    # ------------------------------------------------------------------ one sale
    def _one_sale(self, *, pharmacy, staff, day, seq, pool, rx_ids, clients, rng):
        basket_size = _pick(BASKET_SIZES, rng)
        medicines: list[Medicine] = []
        seen: set = set()
        for _ in range(basket_size * 3):
            if len(medicines) >= basket_size:
                break
            candidate = rng.choice(pool)
            if candidate.id in seen:
                continue
            seen.add(candidate.id)
            medicines.append(candidate)
        if not medicines:
            return None

        items = [{"medicine": str(m.id), "quantity": _pick(LINE_QUANTITIES, rng)} for m in medicines]
        if rng.random() < DISCOUNT_PROBABILITY:
            items[0]["discount"] = str(Decimal(rng.choice(["0.50", "1.00", "1.50", "2.00", "3.00"])))

        # Keep opening stock lean (good turnover / GMROI) by restocking just in
        # time: when a line would outrun what's on the shelf, book a backdated
        # wholesaler delivery for that day. The result is a realistic sawtooth
        # inventory curve rather than one big pile that slowly drains.
        for medicine, line in zip(medicines, items):
            if _on_hand(pharmacy, medicine) < line["quantity"] + 2:
                selling = medicine.regulated_price if medicine.is_price_regulated else _free_price(pharmacy, medicine, rng)
                self._batch(
                    pharmacy, staff, medicine, rng.randint(24, 60), selling,
                    day - timedelta(days=1), rng.choice([150, 240, 330, 420]),
                )

        channel = _pick(CHANNEL_MIX, rng)
        payment = _pick(PAYMENT_MIX, rng)
        client = None
        if clients and (payment == Sale.PaymentMethod.ON_ACCOUNT or rng.random() < CLIENT_ATTACH_PROBABILITY):
            client = rng.choice(clients)
        if payment == Sale.PaymentMethod.ON_ACCOUNT and client is None:
            payment = Sale.PaymentMethod.CASH

        prescription_record_id = None
        if any(m.id in rx_ids for m in medicines):
            record = PrescriptionRecord.objects.create(
                pharmacy=pharmacy,
                created_by=staff,
                status=PrescriptionRecord.UploadStatus.ACCEPTED,
                patient_name=client.full_name if client else "Walk-in patient",
                doctor_name=rng.choice(["Dr. R. Khalil", "Dr. S. Aoun", "Dr. L. Nassar"]),
                prescription_date=day,
                valid_until=timezone.localdate() + timedelta(days=60),
                notes=SEED_TAG,
            )
            prescription_record_id = record.id

        when = timezone.make_aware(
            datetime.combine(day, time(hour=rng.randint(*BUSINESS_HOURS), minute=rng.randint(0, 59), second=rng.randint(0, 59)))
        )

        try:
            sale = create_sale(
                user=staff,
                pharmacy=pharmacy,
                items=items,
                payment_method=payment,
                channel=channel,
                client=client,
                prescription_record_id=prescription_record_id,
                notes=SEED_TAG,
            )
        except ValueError:
            # A line outran its stock despite the top-up (a run of large baskets
            # landing on one SKU). Skip this basket rather than abort the seed.
            if prescription_record_id:
                PrescriptionRecord.objects.filter(id=prescription_record_id, sale__isnull=True).delete()
            return None

        cancelled = rng.random() < CANCEL_PROBABILITY
        fields = {
            "sale_datetime": when,
            "created_at": when,
            "status": Sale.Status.CANCELLED if cancelled else Sale.Status.COMPLETED,
        }
        # `create_sale` numbers invoices `MS-<today>-NNNNN`. For a past day, restamp
        # with that day's date so the invoice list reads right; leave today's sales
        # on the live sequence so the two numbering schemes never collide.
        if day < timezone.localdate():
            fields["invoice_number"] = f"MS-{day:%Y%m%d}-{seq:05d}"
        Sale.objects.filter(pk=sale.pk).update(**fields)
        StockMovement.objects.filter(sale=sale).update(created_at=when)
        ClientLedgerEntry.objects.filter(sale=sale).update(created_at=when)
        sale.sale_datetime = when
        sale.status = Sale.Status.CANCELLED if cancelled else Sale.Status.COMPLETED
        return sale

    # --------------------------------------------------------------- stock setup
    def _sellable_medicines(self, pharmacy) -> list[Medicine]:
        """Stocked lines a counter can ring up without an acute prescription."""
        stocked = (
            InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False)
            .values_list("medicine_id", flat=True)
            .distinct()
        )
        medicines = Medicine.objects.filter(id__in=list(stocked), is_active=True)
        out = []
        for medicine in medicines:
            if not medicine.is_marketed:
                continue
            if medicine.requires_prescription and medicine.generic_name.split()[0] not in CHRONIC_RX_GENERICS:
                continue
            out.append(medicine)
        return out

    def _popularity_weights(self, n, rng) -> list[float]:
        # Zipf-ish: weight ~ 1 / rank^1.1, with noise, normalised so a handful
        # carry most of the volume.
        weights = [(1.0 / (rank ** 1.1)) * rng.uniform(0.7, 1.3) for rank in range(1, n + 1)]
        total = sum(weights)
        return [w / total for w in weights]

    def _open_stock(self, pharmacy, staff, sellable, expected_units, days, rng) -> set:
        """
        Give each line a lean opening position - roughly two weeks of cover -
        dated before the window. The daily loop tops it back up just in time, so
        inventory stays light relative to sales (healthy turnover) instead of
        starting as one big pile. Returns the medicine ids to leave unsold.
        """
        ordered = sorted(sellable, key=lambda m: expected_units.get(m.id, 0), reverse=True)
        never_sold = {m.id for m in ordered[-2:]} if len(ordered) > 8 else set()

        delivered = timezone.localdate() - timedelta(days=days + 8)
        for medicine in sellable:
            if medicine.id in never_sold:
                continue
            two_weeks = max(10, int(math.ceil(expected_units.get(medicine.id, 0) * 14 / days)))
            on_hand = _on_hand(pharmacy, medicine)
            if on_hand >= two_weeks:
                continue
            selling = medicine.regulated_price if medicine.is_price_regulated else _free_price(pharmacy, medicine, rng)
            self._batch(
                pharmacy, staff, medicine, two_weeks - on_hand, selling, delivered, rng.choice([180, 270, 360, 480])
            )

        if never_sold:
            names = ", ".join(m.brand_name for m in ordered[-2:])
            self.stdout.write(f"  left unsold (dead stock): {names}")
        return never_sold

    def _final_shaping(self, pharmacy, staff, sellable, expected_units, days, rng) -> None:
        """
        After the window is sold, push a handful of SKUs into the exact states
        the Smart Insights rules look for, so the Insights tab and the digest
        have concrete findings: a delivery that dates soon, a few lines down at
        their reorder point, and one batch already expired.
        """
        ordered = sorted(sellable, key=lambda m: expected_units.get(m.id, 0), reverse=True)
        mid = [m for m in ordered if expected_units.get(m.id, 0) > 0][2:-2] or ordered[:4]
        rng.shuffle(mid)

        near_expiry = mid[:2]
        reorder_now = mid[2:5]
        expired_one = mid[5] if len(mid) > 5 else (near_expiry[0] if near_expiry else None)

        for medicine in near_expiry:
            selling = medicine.regulated_price if medicine.is_price_regulated else _free_price(pharmacy, medicine, rng)
            self._batch(
                pharmacy, staff, medicine, rng.randint(18, 34), selling,
                timezone.localdate() - timedelta(days=rng.randint(6, 12)), rng.randint(16, 27),
            )
        if near_expiry:
            self.stdout.write(f"  short-dated delivery: {', '.join(m.brand_name for m in near_expiry)}")

        for medicine in reorder_now:
            on_hand = _on_hand(pharmacy, medicine)
            keep = rng.randint(2, 5)
            batch = (
                InventoryBatch.objects.filter(pharmacy=pharmacy, medicine=medicine, is_archived=False, current_quantity__gt=0)
                .order_by("expiry_date")
                .first()
            )
            if batch and on_hand > keep:
                adjust_stock(
                    batch_id=batch.id,
                    user=staff,
                    quantity_delta=-min(batch.current_quantity, on_hand - keep),
                    reason="Seed: demo stock shaping",
                    movement_type=StockMovement.MovementType.CORRECTION,
                )
        if reorder_now:
            self.stdout.write(f"  down to reorder point: {', '.join(m.brand_name for m in reorder_now)}")

        if expired_one is not None:
            selling = expired_one.regulated_price if expired_one.is_price_regulated else _free_price(pharmacy, expired_one, rng)
            self._batch(
                pharmacy, staff, expired_one, rng.randint(3, 9), selling,
                timezone.localdate() - timedelta(days=rng.randint(120, 200)), -rng.randint(2, 20),
            )

    def _batch(self, pharmacy, staff, medicine, quantity, selling, delivered, expiry_days):
        batch = create_inventory_batch(
            user=staff,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "batch_number": f"WSL-{delivered:%y%m}-{random.randint(100, 999)}",
                "initial_quantity": int(quantity),
                "expiry_date": timezone.localdate() + timedelta(days=expiry_days),
                "supplier_name": "Beirut Medical Supply",
                "purchase_cost": (Decimal(str(selling)) * Decimal("0.66")).quantize(Decimal("0.01")),
                "selling_price": Decimal(str(selling)),
                "low_stock_threshold": 3,
            },
            movement_type=StockMovement.MovementType.IMPORT,
        )
        when = timezone.make_aware(datetime.combine(delivered, time(hour=8, minute=30)))
        StockMovement.objects.filter(inventory_batch=batch).update(created_at=when)
        InventoryBatch.objects.filter(pk=batch.pk).update(created_at=when)
        return batch

    # ------------------------------------------------------------------- clients
    def _ensure_clients(self, pharmacy, staff) -> list[Client]:
        clients = list(pharmacy.clients.filter(is_active=True))
        for full_name, phone in DEMO_CLIENT_NAMES:
            if len(clients) >= 4:
                break
            client, made = Client.objects.get_or_create(
                pharmacy=pharmacy,
                phone=phone,
                defaults={
                    "full_name": full_name,
                    "email": f"{full_name.split()[0].lower()}@example.test",
                    "area": pharmacy.area,
                    "address": f"{pharmacy.area}, Beirut",
                    "created_by": staff,
                },
            )
            if made:
                clients.append(client)
        return clients

    # -------------------------------------------------------------- unmet demand
    def _unmet_demand(self, pharmacy, sellable, rng):
        if UnmetDemandSignal.objects.filter(area__iexact=pharmacy.area).exists():
            return
        stocked_ids = {m.id for m in sellable}
        wanted = list(
            Medicine.objects.filter(market_status=MarketStatus.MARKETED, is_active=True)
            .exclude(id__in=stocked_ids)
            .order_by("?")[:6]
        )
        wanted += list(Medicine.objects.filter(id__in=list(stocked_ids)).order_by("?")[:2])
        made = 0
        for medicine in wanted:
            for _ in range(rng.randint(2, 6)):
                created = timezone.now() - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
                signal = UnmetDemandSignal.objects.create(
                    medicine=medicine,
                    query_text=medicine.brand_name,
                    area=pharmacy.area,
                    quantity_requested=rng.randint(1, 3),
                    source=rng.choice([UnmetDemandSignal.Source.SEARCH, UnmetDemandSignal.Source.BASKET]),
                )
                UnmetDemandSignal.objects.filter(pk=signal.pk).update(created_at=created)
                made += 1
        self.stdout.write(f"  unmet-demand signals in {pharmacy.area}: {made}")

    # ---------------------------------------------------------------------- wipe
    def _wipe(self, pharmacy):
        """
        Remove exactly what this command adds: the tagged sales and everything
        hanging off them, the backdated `WSL-` wholesaler batches, and the
        shaping adjustments. It does not restore the pre-seed quantities of
        batches the seeded sales drew down - a re-seed tops those back up, and a
        `--wipe` is only ever a prelude to that.
        """
        sales = Sale.objects.filter(pharmacy=pharmacy, notes__contains=SEED_TAG)
        wsl = InventoryBatch.objects.filter(pharmacy=pharmacy, batch_number__startswith="WSL-")
        n_sales = sales.count()
        n_batches = wsl.count()

        ClientLedgerEntry.objects.filter(sale__in=sales).delete()
        StockMovement.objects.filter(sale__in=sales).delete()
        PrescriptionRecord.objects.filter(pharmacy=pharmacy, notes__contains=SEED_TAG).update(sale=None)
        sales.delete()
        PrescriptionRecord.objects.filter(pharmacy=pharmacy, notes__contains=SEED_TAG).delete()

        StockMovement.objects.filter(inventory_batch__in=wsl).delete()
        StockMovement.objects.filter(pharmacy=pharmacy, reason="Seed: demo stock shaping").delete()
        wsl.delete()
        # Unmet-demand signals are left in place - they carry no seed marker and
        # `_unmet_demand` already no-ops when the area has any.
        self.stdout.write(f"  wiped {n_sales} seeded sales and {n_batches} backdated batches")


def _pick(distribution, rng):
    roll = rng.random()
    cumulative = 0.0
    for value, probability in distribution:
        cumulative += probability
        if roll <= cumulative:
            return value
    return distribution[-1][0]


def _on_hand(pharmacy, medicine) -> int:
    from django.db.models import Sum

    return (
        InventoryBatch.objects.filter(pharmacy=pharmacy, medicine=medicine, is_archived=False).aggregate(
            units=Sum("current_quantity")
        )["units"]
        or 0
    )


def _free_price(pharmacy, medicine, rng) -> Decimal:
    existing = (
        InventoryBatch.objects.filter(pharmacy=pharmacy, medicine=medicine, is_archived=False, selling_price__gt=0)
        .values_list("selling_price", flat=True)
        .first()
    )
    if existing:
        return Decimal(existing)
    return (Decimal("12.00") + Decimal(rng.randint(-250, 350)) / 100).quantize(Decimal("0.01"))
