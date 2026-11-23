"""Finding the total in OCR text from a receipt (receipt.parse_receipt)."""

import unittest

from ssust.receipt import MAX_TEXT, parse_receipt


class Totals(unittest.TestCase):
    def check(self, text, cents, merchant=None):
        result = parse_receipt(text)
        self.assertTrue(result["found"], result)
        self.assertEqual(result["amount"], cents)
        self.assertIs(type(result["amount"]), int)
        if merchant is not None:
            self.assertEqual(result["merchant"], merchant)
        return result

    def test_simple_english(self):
        text = "SAMPLE NOODLE BAR\n1 Beef noodles 42.00\n1 Lemon tea 6.00\nTOTAL 48.00\nThank you"
        result = self.check(text, 4800, "SAMPLE NOODLE BAR")
        self.assertEqual(result["line"], "TOTAL 48.00")

    def test_subtotal_service_charge_and_total(self):
        text = ("Demo Cafe\nPasta 88.00\nSoup 20.00\nSubtotal 108.00\nService charge 10% 10.80\n"
                "Total HK$118.80\nCash 120.00\nChange 1.20")
        self.check(text, 11880, "Demo Cafe")

    def test_grand_total_after_total_last_wins(self):
        text = "Fictional Diner\nTotal 90.00\nTip 10.00\nGRAND TOTAL 100.00"
        self.check(text, 10000)

    def test_amount_due_with_hkd(self):
        self.check("Example Store\nItems 3\nAMOUNT DUE HKD 1,234.50\nVISA **** 4321", 123450)

    def test_traditional_chinese(self):
        text = "樣本茶餐廳\n餐蛋麵 $32\n凍檸茶 $6\n小計 $38\n合計 $38.00\n多謝光臨"
        self.check(text, 3800, "樣本茶餐廳")

    def test_chinese_total_words(self):
        for word in ("總數", "總計", "應付"):
            with self.subTest(word=word):
                self.check(f"示範小店\n{word}: HK$56.5", 5650)

    def test_mixed_language_receipt(self):
        text = "Sample Bakery 示範餅店\n菠蘿包 Pineapple bun 9.00\n蛋撻 Egg tart 2 x 8.00 16.00\n總數 TOTAL $25.00"
        self.check(text, 2500, "Sample Bakery 示範餅店")

    def test_octopus_style(self):
        text = ("SAMPLE CONVENIENCE\n12/11/2026 13:45\nOctopus No. 12345678(9)\nWater 7.50\nSandwich 22.50\n"
                "Total 30.00\n八達通付款 Octopus 30.00\nRemaining Value 餘額 $123.40")
        self.check(text, 3000)

    def test_total_on_the_next_line(self):
        self.check("Demo Kitchen\nTOTAL\n$ 64.00\nThank you", 6400)

    def test_dates_times_and_phone_numbers_are_ignored(self):
        text = "Sample Shop\nTel: 2345 6789\nDate 2026-11-12 Time 12:30\nTOTAL 2026-11-12 12:30 45.00"
        self.check(text, 4500, "Sample Shop")

    def test_plain_number_without_currency(self):
        self.check("Example Kiosk\nTotal 27", 2700)

    def test_cash_tendered_and_change_never_win(self):
        text = "Demo Bar\nTotal 52.00\nCash tendered 100.00\nChange 48.00"
        self.check(text, 5200)

    def test_card_number_on_the_total_line_is_ignored(self):
        self.check("Sample Mart\nTOTAL 88.80 CARD ************1234", 8880)

    def test_one_decimal_place(self):
        self.check("Sample Tea\nTotal $12.5", 1250)


class NothingFound(unittest.TestCase):
    def test_no_total_word(self):
        result = parse_receipt("Sample Shop\nItem 12.00\nItem 30.00")
        self.assertFalse(result["found"])
        self.assertIsNone(result["amount"])
        self.assertEqual(result["merchant"], "Sample Shop")

    def test_only_subtotal(self):
        self.assertFalse(parse_receipt("Shop\nSubtotal 40.00\n小計 40.00")["found"])

    def test_empty_and_garbage(self):
        for text in ("", "   \n  ", "@@@ ### ..."):
            with self.subTest(text=text):
                result = parse_receipt(text)
                self.assertFalse(result["found"])
                self.assertIsNone(result["merchant"])

    def test_zero_total_is_not_a_total(self):
        self.assertFalse(parse_receipt("Shop\nTotal 0.00")["found"])

    def test_text_too_long_is_refused(self):
        with self.assertRaises(ValueError):
            parse_receipt("x" * (MAX_TEXT + 1))

    def test_ocr_spaces_between_chinese_characters_are_removed(self):
        self.assertEqual(parse_receipt("示範 茶 餐 廳 Demo Cafe\nTotal 35")["merchant"], "示範茶餐廳 Demo Cafe")

    def test_merchant_skips_receipt_headers_and_is_short(self):
        result = parse_receipt("RECEIPT\n123\nA Very Long Sample Restaurant Name That Goes On And On\nTotal 10")
        self.assertEqual(result["merchant"], "A Very Long Sample Restaurant Name That")
        self.assertLessEqual(len(result["merchant"]), 40)


if __name__ == "__main__":
    unittest.main()
