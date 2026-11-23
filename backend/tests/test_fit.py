import unittest

from ssust.fit import BANDS, FITS, fit_for, with_fit

HK = 100  # cents per HK$


class Bands(unittest.TestCase):
    def test_ranges_in_integer_cents(self):
        self.assertEqual(BANDS, {
            "cheap": (1, 50 * HK),
            "normal": (50 * HK + 1, 120 * HK),
            "expensive": (120 * HK + 1, None),
        })
        for low, high in BANDS.values():
            self.assertIs(type(low), int)
            self.assertTrue(high is None or type(high) is int)

    def test_three_states(self):
        self.assertEqual(FITS, ("fits", "tight", "over"))


class FitFor(unittest.TestCase):
    def check(self, remaining, cheap, normal, expensive):
        got = {band: fit_for(band, remaining) for band in ("cheap", "normal", "expensive")}
        self.assertEqual(got, {"cheap": cheap, "normal": normal, "expensive": expensive}, remaining)

    def test_exactly_hk50(self):
        self.check(5000, "fits", "over", "over")

    def test_hk50_and_one_cent(self):
        self.check(5001, "fits", "tight", "over")

    def test_exactly_hk120(self):
        self.check(12000, "fits", "fits", "over")

    def test_hk120_and_one_cent(self):
        self.check(12001, "fits", "fits", "tight")

    def test_one_cent_under_hk50(self):
        self.check(4999, "tight", "over", "over")

    def test_expensive_is_at_best_tight(self):
        self.check(10_000_000, "fits", "fits", "tight")

    def test_nothing_left(self):
        self.check(0, "over", "over", "over")

    def test_over_spent_today(self):
        self.check(-500, "over", "over", "over")

    def test_one_cent_left(self):
        self.check(1, "tight", "over", "over")

    def test_no_fit_without_a_band_or_a_budget(self):
        for band in ("unknown", None, "", "free"):
            with self.subTest(band=band):
                self.assertIsNone(fit_for(band, 5000))
        self.assertIsNone(fit_for("cheap", None))


class WithFit(unittest.TestCase):
    PLACES = [
        {"id": "a", "price": "expensive", "distanceKm": 0.1},
        {"id": "b", "price": "unknown", "distanceKm": 0.2},
        {"id": "c", "price": "normal", "distanceKm": 0.3},
        {"id": "d", "price": "cheap", "distanceKm": 0.4},
        {"id": "e", "price": "normal", "distanceKm": 0.5},
        {"id": "f", "price": "cheap", "distanceKm": 0.6},
    ]

    def test_fits_first_then_tight_over_unknown_keeping_distance_order(self):
        got = with_fit(self.PLACES, 8000)
        self.assertEqual([(p["id"], p["fit"]) for p in got], [
            ("d", "fits"), ("f", "fits"), ("c", "tight"), ("e", "tight"), ("a", "over"), ("b", None),
        ])

    def test_input_is_not_changed(self):
        before = [dict(p) for p in self.PLACES]
        with_fit(self.PLACES, 8000)
        self.assertEqual(self.PLACES, before)

    def test_no_budget_keeps_the_order_and_fits_nothing(self):
        got = with_fit(self.PLACES, None)
        self.assertEqual([p["id"] for p in got], list("abcdef"))
        self.assertTrue(all(p["fit"] is None for p in got))


if __name__ == "__main__":
    unittest.main()
