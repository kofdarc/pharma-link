from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from apps.medicines.models import MarketStatus, Medicine, MophSource, PriceRegime
from apps.medicines.services import moph_online
from apps.medicines.services.moph_sync import MophProductRow, sync_products

LISTING_HTML = """
<table class="table">
<thead><tr><th>ATC</th></tr></thead>
<tbody>
<tr>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">D10BA01</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">A-CNOTREN</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">G</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">Isotretinoin - 20mg</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">20mg</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">Capsule, soft gelatin</a></td>
<td><a href="/en/Drugs/view/2248" onclick="view_shop('/en/Drugs/view/2248');return false;" class="drugLink">1,526,524 L.L</a></td>
</tr>
</tbody>
</table>
<div class="paginationDiv">
<a href="/en/Drugs/index/3/4848/letter:A/page:2/sort:Drug.brand_name/direction:ASC">2</a>
<a href="/en/Drugs/index/3/4848/letter:A/page:3/sort:Drug.brand_name/direction:ASC">3</a>
</div>
"""

DETAIL_HTML = """
<table class="table">
<thead><tr><th>ATC</th><th>B/G</th><th>Ingredients</th><th>code</th><th>Registration Nb</th>
<th>Name</th><th>Dosage</th><th>Presentation</th><th>Form</th><th>Route</th><th>Agent</th>
<th>Laboratory</th><th>Country</th><th>Price</th><th>Pharmacist Margin</th><th>Stratum</th>
<th>Responsible Party Name</th><th>Responsible Party Country</th><th>Exch_date</th><th>%SUBSIDY</th></tr></thead>
<tbody>
<tr>
<td>D10BA01</td>
<td>G</td>
<!-- 		    			<td></td> -->
<td>Isotretinoin - 20mg</td>
<!-- 		    			<td></td> -->
<td>8593</td>
<td>1416/1</td>
<td>A-CNOTREN</td>
<td>20mg</td>
<td>30</td>
<td>Capsule, soft gelatin</td>
<td>Oral</td>
<td>Bellapharma S.A.R.L.</td>
<td>Pharmadex under license from Pharmathen SA, Greece</td>
<td>Lebanon</td>
<td>1,526,524 L.L</td>
<td>23.08</td>
<td>B</td>
<td></td>
<td></td>
<td>11/08/20</td>
<td></td>
</tr>
</tbody>
</table>
"""


class OnlineListingParsingTests(SimpleTestCase):
    def test_parses_rows_and_last_page_from_real_markup_shape(self):
        rows, last_page = moph_online.parse_listing_page(LISTING_HTML)

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.view_id, 2248)
        self.assertEqual(row.atc, "D10BA01")
        self.assertEqual(row.brand_name, "A-CNOTREN")
        self.assertEqual(row.ingredients, "Isotretinoin - 20mg")
        self.assertEqual(row.strength, "20mg")
        self.assertEqual(last_page, 3)

    def test_empty_page_reports_last_page_one(self):
        rows, last_page = moph_online.parse_listing_page("<tbody></tbody>")
        self.assertEqual(rows, [])
        self.assertEqual(last_page, 1)


class OnlineDetailParsingTests(SimpleTestCase):
    def test_parses_all_twenty_fields_and_builds_a_product_row(self):
        detail = moph_online.parse_detail_page(DETAIL_HTML)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["code"], "8593")
        self.assertEqual(detail["atc"], "D10BA01")
        self.assertEqual(detail["ingredients"], "Isotretinoin - 20mg")
        self.assertEqual(detail["route"], "Oral")

        row = moph_online.build_online_row(detail, source_reference="online")
        self.assertIsNotNone(row)
        self.assertEqual(row.moph_code, 8593)
        self.assertEqual(row.brand_name, "A-Cnotren")
        self.assertEqual(row.classification, "D10BA01")
        self.assertEqual(row.ingredients, "Isotretinoin - 20mg")
        self.assertEqual(row.route, "Oral")
        self.assertEqual(row.form, "Capsule, soft gelatin")
        self.assertEqual(row.market_status, MarketStatus.MARKETED)
        self.assertEqual(row.source, MophSource.MOPH_ONLINE)
        self.assertIsNone(row.price_usd)
        self.assertIn("price_ll", row.extra)

    def test_missing_code_yields_no_row(self):
        detail = {"brand_name": "Something"}
        self.assertIsNone(moph_online.build_online_row(detail, source_reference="online"))


class CrawlOrchestrationTests(SimpleTestCase):
    def test_incomplete_pagination_is_recorded_without_raising(self):
        def page_fetcher(letter, page):
            return LISTING_HTML  # always reports last_page=3, we only ever fetch page 1

        def detail_fetcher(view_id):
            return DETAIL_HTML

        rows, stats = moph_online.crawl_marketed_online(
            letters=["A"], max_pages_per_letter=1, delay_seconds=0, page_fetcher=page_fetcher, detail_fetcher=detail_fetcher
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(stats.pages_fetched, 1)
        self.assertEqual(stats.pages_expected, 3)
        # max_pages_per_letter was explicitly set, so this isn't flagged as "incomplete" -
        # only an unbounded crawl that stops short counts as a scraper problem.
        self.assertEqual(stats.letters_with_incomplete_pagination, [])

    def test_a_fetch_failure_mid_letter_is_flagged_not_fatal(self):
        def flaky_page_fetcher(letter, page):
            if page == 1:
                return LISTING_HTML  # advertises last_page=3
            raise TimeoutError("moph.gov.lb timed out")

        def detail_fetcher(view_id):
            return DETAIL_HTML

        rows, stats = moph_online.crawl_marketed_online(
            letters=["A", "B"], delay_seconds=0, page_fetcher=flaky_page_fetcher, detail_fetcher=detail_fetcher
        )

        # Page 1 of letter A still contributed its row before the failure on page 2.
        self.assertEqual(len(rows), 1)
        self.assertEqual(stats.letters_with_incomplete_pagination, ["A", "B"])
        # The whole crawl (both letters) completed despite the per-page failures.
        self.assertEqual(stats.letters_attempted, 2)


def make_row(**overrides) -> MophProductRow:
    defaults = dict(
        brand_name="Example Brand",
        strength="500mg",
        form="Tablet",
        manufacturer="Example Labs",
        market_status=MarketStatus.MARKETED,
        source=MophSource.MOPH_ONLINE,
        source_reference="test",
        moph_code=1001,
    )
    defaults.update(overrides)
    return MophProductRow(**defaults)


class SyncProductsTests(TestCase):
    def test_creates_new_marketed_product(self):
        result = sync_products([make_row(price_usd=Decimal("4.50"), source=MophSource.MOPH_MARKETED_EXCEL)])

        self.assertEqual(result["created"], 1)
        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.market_status, MarketStatus.MARKETED)
        self.assertEqual(medicine.price_regime, PriceRegime.REGULATED)
        self.assertEqual(medicine.regulated_price, Decimal("4.50"))

    def test_creates_new_non_marketed_product(self):
        result = sync_products([make_row(
            market_status=MarketStatus.NON_MARKETED, source=MophSource.MOPH_NON_MARKETED_EXCEL, price_usd=None,
        )])

        self.assertEqual(result["created"], 1)
        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.market_status, MarketStatus.NON_MARKETED)
        self.assertEqual(medicine.price_regime, PriceRegime.FREE)
        self.assertIsNone(medicine.regulated_price)

    def test_marketed_to_non_marketed_transition(self):
        sync_products([make_row(price_usd=Decimal("4.50"), source=MophSource.MOPH_MARKETED_EXCEL)])

        result = sync_products([make_row(
            market_status=MarketStatus.NON_MARKETED, source=MophSource.MOPH_NON_MARKETED_EXCEL, price_usd=None,
        )])

        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.market_status, MarketStatus.NON_MARKETED)
        self.assertEqual(result["changed_marketed_to_non_marketed"], 1)

    def test_non_marketed_to_marketed_transition_with_online_enrichment(self):
        sync_products([make_row(
            market_status=MarketStatus.NON_MARKETED, source=MophSource.MOPH_NON_MARKETED_EXCEL, price_usd=None,
        )])

        result = sync_products([make_row(
            market_status=MarketStatus.MARKETED, source=MophSource.MOPH_ONLINE,
            classification="A01AA01", ingredients="Paracetamol - 500mg", route="Oral",
        )])

        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.market_status, MarketStatus.MARKETED)
        self.assertEqual(medicine.classification, "A01AA01")
        self.assertEqual(medicine.ingredients, "Paracetamol - 500mg")
        self.assertEqual(result["changed_non_marketed_to_marketed"], 1)

    def test_same_code_in_online_and_marketed_excel_online_wins_but_price_is_borrowed(self):
        result = sync_products([
            make_row(source=MophSource.MOPH_MARKETED_EXCEL, price_usd=Decimal("9.99"), classification="", manufacturer="Excel Manufacturer"),
            make_row(source=MophSource.MOPH_ONLINE, classification="A01AA01", ingredients="Paracetamol - 500mg", manufacturer=""),
        ])

        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.moph_source, MophSource.MOPH_ONLINE)
        self.assertEqual(medicine.classification, "A01AA01")
        self.assertEqual(medicine.ingredients, "Paracetamol - 500mg")
        # Online has no USD price at all - the merge borrows it from the excel row.
        self.assertEqual(medicine.regulated_price, Decimal("9.99"))
        self.assertEqual(medicine.manufacturer, "Excel Manufacturer")
        self.assertEqual(result["duplicates_skipped"], 1)

    def test_missing_excel_value_does_not_erase_richer_existing_value(self):
        Medicine.objects.create(
            brand_name="Existing Brand", strength="500mg", form="Tablet",
            moph_code=1001, classification="N02BE01", ingredients="Paracetamol 500 mg", route="Oral",
            price_regime=PriceRegime.REGULATED, regulated_price=Decimal("2.00"), market_status=MarketStatus.MARKETED,
        )

        result = sync_products([make_row(
            market_status=MarketStatus.NON_MARKETED, source=MophSource.MOPH_NON_MARKETED_EXCEL,
            classification="", ingredients="", route="", price_usd=None,
        )])

        medicine = Medicine.objects.get(moph_code=1001)
        self.assertEqual(medicine.classification, "N02BE01")
        self.assertEqual(medicine.ingredients, "Paracetamol 500 mg")
        self.assertEqual(medicine.route, "Oral")
        self.assertEqual(medicine.market_status, MarketStatus.NON_MARKETED)
        self.assertEqual(result["updated"], 1)

    def test_duplicate_moph_code_within_one_batch_is_merged_not_duplicated(self):
        result = sync_products([make_row(), make_row(manufacturer="Different Labs")])

        self.assertEqual(Medicine.objects.filter(moph_code=1001).count(), 1)
        self.assertEqual(result["duplicates_skipped"], 1)

    def test_same_brand_different_strength_or_form_are_not_merged(self):
        sync_products([make_row(moph_code=1001, strength="500mg")])
        sync_products([make_row(moph_code=1002, strength="1000mg")])

        self.assertEqual(Medicine.objects.count(), 2)

    def test_same_variant_different_moph_codes_in_one_batch_are_merged(self):
        result = sync_products([
            make_row(moph_code=1001, source=MophSource.MOPH_ONLINE),
            make_row(moph_code=1002, source=MophSource.MOPH_MARKETED_EXCEL, price_usd=Decimal("7.25")),
            make_row(
                moph_code=1003, source=MophSource.MOPH_NON_MARKETED_EXCEL,
                market_status=MarketStatus.NON_MARKETED,
            ),
        ])

        self.assertEqual(Medicine.objects.count(), 1)
        medicine = Medicine.objects.get()
        # Highest-priority source (online) keeps identity and market status.
        self.assertEqual(medicine.moph_code, 1001)
        self.assertEqual(medicine.market_status, MarketStatus.MARKETED)
        self.assertEqual(medicine.moph_extra["alternate_moph_codes"], [1002, 1003])
        # USD price is still borrowed from the marketed-excel sibling.
        self.assertEqual(medicine.regulated_price, Decimal("7.25"))
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["duplicates_skipped"], 2)

    def test_same_variant_merge_keeps_the_code_already_bound_to_the_existing_row(self):
        Medicine.objects.create(
            brand_name="Example Brand", strength="500mg", form="Tablet", moph_code=1002,
            price_regime=PriceRegime.REGULATED, regulated_price=Decimal("1.00"),
            market_status=MarketStatus.MARKETED,
        )

        result = sync_products([
            make_row(moph_code=1001, source=MophSource.MOPH_ONLINE),
            make_row(moph_code=1002, source=MophSource.MOPH_ONLINE),
        ])

        self.assertEqual(Medicine.objects.count(), 1)
        medicine = Medicine.objects.get()
        self.assertEqual(medicine.moph_code, 1002)
        self.assertEqual(medicine.moph_extra["alternate_moph_codes"], [1001])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["duplicates_skipped"], 1)

    def test_malformed_row_missing_brand_is_skipped(self):
        result = sync_products([make_row(brand_name="")])

        self.assertEqual(result["invalid_rows"], 1)
        self.assertEqual(Medicine.objects.count(), 0)

    def test_idempotent_second_run_makes_no_changes(self):
        row = make_row(price_usd=Decimal("4.50"), source=MophSource.MOPH_MARKETED_EXCEL)
        sync_products([row])

        result = sync_products([row])

        self.assertEqual(Medicine.objects.count(), 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["unchanged"], 1)

    def test_legacy_row_without_moph_code_backfills_via_brand_strength_match(self):
        existing = Medicine.objects.create(
            brand_name="Legacy Brand", strength="10mg", form="Tablet",
            price_regime=PriceRegime.REGULATED, regulated_price=Decimal("3.00"),
        )

        sync_products([make_row(brand_name="Legacy Brand", strength="10mg", form="Tablet", moph_code=2002, price_usd=Decimal("3.50"))])

        existing.refresh_from_db()
        self.assertEqual(existing.moph_code, 2002)
        self.assertEqual(Medicine.objects.count(), 1)

    def test_constraint_collision_is_logged_and_skipped_not_fatal(self):
        Medicine.objects.create(
            brand_name="Taken Brand", strength="10mg", form="Tablet", moph_code=9001,
            price_regime=PriceRegime.REGULATED, regulated_price=Decimal("1.00"),
        )

        result = sync_products([
            make_row(moph_code=9002, brand_name="Taken Brand", strength="10mg", form="Tablet", price_usd=Decimal("2.00")),
        ])

        self.assertEqual(result["duplicates_skipped"], 1)
        self.assertEqual(Medicine.objects.filter(brand_name="Taken Brand").count(), 1)
