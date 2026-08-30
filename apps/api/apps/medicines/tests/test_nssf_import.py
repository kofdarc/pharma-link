"""
Parsing and applying the NSSF reimbursable-drug lists.

Fixtures below are trimmed `pdftotext -layout` output from the real April 2025 lists -
same column spacing, a handful of representative rows: an exact match, a row whose NSSF
price is "-", a 95% row that also appears at 80%, a `#####` overflow row, and a code with
no catalog entry.
"""

from decimal import Decimal

from django.test import TestCase

from apps.medicines.models import Medicine, PriceRegime
from apps.medicines.services.nssf_import import DEFAULT_LBP_PER_USD, apply_rows, parse_lists

LIST_80 = """
2025/4/17 date 80% covered list

Code      Reg #   name B/G  strength  qty UOM   MoPH price   NSSF price  Cat  Group ST  substitute   rate
   10548 167320/1 AcetylsalicyA.S HEART G            81mg            30 tablet        148,463                105,972      D                 G5           ASPICOT - 81mg x 100                                                  80%
    9325 42316/1 AripiprazoleABILIFY MAB             400mg             1 vial      29,491,998             29,491,998      D                 G4           ABILIFY MAINTENA - 400mg x 1                                          80%
   11325 147822/1 Adalimuma ABRILADA BioTech         40mg              2 syringe   40,259,574                    -        C                 G2      *    CINNORA - 40mg/0.8ml x 2                                              80%
   10626 141720/1 LanadelumaTAKHZYRO BioTech         300mg/2m          1 vial       ##############                  -        C                 G4      **   TAKHZYRO - 300mg/2ml x 1                                             80%
   99999 12345/1 Nonexistent NOTHING G              10mg             30 tablet        100,000                 90,000      D                 G5           NOTHING - 10mg x 30                                                   80%
"""

LIST_95 = """
2025/4/17 date 95% covered list

Code      Reg #   name B/G  strength  qty UOM   MoPH price   NSSF price  Cat  Group ST  substitute   rate
   10548 167320/1 AcetylsalicyA.S HEART G            81mg            30 tablet        148,463                105,972      D                 G5           ASPICOT - 81mg x 100                                                  80%
    9325 42316/1 AripiprazoleABILIFY MAB             400mg             1 vial      29,491,998             29,491,998      D                 G4           ABILIFY MAINTENA - 400mg x 1                                          80%
   10957 90722/1 Imatinib - 1 IMATINIB NG           100mg             60 tablet     31,085,276                363,006      A21               G3      **   IMATINIB GP PHARM - 100mg x 180                                       95%
"""


class NssfParseTests(TestCase):
    def test_parses_every_row_and_merges_on_higher_rate(self):
        parsed = parse_lists(LIST_80, LIST_95)

        self.assertEqual(parsed.unparsed_lines, 0)
        # 5 distinct from list 80 + 1 new (Imatinib) from list 95
        self.assertEqual(len(parsed.rows), 6)
        self.assertEqual(parsed.rows[10548].reimbursement_rate, 80)
        self.assertEqual(parsed.rows[10548].nssf_price_lbp, 105972)
        self.assertEqual(parsed.rows[11325].nssf_price_lbp, None)  # "-"
        self.assertEqual(parsed.rows[10626].nssf_price_lbp, None)  # "#####" moph price, "-" nssf
        self.assertEqual(parsed.rows[10957].reimbursement_rate, 95)

    def test_higher_rate_wins_when_a_code_appears_in_both_lists(self):
        # Pretend A.S Heart is 95% in the second list.
        list_95_bump = LIST_95.replace(
            "ASPICOT - 81mg x 100                                                  80%",
            "ASPICOT - 81mg x 100                                                  95%",
        )
        parsed = parse_lists(LIST_80, list_95_bump)
        self.assertEqual(parsed.rows[10548].reimbursement_rate, 95)


class NssfApplyTests(TestCase):
    def setUp(self):
        self.aspirin = Medicine.objects.create(
            brand_name="A.S Heart", strength="81mg", form="Tablet", price_regime=PriceRegime.FREE, moph_code=10548
        )
        self.abilify = Medicine.objects.create(
            brand_name="Abilify Maintena", strength="400mg", form="Vial", price_regime=PriceRegime.FREE, moph_code=9325
        )

    def test_apply_sets_coverage_rate_and_converted_reference_price(self):
        result = apply_rows(parse_lists(LIST_80, LIST_95))

        self.assertEqual(result.updated, 2)
        self.assertIn(99999, result.unmatched_codes)

        self.aspirin.refresh_from_db()
        self.assertTrue(self.aspirin.nssf_covered)
        self.assertEqual(self.aspirin.nssf_reimbursement_rate, Decimal("80"))
        self.assertEqual(self.aspirin.nssf_reference_price, (Decimal("105972") / DEFAULT_LBP_PER_USD).quantize(Decimal("0.01")))
        self.assertIn("NSSF reimbursable list 2025-04-17 (80%)", self.aspirin.nssf_source_reference)
        self.assertIsNotNone(self.aspirin.nssf_updated_at)

    def test_apply_is_idempotent(self):
        parsed = parse_lists(LIST_80, LIST_95)
        apply_rows(parsed)
        second = apply_rows(parsed)
        self.assertEqual(second.updated, 0)
        self.assertEqual(second.unchanged, 2)

    def test_deactivate_missing_clears_only_importer_set_coverage(self):
        apply_rows(parse_lists(LIST_80, LIST_95))
        # A manually curated medicine that is not on any list must survive a re-import.
        manual = Medicine.objects.create(
            brand_name="Manual Med", strength="5mg", form="Tablet", price_regime=PriceRegime.FREE, moph_code=88888,
            nssf_covered=True, nssf_reimbursement_rate=Decimal("80"), nssf_source_reference="hand-entered by pharmacist",
        )

        # Re-import a list that no longer contains Abilify (code 9325).
        shrunk = "\n".join(line for line in LIST_80.splitlines() if "42316/1" not in line)
        result = apply_rows(parse_lists(shrunk))

        self.assertEqual(result.deactivated, 1)
        self.abilify.refresh_from_db()
        manual.refresh_from_db()
        self.assertFalse(self.abilify.nssf_covered)
        self.assertTrue(manual.nssf_covered)  # untouched
