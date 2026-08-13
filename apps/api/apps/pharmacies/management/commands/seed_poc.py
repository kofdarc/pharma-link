"""
Seeds a demo scenario that actually exercises the hard parts of the POC:

  - 5 Beirut pharmacies with real-ish coordinates, ratings and reliability
  - a catalog split between MoPH-regulated medicines and free-priced supplements
  - stock deliberately fragmented so some baskets CANNOT come from one pharmacy
  - 3 doctors from the "Order of Physicians" roster, one already activated
  - 6 shopper orders clustered in two neighbourhoods, several multi-pharmacy,
    which is what makes pickup consolidation visible in the dispatch plan
  - 3 drivers online, so the router has real choices to make
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.customers.models import Client
from apps.delivery.models import Driver
from apps.eprescriptions.models import Doctor
from apps.eprescriptions.services.issue import issue_prescription
from apps.eprescriptions.services.qr import prescription_url
from apps.integrations.models import SkuMapping
from apps.integrations.services.keys import create_integration_key
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, MedicineAlias, PriceRegime, ProductCategory
from apps.orders.models import DeliveryAddress, Order, OrderFulfillment, RecurringOrder
from apps.orders.services.lifecycle import accept_fulfillment
from apps.orders.services.placement import place_order
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

# name, generic, strength, form, category, regime, price
CATALOG = [
    ("Panadol", "Paracetamol", "500mg", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "2.25"),
    ("Doliprane", "Paracetamol", "1000mg", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "3.10"),
    ("Amoxil", "Amoxicillin", "500mg", "Capsule", ProductCategory.MEDICINE, PriceRegime.REGULATED, "8.40"),
    ("Augmentin", "Amoxicillin/Clavulanate", "1g", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "14.75"),
    ("Ventolin", "Salbutamol", "100mcg", "Inhaler", ProductCategory.MEDICINE, PriceRegime.REGULATED, "9.90"),
    ("Glucophage", "Metformin", "850mg", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "6.30"),
    ("Concor", "Bisoprolol", "5mg", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "11.20"),
    ("Nexium", "Esomeprazole", "40mg", "Tablet", ProductCategory.MEDICINE, PriceRegime.REGULATED, "18.60"),
    ("Vitamin D3 Forte", "Cholecalciferol", "50000IU", "Capsule", ProductCategory.SUPPLEMENT, PriceRegime.FREE, None),
    ("Omega 3 Gold", "Fish oil", "1000mg", "Softgel", ProductCategory.SUPPLEMENT, PriceRegime.FREE, None),
    ("Magnesium Complex", "Magnesium citrate", "400mg", "Tablet", ProductCategory.SUPPLEMENT, PriceRegime.FREE, None),
    ("Hydra Face Cream", "", "50ml", "Cream", ProductCategory.PARAPHARMACY, PriceRegime.FREE, None),
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
    help = "Seed the full PharmaLink POC scenario (pharmacies, catalog, doctors, shoppers, orders, drivers)."

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

        admin = self._user(User, "admin@pharmalink.test", UserRole.PLATFORM_ADMIN, is_staff=True, is_superuser=True)
        pharmacies = self._pharmacies()
        owners = self._pharmacy_users(User, pharmacies)
        medicines = self._catalog()
        self._stock(pharmacies, medicines, owners)
        self._integration(pharmacies[0], owners[pharmacies[0].id], medicines)
        doctors = self._doctors(User)
        shoppers, addresses = self._shoppers(User)
        self._clients(pharmacies, owners)
        self._orders(shoppers, addresses, medicines, owners)
        self._prescriptions(doctors, medicines)
        self._drivers(User)

        self.stdout.write(self.style.SUCCESS("\nPharmaLink POC scenario seeded."))
        self.stdout.write("\nSign-in accounts (all password: Password123!)")
        self.stdout.write(f"  Platform admin   {admin.email}")
        self.stdout.write("  Pharmacy owner   owner@cedarcare.test          (Cedar Care, Hamra)")
        self.stdout.write("  Pharmacy staff   staff@cedarcare.test")
        self.stdout.write("  Pharmacy owner   owner@achrafiehhealth.test    (Achrafieh Health)")
        self.stdout.write("  Doctor           rima.khalil@doctors.test      (already activated)")
        self.stdout.write("  Shopper          shopper1@pharmalink.test")
        self.stdout.write("  Driver           karim@pharmalink.test")
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
        medicines = {}
        for brand, generic, strength, form, category, regime, price in CATALOG:
            medicine, _ = Medicine.objects.update_or_create(
                brand_name=brand,
                strength=strength,
                form=form,
                defaults={
                    "generic_name": generic,
                    "manufacturer": random.choice(["GSK", "Sanofi", "Novartis", "Pharmaline", "Benta"]),
                    "category": category,
                    "price_regime": regime,
                    "regulated_price": Decimal(price) if price else None,
                    "regulated_price_reference": "MoPH price list 2026-Q1" if price else "",
                    "regulated_price_updated_at": timezone.now() if price else None,
                    "requires_prescription": category == ProductCategory.MEDICINE and brand in {"Amoxil", "Augmentin", "Concor", "Nexium"},
                    "is_active": True,
                },
            )
            medicines[brand] = medicine
            if generic:
                MedicineAlias.objects.get_or_create(medicine=medicine, alias=generic, defaults={"alias_type": MedicineAlias.AliasType.GENERIC})
        MedicineAlias.objects.get_or_create(
            medicine=medicines["Panadol"], alias="Acetaminophen", defaults={"alias_type": MedicineAlias.AliasType.GENERIC}
        )
        self.stdout.write(f"Catalog: {len(medicines)} products ({sum(1 for m in medicines.values() if m.is_price_regulated)} MoPH-regulated)")
        return medicines

    def _stock(self, pharmacies, medicines, owners):
        """
        Fragmented on purpose. No single pharmacy stocks everything, so realistic baskets
        must be split - which is exactly the case the router has to handle well.
        """
        plan = {
            0: ["Panadol", "Amoxil", "Vitamin D3 Forte", "Glucophage", "Omega 3 Gold"],
            1: ["Panadol", "Doliprane", "Ventolin", "Magnesium Complex"],
            2: ["Augmentin", "Nexium", "Concor", "Vitamin D3 Forte", "Hydra Face Cream"],
            3: ["Doliprane", "Ventolin", "Omega 3 Gold"],
            4: ["Panadol", "Glucophage", "Nexium", "Magnesium Complex", "Hydra Face Cream"],
        }
        created = 0
        for index, pharmacy in enumerate(pharmacies):
            if pharmacy.inventory_batches.exists():
                continue
            user = owners[pharmacy.id]
            for brand in plan[index]:
                medicine = medicines[brand]
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
                        "batch_number": f"{brand[:3].upper()}-{random.randint(2400, 2699)}",
                        "initial_quantity": quantity,
                        "expiry_date": timezone.localdate() + timedelta(days=random.choice([25, 55, 120, 240, 400])),
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
        SkuMapping.objects.get_or_create(
            pharmacy=pharmacy,
            external_code="POS-1001",
            defaults={"external_name": "PANADOL 500 TAB", "medicine": medicines["Panadol"], "match_method": SkuMapping.MatchMethod.AUTO_EXACT},
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
            user = self._user(User, f"shopper{index}@pharmalink.test", UserRole.CUSTOMER, first_name=f"Shopper{index}", last_name=area)
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

    def _orders(self, shoppers, addresses, medicines, owners):
        """
        Baskets chosen so several must be split across pharmacies. Once accepted, these are
        exactly the jobs the dispatcher consolidates.
        """
        baskets = [
            [("Panadol", 2), ("Vitamin D3 Forte", 1)],
            [("Ventolin", 1), ("Nexium", 2)],
            [("Augmentin", 1), ("Panadol", 1), ("Omega 3 Gold", 1)],
            [("Concor", 2), ("Glucophage", 1)],
            [("Doliprane", 2), ("Magnesium Complex", 1)],
            [("Hydra Face Cream", 1), ("Panadol", 3)],
        ]
        placed = 0
        for shopper, address, basket in zip(shoppers, addresses, baskets):
            if Order.objects.filter(customer=shopper).exists():
                continue
            items = [{"medicine": str(medicines[brand].id), "quantity": quantity} for brand, quantity in basket]
            try:
                order = place_order(customer=shopper, items=items, address=address)
            except Exception as exc:  # noqa: BLE001 - a partially stocked demo must still seed
                self.stdout.write(self.style.WARNING(f"  Skipped a basket for {shopper.email}: {exc}"))
                continue
            # Accept every slice so the orders are dispatchable straight away.
            for fulfillment in order.fulfillments.select_related("pharmacy"):
                accept_fulfillment(fulfillment=fulfillment, user=owners[fulfillment.pharmacy_id])
            placed += 1

        multi = sum(1 for order in Order.objects.all() if order.fulfillments.count() > 1)
        self.stdout.write(f"Orders placed: {placed} ({multi} span more than one pharmacy)")

        # One recurring schedule, for the chronic-medication story.
        if shoppers and not RecurringOrder.objects.exists():
            RecurringOrder.objects.create(
                customer=shoppers[3],
                address=addresses[3],
                label="Monthly cardiac refill",
                items=[{"medicine": str(medicines["Concor"].id), "quantity": 2}, {"medicine": str(medicines["Glucophage"].id), "quantity": 1}],
                interval_days=30,
                next_run_at=timezone.now() + timedelta(days=1),
            )
            self.stdout.write("Recurring order: 1 (monthly cardiac refill)")

    def _prescriptions(self, doctors, medicines):
        doctor = next((item for item in doctors if item.is_activated), None)
        if doctor is None or doctor.prescriptions.exists():
            return
        prescription, secret, pin = issue_prescription(
            doctor=doctor,
            patient={"patient_name": "Georges Haddad", "patient_email": "georges@example.test", "patient_phone": "+961-3-201-455"},
            items=[
                {"medicine": str(medicines["Augmentin"].id), "medicine_text": "Augmentin 1g", "quantity_prescribed": 14, "unit": "tablet", "dosage_instructions": "1 tablet twice daily for 7 days"},
                {"medicine": str(medicines["Panadol"].id), "medicine_text": "Panadol 500mg", "quantity_prescribed": 20, "unit": "tablet", "dosage_instructions": "As needed, max 4 per day"},
            ],
            diagnosis_note="Complete the full antibiotic course.",
        )
        self.stdout.write("\nDemo prescription (consumable by ANY pharmacy, no account needed):")
        self.stdout.write(f"  Code: {prescription.code}")
        self.stdout.write(f"  PIN:  {pin}")
        self.stdout.write(f"  QR link: {prescription_url(prescription.code, secret)}")
        self.stdout.write("  Try it at /rx (manual code + PIN) or open the QR link directly.")

    def _drivers(self, User):
        created = 0
        for name, phone, vehicle, capacity, lat, lng in DRIVERS:
            email = f"{name.split()[0].lower()}@pharmalink.test"
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
