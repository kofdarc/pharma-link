"""
Seeds a demo scenario that actually exercises the hard parts of the POC:

  - 5 Beirut pharmacies with real-ish coordinates, ratings and reliability
  - 20 REAL medicines, resolved from the synced MoPH catalog (see SEED_INGREDIENTS)
  - 20 free-priced SUPPLEMENTS and parapharmacy products (see SEED_SUPPLEMENTS),
    which are NOT in any national registry - this command is their only source;
    each pharmacy stocks one of every supplement at its own free-set price
  - stock deliberately fragmented so some baskets CANNOT come from one pharmacy
  - 3 doctors from the "Order of Physicians" roster, one already activated
  - shopper orders in every lifecycle state, several multi-pharmacy, which is
    what makes pickup consolidation visible in the dispatch plan
  - saved payment methods, notification preferences, refill schedules and
    e-prescriptions attached to those shoppers, so the patient screens have
    something real to read
  - 3 drivers online, so the router has real choices to make

Nothing here invents a MEDICINE. The medicine catalog is whatever
`sync_moph_catalog` already loaded, and this command only picks those products
out of it - so a seeded demo and the live catalog can never disagree about what
a medicine is or costs. Run `manage.py sync_moph_catalog` first; this command
refuses to guess for medicines. Supplements are the deliberate exception: there
is no MoPH registry for them, so the demo (like any pharmacy) builds that part
of the catalog from its own shelf reality, free-priced.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import NotificationPreferences, UserRole
from apps.customers.models import Client
from apps.delivery.models import Driver
from apps.eprescriptions.models import Doctor, Prescription
from apps.eprescriptions.services.issue import issue_prescription
from apps.eprescriptions.services.qr import prescription_url
from apps.integrations.models import SkuMapping
from apps.integrations.services.keys import create_integration_key
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import (
    DrugSchedule,
    MarketStatus,
    Medicine,
    MedicineAlias,
    PriceRegime,
    ProductCategory,
)
from apps.orders.models import DeliveryAddress, Order, OrderFulfillment, RecurringOrder
from apps.orders.services.lifecycle import (
    accept_fulfillment,
    cancel_order,
    hand_over,
    mark_delivered,
    mark_ready,
    submit_review,
)
from apps.orders.services.placement import place_order
from apps.payments.models import SavedPaymentMethod
from apps.pharmacies.models import Pharmacy

PASSWORD = "Password123!"

PHARMACIES = [
    # name, area, lat, lng, rating, count, reliability
    ("Cedar Care Pharmacy", "Hamra", 33.8975, 35.4790, "4.60", 52, "97.50"),
    ("Bliss Street Pharmacy", "Hamra", 33.8963, 35.4823, "4.10", 31, "92.00"),
    ("Achrafieh Health Pharmacy", "Achrafieh", 33.8886, 35.5175, "4.80", 88, "98.80"),
    ("Gemmayze Corner Pharmacy", "Gemmayze", 33.8959, 35.5142, "3.90", 17, "88.00"),
    ("Verdun Family Pharmacy", "Verdun", 33.8790, 35.4835, "4.35", 44, "95.20"),
]

# The active ingredients the demo catalog is built from: twenty of the most-used
# medicines worldwide, spanning the therapeutic areas a Beirut pharmacy actually
# dispenses - cardiovascular, diabetes, respiratory, gastro, antibiotics,
# analgesics and antihistamines.
#
# These are INGREDIENTS, not products. Each one is resolved at seed time against
# whatever MoPH-registered brand the synced catalog holds for it, so the demo is
# always populated with real Lebanese products at their real published prices.
#
# `rx` marks the ones a pharmacist should not hand over without a prescription.
# The MoPH import carries no prescription flag (see Medicine.drug_schedule), so
# this classification is the platform admin's, exactly as it would be in
# production - and the demo needs it for the e-prescription flows to mean anything.
SEED_INGREDIENTS = [
    # ingredient prefix, rx
    ("Paracetamol", False),
    ("Ibuprofen", False),
    ("Diclofenac", False),
    ("Cetirizine", False),
    ("Loratadine", False),
    ("Omeprazole", False),
    ("Esomeprazole", False),
    ("Ondansetron", False),
    ("Metformin", True),
    ("Atorvastatin", True),
    ("Rosuvastatin", True),
    ("Amlodipine", True),
    ("Bisoprolol", True),
    ("Losartan", True),
    ("Valsartan", True),
    ("Ramipril", True),
    ("Clopidogrel", True),
    ("Salbutamol", True),
    ("Montelukast", True),
    ("Amoxicillin", True),
    ("Azithromycin", True),
    ("Ciprofloxacin", True),
    ("Fluconazole", True),
    ("Dexamethasone", True),
]

# How many of the above must resolve for the demo to be worth seeding. Below
# this the catalog has not been synced and every downstream step - stock,
# baskets, orders, prescriptions - would be built on nothing.
MINIMUM_SEED_MEDICINES = 20

# Oral solids first. A supppository or an elixir is a real MoPH product, but a
# demo basket reads better as tablets and capsules, and the sourcing planner does
# not care which form it is moving.
PREFERRED_FORMS = ["Tablet", "Capsule", "Caplet"]

# Guards the known bad rows: a handful of MoPH entries carry prices that overflow
# the catalogue endpoints. Anything outside this range is a data problem, not a
# product, and must never reach a seeded basket.
SANE_PRICE = (Decimal("0.25"), Decimal("500"))

# Supplements and parapharmacy are NOT in the MoPH catalogue - Lebanon has no
# national registry for them, so this command is the only source of these rows.
# Unlike the medicines above they are free-priced: each pharmacy sets its own
# selling price, so the catalog row carries no regulated_price at all. Each
# entry is (brand_name, generic_name, form, aliases) - the seed creates the
# Medicine as category=SUPPLEMENT / PARAPHARMACY with price_regime=FREE, and
# every seeded pharmacy stocks one of each. The aliases make them match in
# search and `best_catalog_match` (imports, OCR, POS sync).
SEED_SUPPLEMENTS = [
    # brand, generic, form, aliases (first is the canonical name)
    ("PharmaLink Creatine Monohydrate", "Creatine", "Powder", ["creatine", "creatine monohydrate"]),
    ("PharmaLink Creatine Capsules", "Creatine", "Capsule", ["creatine capsules"]),
    ("PharmaLink Whey Protein", "Whey Protein", "Powder", ["whey", "whey protein"]),
    ("PharmaLink Vitamin D3", "Vitamin D3", "Capsule", ["vitamin d", "vitamin d3", "vitamine d"]),
    ("PharmaLink Vitamin C", "Vitamin C", "Effervescent", ["vitamin c", "vitamine c"]),
    ("PharmaLink Omega-3", "Fish Oil Omega-3", "Capsule", ["omega 3", "omega3", "fish oil"]),
    ("PharmaLink Magnesium", "Magnesium", "Tablet", ["magnesium"]),
    ("PharmaLink Zinc", "Zinc", "Tablet", ["zinc"]),
    ("PharmaLink Multivitamin", "Multivitamin", "Tablet", ["multivitamin", "multi vitamin"]),
    ("PharmaLink B-Complex", "Vitamin B Complex", "Tablet", ["b complex", "vitamin b"]),
    ("PharmaLink Collagen", "Collagen", "Powder", ["collagen"]),
    ("PharmaLink Probiotic", "Probiotic", "Capsule", ["probiotic"]),
    ("PharmaLink Iron", "Iron Supplement", "Capsule", ["iron"]),
    ("PharmaLink Calcium", "Calcium", "Tablet", ["calcium"]),
    ("PharmaLink Vitamin B12", "Vitamin B12", "Tablet", ["b12", "vitamin b12"]),
    ("PharmaLink Turmeric", "Turmeric", "Capsule", ["turmeric", "curcumin"]),
    ("PharmaLink Ashwagandha", "Ashwagandha", "Capsule", ["ashwagandha"]),
    ("PharmaLink Melatonin", "Melatonin", "Tablet", ["melatonin"]),
    ("PharmaLink Glucosamine", "Glucosamine", "Capsule", ["glucosamine"]),
    ("PharmaLink Biotin", "Biotin", "Tablet", ["biotin", "vitamin b7"]),
]

DOCTORS = [
    ("LB-MD-10421", "Rima Khalil", "Family medicine", "rima.khalil@doctors.test", "Clinique du Levant", "Achrafieh", True),
    ("LB-MD-20876", "Samir Aoun", "Cardiology", "samir.aoun@doctors.test", "Beirut Heart Center", "Hamra", False),
    ("LB-MD-30155", "Lina Nassar", "Endocrinology", "lina.nassar@doctors.test", "Verdun Medical", "Verdun", False),
]

# label, lat, lng, area - two clusters, so batching has something to exploit
SHOPPER_ADDRESSES = [
    ("Home - Hamra", 33.8991, 35.4772, "Hamra"),
    ("Office - Hamra", 33.8952, 35.4801, "Hamra"),
    ("Home - Achrafieh", 33.8901, 35.5199, "Achrafieh"),
    ("Parents - Achrafieh", 33.8872, 35.5221, "Achrafieh"),
    ("Home - Gemmayze", 33.8968, 35.5121, "Gemmayze"),
    ("Home - Verdun", 33.8781, 35.4858, "Verdun"),
]

DRIVERS = [
    ("Karim Saad", "+961-70-111-201", Driver.Vehicle.SCOOTER, 60, 33.8960, 35.4800),
    ("Joe Mansour", "+961-70-111-202", Driver.Vehicle.SCOOTER, 50, 33.8900, 35.5150),
    ("Ali Zein", "+961-70-111-203", Driver.Vehicle.CAR, 120, 33.8850, 35.5000),
]


class Command(BaseCommand):
    help = "Seed the full HealthConnect POC scenario (pharmacies, catalog, doctors, shoppers, orders, drivers)."

    def add_arguments(self, parser):
        parser.add_argument("--reset-orders", action="store_true", help="Delete existing demo orders and routes first.")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(7)  # deterministic demo
        User = get_user_model()

        if options["reset_orders"]:
            from apps.delivery.models import DeliveryRoute

            DeliveryRoute.objects.all().delete()
            Order.objects.all().delete()
            self.stdout.write("Cleared existing orders and routes.")

        admin = self._user(User, "admin@healthconnect.dev", UserRole.PLATFORM_ADMIN, is_staff=True, is_superuser=True)
        pharmacies = self._pharmacies()
        owners = self._pharmacy_users(User, pharmacies)
        medicines = self._catalog()
        supplements = self._supplements()
        self._stock(pharmacies, medicines, owners, supplements)
        self._integration(pharmacies[0], owners[pharmacies[0].id], medicines)
        doctors = self._doctors(User)
        shoppers, addresses = self._shoppers(User)
        self._clients(pharmacies, owners)
        self._payment_methods(shoppers)
        # Prescriptions before refills: a repeat schedule for a prescription-only
        # medicine has to point at a real one.
        prescriptions = self._prescriptions(doctors, medicines, shoppers)
        self._orders(shoppers, addresses, medicines, owners, prescriptions)
        self._refills(shoppers, addresses, medicines, supplements, prescriptions)
        self._drivers(User)

        self.stdout.write(self.style.SUCCESS("\nHealthConnect POC scenario seeded."))
        self.stdout.write("\nSign-in accounts (all password: Password123!)")
        self.stdout.write(f"  Platform admin   {admin.email}")
        self.stdout.write("  Pharmacy owner   owner@cedarcare.test          (Cedar Care, Hamra)")
        self.stdout.write("  Pharmacy staff   staff@cedarcare.test")
        self.stdout.write("  Pharmacy owner   owner@achrafiehhealth.test    (Achrafieh Health)")
        self.stdout.write("  Doctor           rima.khalil@doctors.test      (already activated)")
        self.stdout.write("  Shopper          shopper1@healthconnect.dev")
        self.stdout.write("  Driver           karim@healthconnect.dev")
        self.stdout.write("\nNot yet activated, to demo the zero-onboarding claim flow:")
        self.stdout.write("  Licence LB-MD-20876 / samir.aoun@doctors.test")
        self.stdout.write("  Licence LB-MD-30155 / lina.nassar@doctors.test")
        self.stdout.write("\nNext: POST /api/dispatch/plan/ as admin (or open /admin/dispatch) to see routing.")

    # ---------------------------------------------------------------- helpers
    def _user(self, User, email, role, **extra):
        user, _ = User.objects.update_or_create(email=email, defaults={"role": role, "is_active": True, **extra})
        user.set_password(PASSWORD)
        user.save()
        return user

    def _pharmacies(self):
        records = []
        for name, area, lat, lng, rating, count, reliability in PHARMACIES:
            pharmacy, _ = Pharmacy.objects.update_or_create(
                name=name,
                area=area,
                defaults={
                    "address": f"{area} main street, Beirut",
                    "city": "Beirut",
                    "phone": f"+961-1-555-{random.randint(100, 999)}",
                    "whatsapp": f"+961-70-555-{random.randint(100, 999)}",
                    "email": f"hello@{name.split()[0].lower()}.example",
                    "latitude": Decimal(str(lat)),
                    "longitude": Decimal(str(lng)),
                    "is_active": True,
                    "is_public": True,
                    "accepts_online_orders": True,
                    "delivery_enabled": True,
                    "rating_average": Decimal(rating),
                    "rating_count": count,
                    "fulfillment_success_rate": Decimal(reliability),
                    "orders_fulfilled": count,
                    "order_preparation_minutes": random.choice([10, 15, 20]),
                },
            )
            records.append(pharmacy)
        self.stdout.write(f"Pharmacies: {len(records)}")
        return records

    def _pharmacy_users(self, User, pharmacies):
        owners = {}
        for pharmacy in pharmacies:
            slug = pharmacy.name.replace(" Pharmacy", "").replace(" ", "").lower()
            owner = self._user(User, f"owner@{slug}.test", UserRole.PHARMACY_OWNER, pharmacy=pharmacy, first_name="Owner", last_name=pharmacy.area)
            owners[pharmacy.id] = owner
        # Keep the original demo credentials working.
        cedar = pharmacies[0]
        self._user(User, "owner@cedarcare.test", UserRole.PHARMACY_OWNER, pharmacy=cedar, first_name="Nour", last_name="Haddad")
        self._user(User, "staff@cedarcare.test", UserRole.PHARMACY_STAFF, pharmacy=cedar, first_name="Maya", last_name="Khoury")
        owners[cedar.id] = User.objects.get(email="owner@cedarcare.test")
        self._user(User, "owner@achrafiehhealth.test", UserRole.PHARMACY_OWNER, pharmacy=pharmacies[2], first_name="Rita", last_name="Sfeir")
        owners[pharmacies[2].id] = User.objects.get(email="owner@achrafiehhealth.test")
        return owners

    def _catalog(self):
        """
        Pick the demo's products out of the real catalog.

        Keyed by ingredient rather than brand: which Lebanese brand of
        atorvastatin MoPH lists is not something this command should decide, and
        it changes between syncs. Whatever it picks is a genuine registered
        product at its published price, so the seeded demo and the live
        catalogue can never tell different stories about the same medicine.
        """
        medicines: dict[str, Medicine] = {}
        missing: list[str] = []

        for ingredient, needs_prescription in SEED_INGREDIENTS:
            if len(medicines) >= MINIMUM_SEED_MEDICINES:
                break
            medicine = self._pick_product(ingredient)
            if medicine is None:
                missing.append(ingredient)
                continue
            # The MoPH import carries no prescription flag; classifying products
            # is the platform admin's job, and the demo needs it done.
            if medicine.requires_prescription != needs_prescription:
                medicine.requires_prescription = needs_prescription
                medicine.save(update_fields=["requires_prescription", "updated_at"])
            medicines[ingredient] = medicine

        if len(medicines) < MINIMUM_SEED_MEDICINES:
            raise CommandError(
                f"Only {len(medicines)} of the {MINIMUM_SEED_MEDICINES} demo medicines could be found in the catalog"
                f"{' (missing: ' + ', '.join(missing) + ')' if missing else ''}.\n"
                "The demo is built from real MoPH products and will not invent any. "
                "Run `manage.py sync_moph_catalog` first, then seed."
            )

        rx = sum(1 for medicine in medicines.values() if medicine.requires_prescription)
        self.stdout.write(f"Catalog: {len(medicines)} real MoPH products selected ({rx} prescription-only)")
        for ingredient, medicine in medicines.items():
            self.stdout.write(f"  {ingredient:<16} {medicine} @ {medicine.regulated_price}")
        return medicines

    def _pick_product(self, ingredient: str) -> Medicine | None:
        """The most demo-friendly marketed product for one active ingredient, or None."""
        low, high = SANE_PRICE
        candidates = Medicine.objects.filter(
            Q(generic_name__istartswith=ingredient) | Q(ingredients__istartswith=ingredient),
            is_active=True,
            market_status=MarketStatus.MARKETED,
            price_regime=PriceRegime.REGULATED,
            regulated_price__isnull=False,
            regulated_price__gte=low,
            regulated_price__lte=high,
        )
        # An oral solid if one exists, otherwise whatever is registered; cheapest
        # first inside each group, so a demo basket stays plausibly affordable.
        for form in PREFERRED_FORMS:
            found = candidates.filter(form__iexact=form).order_by("regulated_price").first()
            if found is not None:
                return found
        return candidates.order_by("regulated_price").first()

    def _supplements(self) -> dict[str, Medicine]:
        """
        Create the demo's supplement / parapharmacy catalog.

        These are NOT in the MoPH catalogue and have no national registry, so the
        seed is their only source (see SEED_SUPPLEMENTS). They are free-priced:
        the catalog row carries no regulated_price and every pharmacy that stocks
        one sets its own selling price. Each gets a MedicineAlias so search,
        imports and OCR can resolve the common name. Idempotent via update_or_create
        keyed on brand_name, mirroring how the rest of the command behaves.
        """
        supplements: dict[str, Medicine] = {}
        for brand, generic, form, aliases in SEED_SUPPLEMENTS:
            medicine, _ = Medicine.objects.update_or_create(
                brand_name=brand,
                defaults={
                    "generic_name": generic,
                    "form": form,
                    "category": ProductCategory.SUPPLEMENT,
                    "price_regime": PriceRegime.FREE,
                    "is_active": True,
                    "market_status": MarketStatus.MARKETED,
                    "requires_prescription": False,
                    "drug_schedule": DrugSchedule.NONE,
                },
            )
            for alias in aliases:
                MedicineAlias.objects.get_or_create(medicine=medicine, alias=alias)
            supplements[brand] = medicine
        self.stdout.write(f"Supplements: {len(supplements)} free-priced products created")
        for brand, medicine in supplements.items():
            self.stdout.write(f"  {medicine.generic_name:<20} {medicine} (price set per pharmacy)")
        return supplements

    def _stock(self, pharmacies, medicines, owners, supplements=None):
        """
        Fragmented on purpose. No single pharmacy stocks everything, so realistic baskets
        must be split - which is exactly the case the router has to handle well.

        The split is generated rather than hand-listed, because the catalog is
        now whatever `_catalog` resolved out of MoPH. Each pharmacy takes an
        overlapping slice: enough shared lines that several pharmacies can
        compete on the same medicine, and enough exclusive ones that a basket
        drawn across the catalog cannot come from one counter.
        """
        ingredients = list(medicines)
        # The first few are the everyday analgesics and antihistamines; a real
        # pharmacy carries those whatever else it stocks.
        universal = ingredients[:3]
        rest = ingredients[3:]
        plan = {
            index: universal + rest[index :: len(pharmacies)] + rest[(index + 1) % len(pharmacies) :: len(pharmacies)][:2]
            for index in range(len(pharmacies))
        }

        created = 0
        for index, pharmacy in enumerate(pharmacies):
            user = owners[pharmacy.id]
            for ingredient in dict.fromkeys(plan[index]):
                medicine = medicines[ingredient]
                # Per medicine, not per pharmacy: a pharmacy carrying stock from
                # an earlier seed still needs batches for anything new, and
                # re-running must not double a line it already has.
                if pharmacy.inventory_batches.filter(medicine=medicine, is_archived=False).exists():
                    continue
                # Free-priced lines differ between pharmacies; regulated ones cannot.
                if medicine.is_price_regulated:
                    selling = medicine.regulated_price
                else:
                    selling = (Decimal("12.00") + Decimal(random.randint(-250, 350)) / 100).quantize(Decimal("0.01"))
                quantity = random.choice([6, 12, 18, 25, 40])
                create_inventory_batch(
                    user=user,
                    pharmacy=pharmacy,
                    data={
                        "medicine": medicine,
                        "batch_number": f"{ingredient[:3].upper()}-{random.randint(2400, 2699)}",
                        "initial_quantity": quantity,
                        "expiry_date": timezone.localdate() + timedelta(days=random.choice([25, 55, 120, 240, 400])),
                        "supplier_name": random.choice(["Beirut Medical Supply", "Levant Pharma", "Mediterranean Health"]),
                        "purchase_cost": (selling * Decimal("0.68")).quantize(Decimal("0.01")),
                        "selling_price": selling,
                        "low_stock_threshold": random.choice([4, 6, 8]),
                    },
                )
                created += 1

            # Every pharmacy carries one of every supplement, so each is findable
            # and orderable everywhere. Supplements are free-priced, so each
            # pharmacy picks its own selling price for its batch (the same random
            # per-pharmacy range the free-priced medicine lines above use).
            for brand, medicine in (supplements or {}).items():
                if pharmacy.inventory_batches.filter(medicine=medicine, is_archived=False).exists():
                    continue
                selling = (Decimal("12.00") + Decimal(random.randint(-250, 350)) / 100).quantize(Decimal("0.01"))
                quantity = random.choice([6, 12, 18, 25, 40])
                create_inventory_batch(
                    user=user,
                    pharmacy=pharmacy,
                    data={
                        "medicine": medicine,
                        "batch_number": f"SUP-{random.randint(2400, 2699)}",
                        "initial_quantity": quantity,
                        "expiry_date": timezone.localdate() + timedelta(days=random.choice([120, 240, 400, 550])),
                        "supplier_name": random.choice(["Beirut Medical Supply", "Levant Pharma", "Mediterranean Health"]),
                        "purchase_cost": (selling * Decimal("0.68")).quantize(Decimal("0.01")),
                        "selling_price": selling,
                        "low_stock_threshold": random.choice([4, 6, 8]),
                    },
                )
                created += 1
        self.stdout.write(f"Stock batches: {created}")

    def _integration(self, pharmacy, owner, medicines):
        if not pharmacy.integration_keys.exists():
            key, secret = create_integration_key(pharmacy=pharmacy, user=owner, name="Counter POS connector")
            self.stdout.write(f"Integration key for {pharmacy.name}: {key.key_id}")
            self.stdout.write(f"  secret (shown once): {secret}")
        # A couple of the pharmacy's own product codes, one deliberately left unmapped
        # so the onboarding checklist has something real to show.
        mapped = medicines["Paracetamol"]
        SkuMapping.objects.get_or_create(
            pharmacy=pharmacy,
            external_code="POS-1001",
            defaults={
                "external_name": str(mapped).upper(),
                "medicine": mapped,
                "match_method": SkuMapping.MatchMethod.AUTO_EXACT,
            },
        )
        SkuMapping.objects.get_or_create(
            pharmacy=pharmacy,
            external_code="POS-9987",
            defaults={"external_name": "HOUSE BRAND THROAT LOZENGE", "match_method": SkuMapping.MatchMethod.UNMATCHED},
        )

    def _doctors(self, User):
        records = []
        for license_number, name, specialty, email, clinic, area, activate in DOCTORS:
            doctor, _ = Doctor.objects.update_or_create(
                license_number=license_number,
                defaults={
                    "full_name": name,
                    "specialty": specialty,
                    "email": email,
                    "phone": f"+961-3-{random.randint(100000, 999999)}",
                    "clinic_name": clinic,
                    "clinic_area": area,
                    "clinic_address": f"{clinic}, {area}, Beirut",
                    "source": Doctor.Source.ORDER_OF_PHYSICIANS,
                    "roster_synced_at": timezone.now(),
                    "is_active": True,
                },
            )
            if activate and not doctor.is_activated:
                user = self._user(User, email, UserRole.DOCTOR, first_name=name.split()[0], last_name=name.split()[-1])
                doctor.user = user
                doctor.is_activated = True
                doctor.activated_at = timezone.now()
                doctor.save(update_fields=["user", "is_activated", "activated_at"])
            records.append(doctor)
        self.stdout.write(f"Doctors on roster: {len(records)} ({sum(1 for d in records if d.is_activated)} activated)")
        return records

    def _shoppers(self, User):
        shoppers, addresses = [], []
        for index, (label, lat, lng, area) in enumerate(SHOPPER_ADDRESSES, start=1):
            user = self._user(User, f"shopper{index}@healthconnect.dev", UserRole.CUSTOMER, first_name=f"Shopper{index}", last_name=area)
            address, _ = DeliveryAddress.objects.update_or_create(
                user=user,
                label=label,
                defaults={
                    "contact_name": f"Shopper{index} {area}",
                    "phone": f"+961-71-{random.randint(100000, 999999)}",
                    "address": f"{label}, {area}, Beirut",
                    "area": area,
                    "city": "Beirut",
                    "latitude": Decimal(str(lat)),
                    "longitude": Decimal(str(lng)),
                    "is_default": True,
                },
            )
            shoppers.append(user)
            addresses.append(address)
        self.stdout.write(f"Shoppers: {len(shoppers)}")
        return shoppers, addresses

    def _clients(self, pharmacies, owners):
        created = 0
        names = [("Georges Haddad", "+961-3-201-455"), ("Maya Chidiac", "+961-3-778-112"), ("Hassan Fakih", "+961-3-664-901")]
        for pharmacy in pharmacies[:3]:
            for full_name, phone in names:
                _, made = Client.objects.get_or_create(
                    pharmacy=pharmacy,
                    phone=phone,
                    defaults={
                        "full_name": full_name,
                        "email": f"{full_name.split()[0].lower()}@example.test",
                        "area": pharmacy.area,
                        "address": f"{pharmacy.area}, Beirut",
                        "chronic_conditions": random.choice(["", "Type 2 diabetes", "Hypertension"]),
                        "allergies": random.choice(["", "Penicillin"]),
                        "created_by": owners[pharmacy.id],
                    },
                )
                created += int(made)
        self.stdout.write(f"Pharmacy clients created: {created}")

    def _orders(self, shoppers, addresses, medicines, owners, prescriptions):
        """
        Baskets walked into every state the order screens have to render.

        Each order goes through the real lifecycle services rather than having
        its status written directly. That matters: `hand_over` consumes the
        stock hold and writes an invoice, `cancel_order` releases it. An order
        whose status was set by hand would look right on screen while the
        inventory behind it told a different story.

        Prescription-only lines are ordered against the prescription that
        actually covers them, because placement enforces exactly that (see
        `_check_prescription_requirements`). Everything else is over-the-counter,
        drawn from across the catalog so the sourcing planner has to split some
        of these baskets across pharmacies.
        """
        otc = [name for name, medicine in medicines.items() if not medicine.requires_prescription]

        def covered_by(prescription):
            """
            The prescribed lines, so the basket matches the cover exactly.

            Capped at the platform's per-item online limit, which a 60-tablet
            cardiac prescription comfortably exceeds. Ordering part of a
            prescription is the normal case anyway, and it leaves the
            prescription partially dispensed - the state /prescriptions most
            needs to be able to render.
            """
            if prescription is None:
                return []
            limit = settings.PUBLIC_MAX_QUANTITY_PER_ITEM
            return [
                (str(item.medicine_id), min(item.quantity_prescribed, limit))
                for item in prescription.items.all()
                if item.medicine_id
            ]

        # shopper index, basket, how far to walk it, prescription
        acute, chronic = prescriptions.get("acute"), prescriptions.get("chronic")
        runs = [
            (0, covered_by(acute), "accepted", acute),
            (1, [(medicines[otc[1]].id, 1), (medicines[otc[5]].id, 2)], "preparing", None),
            (2, [(medicines[otc[0]].id, 2), (medicines[otc[3]].id, 1), (medicines[otc[6]].id, 1)], "ready", None),
            (3, covered_by(chronic), "delivered", chronic),
            (4, [(medicines[otc[2]].id, 2), (medicines[otc[4]].id, 1)], "delivered", None),
            (5, [(medicines[otc[0]].id, 3), (medicines[otc[7]].id, 1)], "cancelled", None),
        ]

        placed = 0
        for index, basket, journey, prescription in runs:
            if index >= len(shoppers):
                continue
            shopper = shoppers[index]
            if not basket or Order.objects.filter(customer=shopper).exists():
                continue
            items = [{"medicine": str(medicine_id), "quantity": quantity} for medicine_id, quantity in basket]
            try:
                order = place_order(customer=shopper, items=items, address=addresses[index], prescription=prescription)
            except Exception as exc:  # noqa: BLE001 - a partially stocked demo must still seed
                self.stdout.write(self.style.WARNING(f"  Skipped a basket for {shopper.email}: {exc}"))
                continue
            self._advance(order, journey, owners)
            placed += 1

        multi = sum(1 for order in Order.objects.all() if order.fulfillments.count() > 1)
        self.stdout.write(f"Orders placed: {placed} ({multi} span more than one pharmacy)")

    def _advance(self, order, journey: str, owners) -> None:
        """Walk one order as far along the real lifecycle as `journey` asks."""
        if journey == "cancelled":
            # Cancelled before anything was accepted, which is the only point a
            # shopper can still call it off - see cancel_order.
            cancel_order(order=order, user=order.customer, reason="Changed my mind")
            return

        for fulfillment in order.fulfillments.select_related("pharmacy"):
            user = owners[fulfillment.pharmacy_id]
            accept_fulfillment(fulfillment=fulfillment, user=user)
            if journey in {"ready", "delivered"}:
                mark_ready(fulfillment=fulfillment, user=user)
            if journey == "delivered":
                # Handover is the driver collecting; delivery is the door. Both
                # steps run, because an order sitting at PICKED_UP is "out for
                # delivery", not delivered.
                hand_over(fulfillment=fulfillment, user=user, handover_code=fulfillment.handover_code)
                mark_delivered(fulfillment=fulfillment)

        if journey != "delivered":
            return
        # A rating on one of the completed orders, so the review UI has both
        # states to render: reviewed and still awaiting one.
        order.refresh_from_db()
        pharmacy = order.fulfillments.first().pharmacy
        if not order.reviews.exists() and random.random() < 0.5:
            submit_review(
                order=order,
                pharmacy=pharmacy,
                customer=order.customer,
                rating=random.choice([4, 5]),
                comment=random.choice(["Arrived earlier than the window.", "Everything correct, well packed."]),
            )

    def _refills(self, shoppers, addresses, medicines, supplements, prescriptions):
        """
        Repeat schedules for the chronic-medication story plus one for a free-priced
        supplement (creatine), which demonstrates a recurring order that needs no
        prescription - the client's "creatine every month" case.

        One active, one paused and one already running, so /refills renders each
        state. The cardiac schedule carries the prescription the doctor issued,
        which is what lets the screen warn that cover runs out before the next
        delivery.
        """
        if RecurringOrder.objects.exists():
            return
        chronic = prescriptions.get("chronic")
        schedules = [
            (3, "Monthly cardiac refill", ["Bisoprolol", "Amlodipine"], 30, True, chronic),
            (4, "Diabetes repeat", ["Metformin"], 30, True, None),
            (2, "Allergy season", ["Cetirizine"], 45, False, None),
        ]
        created = 0
        for index, label, ingredients, interval, active, prescription in schedules:
            if index >= len(shoppers):
                continue
            items = [{"medicine": str(medicines[name].id), "quantity": 1} for name in ingredients if name in medicines]
            if not items:
                continue
            RecurringOrder.objects.create(
                customer=shoppers[index],
                address=addresses[index],
                label=label,
                items=items,
                interval_days=interval,
                preferred_hour=random.choice([10, 15, 19]),
                is_active=active,
                prescription=prescription,
                next_run_at=timezone.now() + timedelta(days=random.choice([1, 6, 19])),
            )
            created += 1

        # A free-priced supplement refill (creatine) for a shopper who isn't already
        # on the chronic schedule - placed through the same RecurringOrder flow. No
        # prescription: supplements are not regulated, so _check_prescription_requirements
        # never demands cover for them.
        creatine = next((m for m in supplements.values() if "Creatine" in m.generic_name), None)
        shopper_index = 0
        if creatine is not None and shopper_index < len(shoppers) and not RecurringOrder.objects.filter(customer=shoppers[shopper_index]).exists():
            RecurringOrder.objects.create(
                customer=shoppers[shopper_index],
                address=addresses[shopper_index],
                label="Daily creatine tub",
                items=[{"medicine": str(creatine.id), "quantity": 1}],
                interval_days=30,
                preferred_hour=random.choice([10, 15, 19]),
                is_active=True,
                prescription=None,
                next_run_at=timezone.now() + timedelta(days=random.choice([1, 6, 19])),
            )
            created += 1

        self.stdout.write(f"Refill schedules: {created} ({RecurringOrder.objects.filter(is_active=True).count()} active)")

    def _payment_methods(self, shoppers):
        """A saved card and cash per shopper, so checkout has something to pre-select."""
        created = 0
        for shopper in shoppers:
            if shopper.payment_methods.exists():
                continue
            # Card details are recognisable, not usable: brand, last four and
            # expiry, which is all SavedPaymentMethod is allowed to hold.
            SavedPaymentMethod.objects.create(
                user=shopper,
                kind=SavedPaymentMethod.Kind.CARD,
                brand=random.choice(["Visa", "Mastercard"]),
                last4=f"{random.randint(1000, 9999)}",
                expiry=f"{random.randint(1, 12):02d}/2{random.randint(8, 9)}",
                is_default=True,
            )
            SavedPaymentMethod.objects.create(user=shopper, kind=SavedPaymentMethod.Kind.CASH)
            NotificationPreferences.for_user(shopper)
            created += 1
        self.stdout.write(f"Shoppers given saved payment methods and notification preferences: {created}")

    def _prescriptions(self, doctors, medicines, shoppers):
        """
        E-prescriptions issued to the seeded shoppers' own email addresses.

        A prescription has no owning user account - it is matched to a shopper
        by the address the doctor captured, which is what MyPrescriptionsView
        looks up. Issuing them against `shopperN@healthconnect.dev` is therefore
        what makes /prescriptions show anything when signed in as one.

        One is left expired so the screen has to render a prescription that can
        no longer be claimed, rather than only the happy path.
        """
        doctor = next((item for item in doctors if item.is_activated), None)
        if doctor is None or doctor.prescriptions.exists() or not shoppers:
            return {}

        issued: dict[str, Prescription] = {}
        plans = [
            (
                "acute",
                0,
                "Complete the full antibiotic course.",
                [("Amoxicillin", 21, "tablet", "1 tablet three times daily for 7 days"), ("Paracetamol", 20, "tablet", "As needed, max 4 per day")],
                None,
            ),
            (
                "chronic",
                3,
                "Long-term cardiovascular therapy. Review in three months.",
                [("Bisoprolol", 60, "tablet", "1 tablet each morning"), ("Amlodipine", 30, "tablet", "1 tablet each evening")],
                None,
            ),
            (
                "expired",
                1,
                "Short course, now completed.",
                [("Montelukast", 30, "tablet", "1 tablet each evening")],
                # Backdated past its own validity window, so the patient screens
                # have a prescription that genuinely cannot be claimed.
                timezone.now() - timedelta(days=120),
            ),
        ]

        for key, shopper_index, note, lines, issued_at in plans:
            items = [
                {
                    "medicine": str(medicines[ingredient].id),
                    "medicine_text": str(medicines[ingredient]),
                    "quantity_prescribed": quantity,
                    "unit": unit,
                    "dosage_instructions": dosage,
                }
                for ingredient, quantity, unit, dosage in lines
                if ingredient in medicines
            ]
            if len(items) < len(lines):
                # Which brands the catalog holds is MoPH's business, but WHICH
                # INGREDIENTS this command prescribes is its own - so a line
                # that resolved to nothing is a bug here, not missing data.
                absent = [ingredient for ingredient, *_ in lines if ingredient not in medicines]
                self.stdout.write(self.style.WARNING(f"  {key} prescription is missing {', '.join(absent)}; check SEED_INGREDIENTS."))
            if not items or shopper_index >= len(shoppers):
                continue
            shopper = shoppers[shopper_index]
            prescription, secret, pin = issue_prescription(
                doctor=doctor,
                patient={
                    "patient_name": f"{shopper.first_name} {shopper.last_name}".strip(),
                    "patient_email": shopper.email,
                    "patient_phone": "",
                },
                items=items,
                diagnosis_note=note,
            )
            if issued_at is not None:
                prescription.issued_at = issued_at
                prescription.valid_until = issued_at + timedelta(days=30)
                prescription.status = Prescription.Status.EXPIRED
                prescription.save(update_fields=["issued_at", "valid_until", "status", "updated_at"])
            issued[key] = prescription

            if key == "acute":
                self.stdout.write("\nDemo prescription (consumable by ANY pharmacy, no account needed):")
                self.stdout.write(f"  Code: {prescription.code}")
                self.stdout.write(f"  PIN:  {pin}")
                self.stdout.write(f"  QR link: {prescription_url(prescription.code, secret)}")
                self.stdout.write("  Try it at /rx (manual code + PIN) or open the QR link directly.")

        self.stdout.write(f"E-prescriptions issued to shoppers: {len(issued)}")
        return issued

    def _drivers(self, User):
        created = 0
        for name, phone, vehicle, capacity, lat, lng in DRIVERS:
            email = f"{name.split()[0].lower()}@healthconnect.dev"
            user = self._user(User, email, UserRole.DRIVER, first_name=name.split()[0], last_name=name.split()[-1])
            _, made = Driver.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": name,
                    "phone": phone,
                    "vehicle_type": vehicle,
                    "capacity_units": capacity,
                    "base_latitude": Decimal(str(lat)),
                    "base_longitude": Decimal(str(lng)),
                    "is_active": True,
                    "is_online": True,
                },
            )
            created += int(made)
        self.stdout.write(f"Drivers online: {Driver.objects.filter(is_online=True).count()}")
