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


class OcrNoise(Totals):
    """What a phone camera really gives: misread letters, split decimals, columns on two lines."""

    def test_total_read_with_a_zero_or_a_one(self):
        for word in ("T0TAL", "TOTA1", "TOTAI", "T0TA L", "Tota1"):
            with self.subTest(word=word):
                self.assertFalse(self.check(f"Sample Shop\nBurger 40.00\n{word} 48.00", 4800)["guess"])

    def test_decimal_comma_or_space(self):
        for amount in ("48,00", "48. 00", "48 .00", "HK$ 48 . 00"):
            with self.subTest(amount=amount):
                self.check(f"Sample Shop\nTOTAL {amount}", 4800)

    def test_amount_two_lines_after_the_total_word(self):
        self.check("Sample Shop\nTOTAL\nHKD\n48.00\nThank you", 4800)

    def test_misread_subtotal_never_wins(self):
        self.check("Sample Shop\nSUBT0TAL 40.00\nService 4.00\nT0TAL 44.00", 4400)

    def test_total_quantity_is_not_a_total(self):
        result = self.check("Sample Shop\nBurger 48.00\nTotal Qty 3", 4800)
        self.assertTrue(result["guess"])

    def test_best_guess_is_the_largest_price(self):
        result = self.check("Sample Shop\nItem 12.00\nItem 30.00\nVISA 42.00\nCash 50.00\nChange 8.00", 4200)
        self.assertTrue(result["guess"])
        self.assertEqual(result["line"], "VISA 42.00")

    def test_a_real_total_is_not_a_guess(self):
        self.assertFalse(self.check("Sample Shop\nTOTAL 48.00", 4800)["guess"])


class AmountInsteadOfTotal(Totals):
    """Some receipts print AMOUNT (or AMT, 金額, Montant) where others print TOTAL."""

    def test_amount_line(self):
        for line in ("AMOUNT 48.00", "Amount: HK$48.00", "AM0UNT 48.00", "Amt 48.00", "AMOUNT HKD\n48.00",
                     "金額 $48.00", "Montant 48,00", "Amount payable 48.00"):
            with self.subTest(line=line):
                self.assertFalse(self.check(f"Sample Shop\nBurger 40.00\nFries 8.00\n{line}", 4800)["guess"])

    def test_amount_column_header_is_not_the_total(self):
        text = "Sample Shop\nItem     Qty   Amount\nBurger   1     40.00\nFries    1     8.00\nAmount   48.00"
        self.check(text, 4800)

    def test_a_total_line_wins_over_amount_lines(self):
        self.check("Sample Shop\nTOTAL 48.00\nAmount paid 50.00", 4800)
        self.check("Sample Shop\nAmount 40.00\nService 4.80\nTotal 44.80", 4480)

    def test_amount_tendered_never_counts(self):
        result = self.check("Sample Shop\nBurger 48.00\nAmount tendered 100.00", 4800)
        self.assertTrue(result["guess"])


class NothingFound(unittest.TestCase):
    def test_no_total_word_and_no_price(self):
        result = parse_receipt("Sample Shop\nThank you\nTable 12")
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
