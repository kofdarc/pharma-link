from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.medicines.models import Medicine, PriceRegime
from apps.medicines.services.search import normalize_name


def identity(medicine: Medicine) -> tuple[str, str]:
    return normalize_name(medicine.brand_name), normalize_name(medicine.strength)


def build_reconciliation_plan(legacy: list[Medicine], priced: list[Medicine]):
    legacy_by_identity = defaultdict(list)
    priced_by_identity = defaultdict(list)
    for medicine in legacy:
        legacy_by_identity[identity(medicine)].append(medicine)
    for medicine in priced:
        priced_by_identity[identity(medicine)].append(medicine)

    safe_pairs: list[tuple[Medicine, Medicine]] = []
    ambiguous_legacy = 0
    unmatched_legacy = 0
    for key, legacy_matches in legacy_by_identity.items():
        priced_matches = priced_by_identity.get(key, [])
        if len(legacy_matches) == 1 and len(priced_matches) == 1:
            safe_pairs.append((legacy_matches[0], priced_matches[0]))
        elif priced_matches:
            ambiguous_legacy += len(legacy_matches)
        else:
            unmatched_legacy += len(legacy_matches)
    return safe_pairs, ambiguous_legacy, unmatched_legacy


def enrich_unique_matches(safe_pairs: list[tuple[Medicine, Medicine]], *, updated_at):
    enriched: list[Medicine] = []
    for source, target in safe_pairs:
        changed = False
        if source.classification and not target.classification:
            target.classification = source.classification
            changed = True
        if source.generic_name and not target.generic_name:
            target.generic_name = source.generic_name
            changed = True
        if changed:
            target.updated_at = updated_at
            enriched.append(target)
    return enriched


class Command(BaseCommand):
    help = "Reconcile legacy ATC catalogue rows with priced medicines and retire unpriced active records."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write changes; without this flag the command is a dry run.")

    def handle(self, *args, **options):
        with transaction.atomic():
            legacy = list(
                Medicine.objects.select_for_update()
                .filter(
                    is_active=True,
                    price_regime=PriceRegime.REGULATED,
                    regulated_price__isnull=True,
                )
                .order_by("id")
            )
            priced = list(
                Medicine.objects.select_for_update()
                .filter(is_active=True, regulated_price__isnull=False)
                .order_by("id")
            )

            safe_pairs, ambiguous_legacy, unmatched_legacy = build_reconciliation_plan(legacy, priced)
            now = timezone.now()
            enriched = enrich_unique_matches(safe_pairs, updated_at=now)

            self.stdout.write(f"Active regulated rows without prices: {len(legacy)}")
            self.stdout.write(f"Unique priced matches: {len(safe_pairs)}")
            self.stdout.write(f"Priced medicines enriched with ATC/generic metadata: {len(enriched)}")
            self.stdout.write(f"Ambiguous legacy rows: {ambiguous_legacy}")
            self.stdout.write(f"Unmatched legacy rows: {unmatched_legacy}")
            self.stdout.write(f"Legacy rows to retire: {len(legacy)}")

            if not options["apply"]:
                self.stdout.write("Dry run only. Re-run with --apply to update the database.")
                transaction.set_rollback(True)
                return

            if enriched:
                Medicine.objects.bulk_update(enriched, ["classification", "generic_name", "updated_at"], batch_size=500)
            for medicine in legacy:
                medicine.is_active = False
                medicine.updated_at = now
            if legacy:
                Medicine.objects.bulk_update(legacy, ["is_active", "updated_at"], batch_size=500)

            self.stdout.write(self.style.SUCCESS(f"Enriched {len(enriched)} medicines and retired {len(legacy)} legacy rows."))
