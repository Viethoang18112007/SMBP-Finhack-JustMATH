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
        result = self.check("Sample Shop\nBurger 48.00\nFries 8.00\nTotal Qty 3", 4800)
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


class HongKongRestaurant(unittest.TestCase):
    """A real dine-in receipt: "$" prices with one decimal, a thousands comma, a 10% service charge
    and the total printed big next to "Amount"."""

    check = Totals.check

    LINES = ("(#E7)\nCafe Boheme\nPhone: +852 9251 6870\nShop 8, G/F, Alto Residences,\n"
             "29 Tong Yin Street, Tseung Kwan O\nOrder Time: 2026-11-22 12:21:16\n"
             "Printing Time: 2026-11-22 13:32:10\nReceipt No.: 20261122122116E7\nServed By: Shirley\n"
             "Order No.: E7 [Dine-in]\nNumber of Patron: 5\n"
             "1 Apple Juice $38.0\n1 Aqua Panna 750ML $68.0\n1 Truffle & Camembert Pizza $178.0\n"
             "1 BBQ Pork Rib 1KG $388.0\n1 Seafood Linguine $178.0\n1 Marshmallow Banana Pizza $88.0\n")

    def test_amount_with_thousands_and_one_decimal(self):
        text = self.LINES + "Subtotal $938.0\nService Charge(10%) $93.8\nAmount $1,032.0\nThank You"
        result = self.check(text, 103200, "Cafe Boheme")
        self.assertFalse(result["guess"])
        self.assertEqual(result["line"], "Amount $1,032.0")

    def test_amount_on_the_next_line(self):
        text = self.LINES + "$938.0\nSubtotal\n$93.8\nService Charge(10%)\nAmount\n$1,032.0\nThank You"
        self.assertFalse(self.check(text, 103200)["guess"])

    def test_total_with_thousands_and_one_decimal(self):
        for line in ("TOTAL $1,032.0", "T0TAL 1,032.0", "TOTA1 HK$1,032.0", "Total 1,032.0"):
            with self.subTest(line=line):
                self.assertFalse(self.check(f"Sample Shop\nPizza $938.0\n{line}", 103200)["guess"])

    def test_one_decimal_split_by_spaces(self):
        for line in ("TOTAL 93 . 8", "TOTAL $93. 8", "TOTAL 1,032 .0"):
            with self.subTest(line=line):
                self.check(f"Sample Shop\n{line}", 103200 if "032" in line else 9380)

    def test_amount_misread_the_subtotal_is_a_best_guess(self):
        # The big "Amount" line misread: the subtotal is the weak fallback (never added to the service charge).
        text = self.LINES + "Subtotal $938.0\nService Charge(18%) $93.8\nAmount gol\nI"
        result = self.check(text, 93800)
        self.assertTrue(result["guess"])
        self.assertEqual(result["line"], "Subtotal $938.0")

    def test_subtotal_on_the_next_line_is_a_best_guess(self):
        result = self.check("Sample Cafe\nSubtotal\n$938.0\nService Charge(10%)\n$93.8", 93800)
        self.assertTrue(result["guess"])

    def test_a_total_wins_over_subtotal_and_service(self):
        result = self.check("Sample Cafe\nSubtotal 100.00\nService 10.00\nTotal 110.50", 11050)
        self.assertFalse(result["guess"])

    def test_most_frequent_price_with_one_decimal_is_a_guess(self):
        result = self.check(self.LINES + "Thank You", 17800)
        self.assertTrue(result["guess"])

    def test_what_the_phone_read_finds_nothing(self):
        # The left column only, as the iPhone read it: no price at all, so nothing is invented.
        text = ("HET)\ncafe  Boher\ne\nime: 202\n3 50261122122116E 7\nApple Juice\nAqua Panna 758ML\n"
                "r   e & Camembert Pizz\n) Pork Rlb 1KG\nfood Linguine\nMarshmallow Banana Pizza\nSubtotal\nService")
        result = parse_receipt(text)
        self.assertFalse(result["found"])
        self.assertIsNone(result["amount"])


class RealReceipts(unittest.TestCase):
    """Anonymised copies of real receipts that failed (no real card numbers, refs or phones)."""

    check = Totals.check

    FUSION = ("fusion\nHKUST\n124715 能量果凍-白葡萄味 1 $15.90\n5% OFF (SU-SCO) -$0.80\n1 小計 $15.10\n"
              "MASTER $15.10\n找續 $0.00\nGP.MASTERCARD $15.10\nAPP Label:DEBIT MASTERCARD\n25/11/26 15:25:28")
    BOHEME = ("Cafe Boheme\nOrder Time: 2026-11-22 12:21:16\nApple Juice $38.0\nAqua Panna 750ML $68.0\n"
              "Truffle & Camembert Pizza $178.0\nBBQ Pork Rib 1KG $388.0\nSeafood Linguine $178.0\n"
              "Marshmallow Banana Pizza $88.0\nSubtotal $938.0\nService Charge(10%) $93.8\nAmount $1,032.0")
    SEEN = ("HET)\ncafe  Boher\ne\nime: 202\n3 50261122122116E 7\nApple Juice\nAqua Panna 758ML\n"
            "r   e & Camembert Pizz\n) Pork Rlb 1KG\nfood Linguine\nMarshmallow Banana Pizza\nSubtotal\nService")

    def test_fusion_subtotal_confirmed_by_the_card_line(self):
        result = parse_receipt(self.FUSION)
        self.assertEqual((result["found"], result["amount"], result["guess"]), (True, 1510, False))
        self.assertIn("小計", result["line"])
        self.assertEqual(result["merchant"].lower(), "fusion")

    def test_fusion_without_the_subtotal_word_guesses_the_paid_amount(self):
        # 小計 misread: 15.10 is printed three times, 15.90 (before the discount) once.
        result = self.check(self.FUSION.replace("小計", "小言"), 1510)
        self.assertTrue(result["guess"])

    def test_cafe_boheme_amount_beats_the_subtotal(self):
        result = self.check(self.BOHEME, 103200, "Cafe Boheme")
        self.assertFalse(result["guess"])
        self.assertEqual(result["line"], "Amount $1,032.0")

    def test_subtotal_never_beats_amount_whatever_the_order(self):
        for text in ("Shop\nAmount $1,032.0\nSubtotal $938.0", "Shop\nSubtotal $938.0\nVISA $938.0\nAmount $1,032.0"):
            with self.subTest(text=text):
                self.assertEqual(self.check(text, 103200)["guess"], False)

    def test_what_the_reader_saw_has_no_amounts(self):
        result = parse_receipt(self.SEEN)
        self.assertFalse(result["found"])
        self.assertIsNone(result["amount"])
        self.assertEqual(result["reason"], "no_amounts")

    def test_cash_tendered_and_change(self):
        text = "Sample Deli\nSandwich $40.00\nCoffee $22.50\nTOTAL $62.50\nCASH TENDERED $100.00\nCHANGE $37.50"
        self.assertFalse(self.check(text, 6250, "Sample Deli")["guess"])

    def test_total_with_a_discount(self):
        text = "Sample Shop\nBurger $48.00\nCoupon -$10.00\nTOTAL $38.00\nVISA $38.00"
        result = self.check(text, 3800)
        self.assertFalse(result["guess"])
        self.assertEqual(result["line"], "TOTAL $38.00")


class Labels(unittest.TestCase):
    check = Totals.check

    def test_strong_labels(self):
        for word in ("TOTAL", "GRAND TOTAL", "AMOUNT DUE", "TOTAL DUE", "應付", "總計", "总计", "合計", "合计", "總額"):
            with self.subTest(word=word):
                result = self.check(f"Sample Shop\nItem $30.00\nItem $9.00\n{word} $39.00\nAmount $50.00", 3900)
                self.assertFalse(result["guess"])

    def test_payment_line_confirms_one_of_two_totals(self):
        # "TOTAL SAVED" is last, but the card paid the other one.
        self.assertFalse(self.check("Sample Shop\nTOTAL 48.00\nTOTAL SAVED 5.00\nVISA 48.00", 4800)["guess"])

    def test_subtotal_confirmed_by_a_payment_line_is_sure(self):
        for pay in ("MASTERCARD", "VISA", "AMEX", "UNIONPAY", "OCTOPUS", "八達通", "PAYME", "ALIPAY", "WECHAT PAY",
                    "信用卡", "扣賬卡", "EPS"):
            with self.subTest(pay=pay):
                text = f"Sample Shop\nItem $30.00\nItem $12.00\nSubtotal $42.00\n{pay} $42.00"
                self.assertFalse(self.check(text, 4200)["guess"])

    def test_subtotal_alone_is_a_guess(self):
        self.assertTrue(self.check("Sample Shop\nItem $30.00\nItem $12.00\n小計 $42.00", 4200)["guess"])


class Excluded(unittest.TestCase):
    check = Totals.check

    def test_cash_and_change_lines_never_count(self):
        for line in ("CASH $100.00", "現金 $100.00", "TENDERED $100.00", "CHANGE $100.00", "找續 $100.00",
                     "找贖 $100.00", "實收 $100.00"):
            with self.subTest(line=line):
                self.check(f"Sample Shop\nItem $20.00\nItem $8.00\n{line}", 2000)

    def test_negative_amounts_never_count(self):
        for line in ("Coupon -$50.00", "Coupon $-50.00", "Coupon -50.00", "Coupon - HK$50.00"):
            with self.subTest(line=line):
                self.check(f"Sample Shop\n{line}\nItem $12.00\nItem $8.00", 1200)

    def test_zero_amounts_never_count(self):
        self.check("Sample Shop\nItem $12.00\nItem $8.00\nRounding $0.00\nTOTAL $0.00", 1200)


class BestGuess(unittest.TestCase):
    check = Totals.check

    def test_ids_phones_dates_times_and_cards_are_not_amounts(self):
        text = ("Sample Shop\nTEL:27191463\n535389******2423\n25/11/26 15:25:28\nRef 4820031177\n"
                "Table 12\nTea $12.00\nBun $9.50")
        result = self.check(text, 1200)
        self.assertTrue(result["guess"])

    def test_the_amount_printed_most_often_wins(self):
        self.check("Sample Shop\nItem $5.00\nItem $12.00\nPaid $5.00", 500)

    def test_a_tie_goes_to_the_larger_amount(self):
        self.check("Sample Shop\nA $5.00\nB $7.00\nC $5.00\nD $7.00", 700)

    def test_all_once_the_largest(self):
        self.check("Sample Shop\nA $5.00\nB $17.50\nC $7.00", 1750)

    def test_a_single_price_is_not_enough(self):
        result = parse_receipt("Sample Shop\nBurger 48.00\nThank you")
        self.assertEqual((result["found"], result["reason"]), (False, "no_amounts"))

    def test_prices_all_excluded_is_no_total(self):
        result = parse_receipt("Sample Shop\nCash $100.00\nChange $37.50")
        self.assertEqual((result["found"], result["reason"]), (False, "no_total"))

    def test_plain_numbers_are_not_prices(self):
        self.assertEqual(parse_receipt("Sample Shop\nTable 12\nGuests 4\nShop 8")["reason"], "no_amounts")


class Formats(unittest.TestCase):
    check = Totals.check

    def test_number_formats(self):
        for amount, cents in (("$1,032.0", 103200), ("$938.0", 93800), ("1.032,00", 103200), ("HK$ 38", 3800),
                              ("38,00 $HK", 3800), ("$15.10", 1510), ("HKD 1,234", 123400), ("12.345,60", 1234560)):
            with self.subTest(amount=amount):
                self.assertFalse(self.check(f"Sample Shop\nTOTAL {amount}", cents)["guess"])

    def test_currency_marks_make_whole_numbers_prices(self):
        self.check("Sample Shop\nTea HK$ 38\nBun HK$ 12", 3800)
        self.check("Sample Shop\nTea 38,00 $HK\nBun 12,00 $HK", 3800)


class NothingFound(unittest.TestCase):
    def test_no_total_word_and_no_price(self):
        result = parse_receipt("Sample Shop\nThank you\nTable 12")
        self.assertFalse(result["found"])
        self.assertIsNone(result["amount"])
        self.assertEqual(result["merchant"], "Sample Shop")

    def test_only_subtotal_is_a_best_guess(self):
        result = parse_receipt("Shop\nSubtotal 40.00\n小計 40.00")
        self.assertEqual((result["found"], result["amount"], result["guess"]), (True, 4000, True))

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
