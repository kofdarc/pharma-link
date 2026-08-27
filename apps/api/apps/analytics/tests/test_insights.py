"""
Smart Insights (apps/analytics/services/insights.py): a rule-based synthesis layer over the
KPI service, not an LLM call. See docs/AI_FEATURES.md §5.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.analytics.services.insights import generate_insights
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.orders.models import UnmetDemandSignal
from apps.pharmacies.models import Pharmacy
from apps.sales.services.create_sale import create_sale


class InsightsTestCase(TestCase):
    def setUp(self):
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.user = get_user_model().objects.create_user(
            email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy
        )
        self.medicine = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("2.25"),
        )

    def batch_data(self, **overrides):
        # create_inventory_batch() always derives current_quantity from initial_quantity, so
        # tests that want a specific starting stock level must override initial_quantity.
        data = {
            "medicine": self.medicine,
            "batch_number": "B-1",
            "initial_quantity": 10,
            "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
            "purchase_cost": Decimal("1.00"),
            "selling_price": Decimal("2.25"),
            "low_stock_threshold": 3,
        }
        data.update(overrides)
        return data

    def test_no_data_yields_no_insights(self):
        self.assertEqual(generate_insights(self.pharmacy), [])

    def test_expiring_stock_flagged_critical(self):
        create_inventory_batch(
            user=self.user,
            pharmacy=self.pharmacy,
            data=self.batch_data(expiry_date=timezone.localdate() + timezone.timedelta(days=10)),
        )

        insights = generate_insights(self.pharmacy)

        expiry = next(i for i in insights if i["id"] == "expiry-30d")
        self.assertEqual(expiry["severity"], "critical")

    def test_low_stock_flagged(self):
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(initial_quantity=2, low_stock_threshold=5))

        insights = generate_insights(self.pharmacy)

        low_stock = next(i for i in insights if i["id"] == "low-stock")
        self.assertEqual(low_stock["metric"], 1)

    def test_unmet_demand_for_unstocked_medicine_is_an_opportunity(self):
        other = Medicine.objects.create(
            brand_name="Augmentin",
            generic_name="Amoxicillin/Clavulanate",
            strength="1g",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("14.75"),
        )
        UnmetDemandSignal.objects.create(medicine=other, area="Hamra", quantity_requested=2, source=UnmetDemandSignal.Source.SEARCH)
        UnmetDemandSignal.objects.create(medicine=other, area="Hamra", quantity_requested=1, source=UnmetDemandSignal.Source.SEARCH)

        insights = generate_insights(self.pharmacy)

        opportunity = next(i for i in insights if i["id"] == "unmet-demand")
        self.assertEqual(opportunity["severity"], "opportunity")
        self.assertEqual(opportunity["metric"], 2)

    def test_stocking_the_demanded_medicine_suppresses_the_opportunity_insight(self):
        UnmetDemandSignal.objects.create(medicine=self.medicine, area="Hamra", quantity_requested=3, source=UnmetDemandSignal.Source.SEARCH)
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data())

        insights = generate_insights(self.pharmacy)

        self.assertFalse(any(i["id"] == "unmet-demand" for i in insights))

    def test_dead_stock_flagged_when_nothing_sold_recently(self):
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(initial_quantity=10))

        insights = generate_insights(self.pharmacy)

        dead_stock = next(i for i in insights if i["id"] == "dead-stock")
        self.assertEqual(dead_stock["severity"], "warning")

    def test_a_recent_sale_clears_dead_stock_flag(self):
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(initial_quantity=10))
        create_sale(user=self.user, pharmacy=self.pharmacy, items=[{"medicine": self.medicine.id, "quantity": 1}])

        insights = generate_insights(self.pharmacy)

        self.assertFalse(any(i["id"] == "dead-stock" for i in insights))

    def test_insights_are_sorted_critical_first(self):
        create_inventory_batch(
            user=self.user,
            pharmacy=self.pharmacy,
            data=self.batch_data(initial_quantity=2, low_stock_threshold=5, expiry_date=timezone.localdate() + timezone.timedelta(days=10)),
        )

        insights = generate_insights(self.pharmacy)

        severities = [i["severity"] for i in insights]
        self.assertEqual(severities, sorted(severities, key=lambda s: {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}[s]))

    def test_limit_caps_the_result(self):
        create_inventory_batch(
            user=self.user,
            pharmacy=self.pharmacy,
            data=self.batch_data(initial_quantity=2, low_stock_threshold=5, expiry_date=timezone.localdate() + timezone.timedelta(days=10)),
        )

        insights = generate_insights(self.pharmacy, limit=1)

        self.assertEqual(len(insights), 1)
