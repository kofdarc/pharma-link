from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, MedicineAlias
from apps.pharmacies.models import Pharmacy


class Command(BaseCommand):
    help = "Seed demo pharmacies, users, medicines, and inventory for local MVP testing."

    def handle(self, *args, **options):
        User = get_user_model()
        pharmacy, _ = Pharmacy.objects.update_or_create(
            name="Cedar Care Pharmacy",
            area="Hamra",
            defaults={
                "address": "Hamra Street, Beirut",
                "city": "Beirut",
                "phone": "+961-1-555-010",
                "whatsapp": "+961-70-555-010",
                "email": "hello@cedarcare.example",
                "is_active": True,
                "is_public": True,
            },
        )
        admin, _ = User.objects.update_or_create(
            email="admin@pharmalink.test",
            defaults={"role": UserRole.PLATFORM_ADMIN, "is_staff": True, "is_superuser": True, "is_active": True},
        )
        admin.set_password("Password123!")
        admin.save()
        owner, _ = User.objects.update_or_create(
            email="owner@cedarcare.test",
            defaults={"role": UserRole.PHARMACY_OWNER, "pharmacy": pharmacy, "is_active": True, "first_name": "Nour", "last_name": "Haddad"},
        )
        owner.set_password("Password123!")
        owner.save()
        staff, _ = User.objects.update_or_create(
            email="staff@cedarcare.test",
            defaults={"role": UserRole.PHARMACY_STAFF, "pharmacy": pharmacy, "is_active": True, "first_name": "Maya", "last_name": "Khoury"},
        )
        staff.set_password("Password123!")
        staff.save()

        panadol, _ = Medicine.objects.update_or_create(
            brand_name="Panadol",
            strength="500mg",
            form="Tablet",
            defaults={"generic_name": "Paracetamol", "manufacturer": "GSK", "is_active": True},
        )
        MedicineAlias.objects.get_or_create(medicine=panadol, alias="Acetaminophen", defaults={"alias_type": MedicineAlias.AliasType.GENERIC})
        amoxil, _ = Medicine.objects.update_or_create(
            brand_name="Amoxil",
            strength="500mg",
            form="Capsule",
            defaults={"generic_name": "Amoxicillin", "manufacturer": "GSK", "is_active": True},
        )

        if not pharmacy.inventory_batches.exists():
            create_inventory_batch(
                user=staff,
                pharmacy=pharmacy,
                data={
                    "medicine": panadol,
                    "batch_number": "PND-2401",
                    "initial_quantity": 40,
                    "expiry_date": timezone.localdate() + timedelta(days=180),
                    "supplier_name": "Beirut Medical Supply",
                    "purchase_cost": Decimal("1.50"),
                    "selling_price": Decimal("2.25"),
                    "low_stock_threshold": 8,
                },
            )
            create_inventory_batch(
                user=staff,
                pharmacy=pharmacy,
                data={
                    "medicine": amoxil,
                    "batch_number": "AMX-2402",
                    "initial_quantity": 4,
                    "expiry_date": timezone.localdate() + timedelta(days=40),
                    "supplier_name": "Levant Pharma",
                    "purchase_cost": Decimal("3.25"),
                    "selling_price": Decimal("4.10"),
                    "low_stock_threshold": 6,
                },
            )

        self.stdout.write(self.style.SUCCESS("Seeded HealthConnect demo data."))
        self.stdout.write("Admin: admin@pharmalink.test / Password123!")
        self.stdout.write("Owner: owner@cedarcare.test / Password123!")
        self.stdout.write("Staff: staff@cedarcare.test / Password123!")

