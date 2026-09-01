"""
Load a catalogue of real, market-brand dietary supplements sold in Lebanese
pharmacies.

Supplements are NOT in the MoPH National Drugs Database and the Ministry does
not set a price for them, so there is no authoritative source to sync from - the
catalogue has to be built by hand. Every row is created as
``category=SUPPLEMENT`` / ``price_regime=FREE`` with no ``regulated_price``:
each pharmacy prices its own shelf via ``InventoryBatch.selling_price``.

Idempotent: keyed on ``brand_name`` via ``update_or_create``, so re-running only
refreshes the descriptive fields and never duplicates a product. Safe to run
against the local sqlite dev DB and against production (the release image picks
this command up on the next deploy; it can also be run as a one-off ECS task).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.medicines.models import (
    DrugSchedule,
    MarketStatus,
    Medicine,
    MedicineAlias,
    PriceRegime,
    ProductCategory,
)

# (brand_name, generic_name, strength, form, manufacturer, [search aliases])
SUPPLEMENTS: list[tuple[str, str, str, str, str, list[str]]] = [
    # --- Multivitamins ---
    ("Centrum Adults", "Multivitamin and multimineral", "", "Tablet", "Haleon",
     ["centrum", "multivitamin", "multi vitamin"]),
    ("Centrum Silver 50+", "Multivitamin and multimineral", "", "Tablet", "Haleon",
     ["centrum silver"]),
    ("Centrum MultiGummies", "Multivitamin", "", "Gummy", "Haleon",
     ["centrum gummies"]),
    ("Supradyn Energy", "Multivitamin with coenzyme Q10", "", "Effervescent tablet", "Bayer",
     ["supradyn"]),
    ("Pharmaton Vitality", "Multivitamin with ginseng G115", "", "Capsule", "Sanofi",
     ["pharmaton"]),
    ("Bion3 Defense", "Multivitamin with probiotics", "", "Tablet", "Procter & Gamble",
     ["bion3", "bion 3"]),
    ("Wellman Original", "Multivitamin for men", "", "Tablet", "Vitabiotics",
     ["wellman", "well man"]),
    ("Wellwoman Original", "Multivitamin for women", "", "Capsule", "Vitabiotics",
     ["wellwoman", "well woman"]),
    ("Pregnacare Original", "Prenatal multivitamin with folic acid", "", "Tablet", "Vitabiotics",
     ["pregnacare", "prenatal", "pregnancy vitamins"]),
    # --- Vitamin B / C ---
    ("Berocca Performance", "Vitamin B complex with vitamin C", "", "Effervescent tablet", "Bayer",
     ["berocca", "b complex", "vitamin b"]),
    ("Redoxon Double Action", "Vitamin C with zinc", "1000 mg", "Effervescent tablet", "Bayer",
     ["redoxon", "vitamin c", "vitamine c"]),
    ("Solgar Vitamin C 1000 mg", "Ascorbic acid", "1000 mg", "Tablet", "Solgar",
     ["vitamin c", "vitamine c"]),
    ("Solgar Ester-C Plus 1000 mg", "Calcium ascorbate", "1000 mg", "Tablet", "Solgar",
     ["ester c"]),
    ("Now Foods Vitamin C-1000", "Ascorbic acid with rose hips", "1000 mg", "Tablet", "NOW Foods",
     ["vitamin c"]),
    ("Solgar B-Complex 100", "Vitamin B complex", "", "Vegetable capsule", "Solgar",
     ["b complex", "vitamin b", "b-complex"]),
    ("Solgar Vitamin B12 1000 mcg", "Cyanocobalamin", "1000 mcg", "Nugget", "Solgar",
     ["b12", "vitamin b12", "vitamine b12"]),
    ("Now Foods Vitamin B-12 1000 mcg", "Methylcobalamin", "1000 mcg", "Lozenge", "NOW Foods",
     ["b12", "vitamin b12"]),
    ("Solgar Biotin 1000 mcg", "Biotin", "1000 mcg", "Vegetable capsule", "Solgar",
     ["biotin", "vitamin b7"]),
    ("Solgar Folic Acid 400 mcg", "Folic acid", "400 mcg", "Tablet", "Solgar",
     ["folic acid", "folate", "vitamin b9"]),
    # --- Vitamin D ---
    ("Solgar Vitamin D3 1000 IU", "Cholecalciferol", "1000 IU (25 mcg)", "Softgel", "Solgar",
     ["vitamin d", "vitamin d3", "vitamine d"]),
    ("Solgar Vitamin D3 2200 IU", "Cholecalciferol", "2200 IU (55 mcg)", "Vegetable capsule", "Solgar",
     ["vitamin d3"]),
    ("Nature's Bounty Vitamin D3 2000 IU", "Cholecalciferol", "2000 IU (50 mcg)", "Softgel", "Nature's Bounty",
     ["vitamin d3"]),
    ("Nature Made Vitamin D3 1000 IU", "Cholecalciferol", "1000 IU (25 mcg)", "Softgel", "Nature Made",
     ["vitamin d3"]),
    # --- Omega-3 ---
    ("Solgar Omega-3 700 mg", "Fish oil (EPA/DHA)", "700 mg", "Softgel", "Solgar",
     ["omega 3", "omega3", "fish oil"]),
    ("Solgar Omega 3-6-9", "Fish, flaxseed and borage oil", "1300 mg", "Softgel", "Solgar",
     ["omega 369", "omega 3 6 9"]),
    ("Nature's Bounty Fish Oil 1200 mg", "Fish oil (omega-3)", "1200 mg", "Softgel", "Nature's Bounty",
     ["fish oil", "omega 3"]),
    ("Now Foods Omega-3 1000 mg", "Fish oil (EPA/DHA)", "1000 mg", "Softgel", "NOW Foods",
     ["omega 3", "fish oil"]),
    ("Seven Seas Cod Liver Oil", "Cod liver oil with omega-3", "", "Softgel", "Merck",
     ["cod liver oil", "omega 3"]),
    # --- Minerals ---
    ("Solgar Magnesium Citrate", "Magnesium citrate", "200 mg", "Tablet", "Solgar",
     ["magnesium"]),
    ("Now Foods Magnesium Citrate 200 mg", "Magnesium citrate", "200 mg", "Tablet", "NOW Foods",
     ["magnesium"]),
    ("Nature's Bounty Magnesium 500 mg", "Magnesium oxide", "500 mg", "Tablet", "Nature's Bounty",
     ["magnesium"]),
    ("Solgar Chelated Zinc", "Zinc bisglycinate", "22 mg", "Tablet", "Solgar",
     ["zinc"]),
    ("Now Foods Zinc Picolinate 50 mg", "Zinc picolinate", "50 mg", "Capsule", "NOW Foods",
     ["zinc"]),
    ("Solgar Gentle Iron", "Iron bisglycinate", "20 mg", "Vegetable capsule", "Solgar",
     ["iron", "iron supplement"]),
    ("Solgar Calcium Magnesium plus Vitamin D3", "Calcium, magnesium and vitamin D3", "", "Tablet", "Solgar",
     ["calcium", "cal mag"]),
    ("Nature's Bounty Calcium 600 + D3", "Calcium carbonate with vitamin D3", "600 mg", "Tablet", "Nature's Bounty",
     ["calcium"]),
    ("Osteocare Original", "Calcium, magnesium, zinc and vitamin D", "", "Tablet", "Vitabiotics",
     ["osteocare", "calcium"]),
    # --- Herbal / specialty ---
    ("Now Foods Ashwagandha 450 mg", "Ashwagandha root extract", "450 mg", "Vegetable capsule", "NOW Foods",
     ["ashwagandha"]),
    ("Now Foods CoQ10 100 mg", "Coenzyme Q10", "100 mg", "Softgel", "NOW Foods",
     ["coq10", "coenzyme q10", "ubiquinone"]),
    ("Solgar Turmeric Root Extract", "Curcumin (turmeric)", "", "Vegetable capsule", "Solgar",
     ["turmeric", "curcumin"]),
    ("Nature's Bounty Hair Skin & Nails", "Biotin with collagen", "", "Softgel", "Nature's Bounty",
     ["collagen", "biotin", "hair skin nails"]),
    ("Solgar Collagen Hyaluronic Acid Complex", "Hydrolysed collagen with hyaluronic acid", "120 mg", "Tablet", "Solgar",
     ["collagen"]),
    ("Solgar Glucosamine Chondroitin MSM", "Glucosamine, chondroitin and MSM", "", "Tablet", "Solgar",
     ["glucosamine", "chondroitin"]),
    ("Nature's Bounty Probiotic 10", "Multi-strain probiotic (10 strains)", "20 billion CFU", "Capsule", "Nature's Bounty",
     ["probiotic", "probiotics"]),
    ("Now Foods Melatonin 3 mg", "Melatonin", "3 mg", "Tablet", "NOW Foods",
     ["melatonin"]),
    # --- Sports nutrition ---
    ("Optimum Nutrition Gold Standard 100% Whey", "Whey protein isolate and concentrate", "", "Powder", "Optimum Nutrition",
     ["whey", "whey protein", "protein"]),
    ("Optimum Nutrition Micronized Creatine", "Creatine monohydrate", "", "Powder", "Optimum Nutrition",
     ["creatine", "creatine monohydrate"]),
]


class Command(BaseCommand):
    help = "Create/refresh the free-priced dietary supplement catalogue (real market brands)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Database alias to write to (default: 'default').",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        db = options["database"]
        created = updated = aliases_added = 0

        for brand, generic, strength, form, manufacturer, aliases in SUPPLEMENTS:
            medicine, was_created = Medicine.objects.using(db).update_or_create(
                brand_name=brand,
                defaults={
                    "generic_name": generic,
                    "strength": strength,
                    "form": form,
                    "manufacturer": manufacturer,
                    "category": ProductCategory.SUPPLEMENT,
                    "price_regime": PriceRegime.FREE,
                    "regulated_price": None,
                    "is_active": True,
                    "market_status": MarketStatus.MARKETED,
                    "requires_prescription": False,
                    "drug_schedule": DrugSchedule.NONE,
                },
            )
            created += was_created
            updated += not was_created

            for alias in aliases:
                _, alias_created = MedicineAlias.objects.using(db).get_or_create(
                    medicine=medicine,
                    alias=alias,
                    defaults={"alias_type": MedicineAlias.AliasType.OTHER},
                )
                aliases_added += alias_created

        self.stdout.write(
            self.style.SUCCESS(
                f"Supplements: {created} created, {updated} refreshed, "
                f"{aliases_added} aliases added ({len(SUPPLEMENTS)} in catalogue, all FREE-priced)."
            )
        )
