"""The 30 day spending projection: real cumulative spending, average, status thresholds."""

import unittest

from ssust import money
from ssust.projection import DAYS_AHEAD, MIN_DAYS, STATUS_PCT, WINDOW, project

WEEK = {fund: 0 for fund in money.FUNDS}


def pay(date, amount, category="main"):
    return {"date": date, "amount": amount, "category": category}


def opening(weekly_spend, savings=0):
    """Five spending funds that add up to `weekly_spend`, plus savings (left out of the pace)."""
    return {**WEEK, "main": weekly_spend, "savings": savings}


class Shape(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(DAYS_AHEAD, 30)
        self.assertEqual(WINDOW, 14)
        self.assertEqual(MIN_DAYS, 2)
        self.assertEqual(STATUS_PCT, {"comfortable": 90, "on_track": 105})

    def test_no_projection_without_two_days_of_data(self):
        self.assertFalse(project([], "2026-11-11", opening(70000))["ready"])
        one_day = project([pay("2026-11-11", 5000)], "2026-11-11", opening(70000))
        self.assertFalse(one_day["ready"])
        self.assertEqual(one_day["reason"], "few_days")
        self.assertEqual(one_day["days"], 1)

    def test_no_projection_without_a_budget(self):
        result = project([pay("2026-11-09", 5000)], "2026-11-11", {f: None for f in money.FUNDS})
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "no_budget")

    def test_zero_budget_is_not_a_division_by_zero(self):
        result = project([pay("2026-11-09", 5000)], "2026-11-11", opening(0))
        self.assertTrue(result["ready"])
        self.assertEqual(result["pace"], 0)
        self.assertEqual(result["status"], "too_fast")
        nothing = project([pay("2026-11-09", 0)], "2026-11-11", opening(0))
        self.assertEqual(nothing["status"], "comfortable")

    def test_real_cumulative_per_day_and_average(self):
        payments = [pay("2026-11-09", 6200), pay("2026-11-09", 1500, "snack"), pay("2026-11-10", 4800),
                    pay("2026-11-10", 2500, "snack")]
        result = project(payments, "2026-11-11", opening(70000, savings=50000))
        self.assertTrue(result["ready"])
        self.assertEqual(result["days"], 3)  # Monday to Wednesday, today included
        self.assertEqual(result["window"], 3)
        self.assertEqual([r["date"] for r in result["real"]], ["2026-11-09", "2026-11-10", "2026-11-11"])
        self.assertEqual([r["cents"] for r in result["real"]], [7700, 15000, 15000])
        self.assertEqual(result["avgDaily"], 5000)
        self.assertEqual(result["pace"], 10000)  # 70000 / 7, savings left out
        self.assertEqual(len(result["projected"]), DAYS_AHEAD)
        self.assertEqual(result["projected"][0], {"date": "2026-11-12", "cents": 20000})
        self.assertEqual(result["projected"][-1], {"date": "2026-12-11", "cents": 15000 + 30 * 5000})
        self.assertEqual(result["projected30"], 150000)
        self.assertEqual(result["budget30"], 300000)
        self.assertEqual(result["status"], "comfortable")
        for value in (result["avgDaily"], result["pace"], result["projected30"], result["budget30"]):
            self.assertIs(type(value), int)

    def test_average_uses_the_last_14_days_only(self):
        payments = [pay("2026-10-01", 1000000)] + [pay(f"2026-11-{d:02d}", 1400) for d in range(1, 15)]
        result = project(payments, "2026-11-14", opening(70000))
        self.assertEqual(result["window"], 14)
        self.assertEqual(result["avgDaily"], 1400)
        self.assertEqual(result["real"][-1]["cents"], 1000000 + 14 * 1400)

    def test_voided_payments_do_not_count(self):
        payments = [pay("2026-11-09", 5000), {**pay("2026-11-10", 99900), "voidedAt": "x"}]
        self.assertEqual(project(payments, "2026-11-10", opening(70000))["real"][-1]["cents"], 5000)


class Boundaries(unittest.TestCase):
    """Weekly spending budget 70000 -> 30 day budget 300000. Two days of 7 * x cents give avg x."""

    def status_for_avg(self, avg):
        # avg cents a day over a 2 day window: day one pays 2 * avg, day two nothing.
        return project([pay("2026-11-10", 2 * avg)], "2026-11-11", opening(70000))

    def test_comfortable_up_to_90_percent(self):
        result = self.status_for_avg(9000)  # 30 * 9000 = 270000 = 90% of 300000
        self.assertEqual(result["projected30"], 270000)
        self.assertEqual((result["status"], result["label"]), ("comfortable", "Comfortable"))
        self.assertEqual(self.status_for_avg(9001)["status"], "on_track")

    def test_on_track_up_to_105_percent(self):
        result = self.status_for_avg(10500)  # 315000 = 105%
        self.assertEqual((result["status"], result["label"]), ("on_track", "On track"))
        too_fast = self.status_for_avg(10501)
        self.assertEqual((too_fast["status"], too_fast["label"]), ("too_fast", "Spending too fast"))

    def test_exact_with_a_pace_that_does_not_divide_by_7(self):
        # 10000 a week: 30 day budget is 300000 / 7 = 42857.14...; 90% is 38571.43.
        week = opening(10000)
        ok = project([pay("2026-11-10", 2 * 1285)], "2026-11-11", week)  # 30 * 1285 = 38550
        self.assertEqual(ok["status"], "comfortable")
        over = project([pay("2026-11-10", 2 * 1286)], "2026-11-11", week)  # 38580 > 38571.43
        self.assertEqual(over["status"], "on_track")


if __name__ == "__main__":
    unittest.main()
