"""Characterization tests for input parsing: they pin the current behaviour."""

import unittest
from ssust.validate import MAX_CENTS, clean_note, parse_amount


class ParseAmount(unittest.TestCase):
    def test_plain_and_decimal_amounts(self):
        self.assertEqual(parse_amount("48"), 4800)
        self.assertEqual(parse_amount("48.5"), 4850)
        self.assertEqual(parse_amount("48.05"), 4805)
        self.assertEqual(parse_amount("5."), 500)
        self.assertEqual(parse_amount(" 48 "), 4800)

    def test_hk_dollar_prefix(self):
        self.assertEqual(parse_amount("HK$48"), 4800)
        self.assertEqual(parse_amount("hk$48"), 4800)
        self.assertEqual(parse_amount("HK$ 48"), 4800)

    def test_commas_are_ignored(self):
        self.assertEqual(parse_amount("1,234.50"), 123450)
        self.assertEqual(parse_amount("HK$1,234"), 123400)

    def test_three_decimals_are_rejected(self):
        self.assertIsNone(parse_amount("1.234"))
        self.assertIsNone(parse_amount("0.001"))

    def test_zero_is_rejected(self):
        self.assertIsNone(parse_amount("0"))
        self.assertIsNone(parse_amount("0.00"))
        self.assertEqual(parse_amount("0.01"), 1)

    def test_max_limit(self):
        self.assertEqual(MAX_CENTS, 100_000_000)
        self.assertEqual(parse_amount("1000000"), MAX_CENTS)
        self.assertEqual(parse_amount("1,000,000.00"), MAX_CENTS)
        self.assertIsNone(parse_amount("1000000.01"))

    def test_malformed_text_is_rejected(self):
        for raw in ("", "   ", "HK$", ".5", "-5", "+5", "1e3", "1.2.3", "abc", "4 8", "1.x"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_non_strings_are_rejected(self):
        for raw in (48, 48.0, None, True, ["48"], {"amount": "48"}):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_only_ascii_digits_are_accepted(self):
        # Finding M2-1 (fixed): other scripts' digits are rejected.
        for raw in ("١٢", "４８", "1.٥", "١٢.50"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_superscript_digits_are_rejected(self):
        # Finding M2-2 (fixed): returns None instead of raising.
        for raw in ("²", "1.²", "²5", "①"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))


class CleanNote(unittest.TestCase):
    def test_none_becomes_empty(self):
        self.assertEqual(clean_note(None), "")

    def test_angle_brackets_are_removed(self):
        self.assertEqual(clean_note("<b>hi</b>"), "bhi/b")
        self.assertEqual(clean_note("<script>"), "script")

    def test_control_characters_are_removed(self):
        self.assertEqual(clean_note("a\x00b\tc\nd\re\x7f"), "abcde")
        self.assertEqual(clean_note("a​b"), "ab")  # zero-width space

    def test_other_text_is_kept(self):
        self.assertEqual(clean_note("  lunch & tea  "), "lunch & tea")
        self.assertEqual(clean_note("茶餐廳"), "茶餐廳")

    def test_forty_character_cap(self):
        self.assertEqual(clean_note("a" * 40), "a" * 40)
        self.assertEqual(clean_note("a" * 41), "a" * 40)
        self.assertEqual(clean_note("  " + "a" * 40 + "  "), "a" * 40)

    def test_no_trailing_space_after_cut(self):
        # Finding M2-3 (fixed): the result is stripped again after the cut.
        self.assertEqual(clean_note("a" * 39 + " b"), "a" * 39)
        self.assertEqual(clean_note("a" * 38 + "   b"), "a" * 38)

    def test_non_text_raises(self):
        for raw in (5, 4.5, ["a"], {"a": 1}, b"note"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    clean_note(raw)


if __name__ == "__main__":
    unittest.main()


class AmountFormats(unittest.TestCase):
    """P0.2: payments are strictly positive; funds may be 0; commas only group thousands."""

    def test_dot_decimals(self):
        self.assertEqual(parse_amount("12.34"), 1234)
        self.assertEqual(parse_amount("12.3"), 1230)
        self.assertIsNone(parse_amount("12.345"))

    def test_comma_as_decimal_mark_is_rejected(self):
        # "12,50" must never become HK$1,250.
        for raw in ("12,50", "12,5", "1,2345", ",5", "1,,000", "1,000,00", "12,"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_comma_thousands_are_accepted(self):
        self.assertEqual(parse_amount("1,234"), 123400)
        self.assertEqual(parse_amount("12,345.67"), 1234567)

    def test_payment_amounts_are_strictly_positive(self):
        for raw in ("0", "0.00", "-1", "-0.01", "HK$0"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_huge_and_non_numeric(self):
        for raw in ("99999999999999999999", "1000000.01", "NaN", "Infinity", "1e9", "twelve"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw))

    def test_funds_may_be_zero(self):
        self.assertEqual(parse_amount("0", allow_zero=True), 0)
        self.assertEqual(parse_amount("0.00", allow_zero=True), 0)
        self.assertEqual(parse_amount("HK$0", allow_zero=True), 0)
        self.assertEqual(parse_amount("12.34", allow_zero=True), 1234)
        for raw in ("-1", "", "12,50", "1000000.01"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_amount(raw, allow_zero=True))
