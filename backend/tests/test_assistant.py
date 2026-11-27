import tempfile
import unittest
from pathlib import Path

from ssust import assistant, prices
from ssust.dates import FixedClock
from ssust.service import Service
from ssust.store import open_books

CHAINS = prices.load_chains()[0]


class ParseEntry(unittest.TestCase):
    def parse(self, text):
        return assistant.parse_entry(text, CHAINS)

    def test_amount_chain_and_note(self):
        r = self.parse("$50 KFC dinner")
        self.assertTrue(r["ok"])
        self.assertEqual((r["amount"], r["category"], r["note"]), (5000, "main", "KFC dinner"))
        self.assertIsNone(r["typo"])

    def test_amount_anywhere_with_cents_and_chinese(self):
        self.assertEqual(self.parse("HK$12.5 coffee")["amount"], 1250)
        r = self.parse("奶茶 28")
        self.assertEqual((r["amount"], r["category"]), (2800, "snack"))

    def test_keywords_pick_the_fund(self):
        self.assertEqual(self.parse("movie ticket 95")["category"], "experience")
        self.assertEqual(self.parse("$3200 rent")["category"], "fixed")
        self.assertEqual(self.parse("textbook 320")["category"], "development")

    def test_suspected_typo_suggests_a_fix(self):
        r = self.parse("KFC dinner $500")
        self.assertIsNotNone(r["typo"])
        self.assertEqual(r["typo"]["suggestion"], 5000)
        self.assertIsNotNone(self.parse("lunch 900")["typo"])  # no chain: over the usual for Main meals

    def test_no_amount_is_an_error(self):
        self.assertFalse(self.parse("lunch")["ok"])
        self.assertFalse(self.parse("")["ok"])

    def test_unknown_words_are_not_confident(self):
        r = self.parse("$40 something")
        self.assertFalse(r["confident"])

    def test_cha_chaan_teng_is_a_meal_not_a_drink(self):
        self.assertEqual(self.parse("示範茶餐廳 35")["category"], "main")


# What the offline OCR (tesseract.js in the browser) read from the six sample receipt images in
# frontend/img/samples, captured once from the real app. OCR can misread (see the cha chaan teng
# subtotal), which is why the app only pre-fills Add payment and the student confirms.
OCR_MCD = "SAMPLE RECEIPT - NOT A REAL RECEIPT\nMcDonald's\nSample branch, Clear Water Bay\nBig Mac Extra Value Meal 44.50\nTOTAL HK$44.50\nOctopus 44.50\nSample - amounts for the demo only"
OCR_TAMJAI = 'SAMPLE RECEIPT - NOT A REAL RECEIPT\nTamJai SamGor\nSample branch, Sai Kung\nMixian, 2 toppings 43.00\nIced lemon tea 6.00\nTOTAL HK$49.00\nCash 50.00\nChange 1.00\nSample - amounts for the demo only'
OCR_BOOKSTORE = 'SAMPLE RECEIPT - NOT A REAL RECEIPT\nHKUST Bookstore\nSample, Academic Building\nLinear Algebra textbook 320.00\nTOTAL HK$320.00\nCard 320.00\nSample - amounts for the demo only'
OCR_NOODLE = 'SAMPLE RECEIPT - FICTIONAL SHOP\nLUCKY BOWL NOODLE BAR\nDemo Road, Kowloon Tong\nBeef brisket noodles 38.00\nLemon tea 8.00\nSubtotal 46.00\nService charge 10% 4.60\nTOTAL HK$50.60\nCash 60.00\nChange 9.40\nThank you - sample amounts only'
OCR_CHA_CHAAN_TENG = 'SAMPLE RECEIPT 示範 收據\n示範 茶 餐 廳 Demo Cafe\n餐 蛋 麵 Noodles $39.99\n凍 枋 茶 Iced lemon tea $5.99\n小 計 subtotal $35.99\n合計 TOTAL $35.00\n八 達 通 Octopus $35.99\n餘額 Remaining $82.40\n多 謝 光臨 - sample only'
OCR_HOTPOT = 'SAMPLE RECEIPT - FICTIONAL SHOP\nEXAMPLE HOTPOT HOUSE\nTable 7 - 2 guests\nHotpot set for 2 136.00\nSoft drinks x2 16.00\nSubtotal 152.00\nService charge 10% 15.20\nGRAND TOTAL HKD 167.20\nVISA 李冰冰 半 冰冰 冰冰 半 半 本 主 4242 167.29\nSample amounts only'

OCR_FUSION = ("|\nfusion\nHKUST TEL:27191463\n154715 能量果凍二自葡萄味  1 $15.90\n5% OFF (SU-SCO)            -$0.80\n"
              "1 小計                         $15.10\nMASTER                                $15.10\n找                            $0.00\n"
              "$15.10\nGP,MASTERCARD\nT MAST\n收銀員姓名; SCO1\n店繃'00463 收銀機:026。 收銀員:9991\n"
              "單旦#;0141       25/11/26 15:25:28\n如需退換或退款,請於\n收據正本到本店。不適\n金及指定產品 , 詳情請\n"
              "百佳超級市場(香\n莖天內帶同貨品,\na\n參閱網站PNS ,hk。\n港)有限公司")


class ReceiptPipeline(unittest.TestCase):
    """OCR text -> receipt.parse_receipt (total, merchant) -> assistant.parse_entry (fund, reason, typo)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = Service(open_books(Path(self._tmp.name)), FixedClock("2027-03-03"))

    def scan(self, text):
        return self.svc.scan_receipt(text)

    def test_six_samples(self):
        cases = (
            (OCR_MCD, 4450, "McDonald's", "main", "McDonald's is a food chain"),
            (OCR_TAMJAI, 4900, "TamJai SamGor", "main", "TamJai SamGor is a food chain"),
            (OCR_BOOKSTORE, 32000, "HKUST Bookstore", "development", '"book"'),
            (OCR_NOODLE, 5060, "LUCKY BOWL NOODLE BAR", "main", '"noodle"'),
            (OCR_CHA_CHAAN_TENG, 3500, "示範茶餐廳 Demo Cafe", "main", '"茶餐廳"'),
            (OCR_HOTPOT, 16720, "EXAMPLE HOTPOT HOUSE", "main", '"hotpot"'),
        )
        for text, amount, merchant, fund, reason in cases:
            with self.subTest(merchant=merchant):
                r = self.scan(text)
                self.assertTrue(r["found"])
                self.assertEqual((r["amount"], r["merchant"]), (amount, merchant))
                entry = r["entry"]
                self.assertEqual((entry["amount"], entry["category"], entry["reason"]), (amount, fund, reason))
                self.assertEqual(entry["note"], merchant)
                self.assertIsNone(entry["typo"])

    def test_fusion_receipt_photo(self):
        # What the browser reader read from frontend/img/samples/receipt-fusion.png (a real fusion
        # receipt, card and reference numbers covered): no TOTAL line, the subtotal is sure because
        # the MASTER card line shows the same amount.
        r = self.scan(OCR_FUSION)
        self.assertTrue(r["found"])
        self.assertFalse(r["guess"])
        self.assertEqual((r["amount"], r["merchant"]), (1510, "fusion"))
        self.assertEqual((r["entry"]["category"], r["entry"]["reason"]), ("main", "no clear clue, so Main meals"))

    def test_typo_check_runs_on_a_receipt(self):
        r = self.scan(OCR_MCD.replace("TOTAL HK$44.50", "TOTAL HK$445.00"))
        self.assertEqual(r["amount"], 44500)
        self.assertIsNotNone(r["entry"]["typo"])
        self.assertEqual(r["entry"]["typo"]["suggestion"], 4450)

    def test_no_total_means_no_entry(self):
        r = self.scan("SAMPLE RECEIPT\nSample Shop\nThank you")
        self.assertFalse(r["found"])
        self.assertIsNone(r["entry"])

    def test_scan_never_saves(self):
        self.svc.set_mode("demo")
        before = self.svc.get_state()["payments"]
        self.scan(OCR_TAMJAI)
        self.assertEqual(self.svc.get_state()["payments"], before)


class Insights(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = Service(open_books(Path(self._tmp.name)), FixedClock("2027-03-03"))

    def test_demo_week_warns_about_snacks(self):
        self.svc.set_mode("demo")
        ins = self.svc.insights()
        self.assertTrue(ins["ready"])
        self.assertEqual([w["fund"] for w in ins["warnings"]], ["snack"])
        self.assertEqual(ins["total"], 15000)
        self.assertEqual(sum(row["spent"] for row in ins["breakdown"]), 15000)

    def test_state_carries_insights_for_the_current_week_only(self):
        self.svc.set_mode("demo")
        self.assertIsNotNone(self.svc.get_state()["insights"])

    def test_no_budget_means_not_ready(self):
        self.assertFalse(self.svc.insights()["ready"])
