"""The "how cooked are you" score: integer, explainable, three factors, five levels."""

import tempfile
import unittest
from pathlib import Path

from ssust import cooked
from ssust.dates import FixedClock
from ssust.service import Service
from ssust.store import open_books

OPENING = {"main": 77000, "snack": 8000, "fixed": 20000, "experience": 12000, "development": 8000, "savings": 50000}
WEEKLY = 125000  # the five spending funds


def proj(projected30, weekly=WEEKLY, days=3, total=15000, avg=None):
    avg = projected30 // 30 if avg is None else avg
    return {"ready": True, "days": days, "real": [{"date": "2026-11-11", "cents": total}], "avgDaily": avg,
            "projected30": projected30, "budget30": (weekly * 30 + 3) // 7, "weekly": weekly,
            "projected": [{"date": f"2026-11-{12 + k:02d}" if k < 19 else f"2026-12-{k - 18:02d}", "cents": total + avg * (k + 1)}
                          for k in range(30)]}


class PaceFactor(unittest.TestCase):
    def test_boundaries(self):
        budget30 = (WEEKLY * 30 + 3) // 7
        for pct, points in ((0, 0), (80, 0), (81, 1), (105, 25), (130, 50), (200, 50)):
            with self.subTest(pct=pct):
                self.assertEqual(cooked.pace_points(-(-budget30 * pct // 100), budget30), points)

    def test_not_ready_counts_zero(self):
        self.assertEqual(cooked.pace_points(None, 0), 0)


class RunOutFactor(unittest.TestCase):
    def test_ten_points_per_fund_max_thirty(self):
        for n, points in ((0, 0), (1, 10), (2, 20), (3, 30), (4, 30)):
            with self.subTest(n=n):
                self.assertEqual(cooked.runout_points(n), points)


class SavingsFactor(unittest.TestCase):
    def test_share_of_savings_used(self):
        for used, points in ((0, 0), (1250, 1), (12500, 10), (25000, 20), (50000, 20)):
            with self.subTest(used=used):
                self.assertEqual(cooked.savings_points(used, 50000), points)

    def test_no_savings_set(self):
        self.assertEqual(cooked.savings_points(0, 0), 0)
        self.assertEqual(cooked.savings_points(-500, 50000), 0)


class Levels(unittest.TestCase):
    def test_level_boundaries(self):
        for score, level in ((0, "chill"), (19, "chill"), (20, "fine"), (39, "fine"), (40, "sweating"),
                             (59, "sweating"), (60, "cooked"), (79, "cooked"), (80, "well_done"), (100, "well_done")):
            with self.subTest(score=score):
                self.assertEqual(cooked.level_for(score)[0], level)

    def test_labels(self):
        self.assertEqual([label for _, label in (cooked.level_for(s) for s in (0, 20, 40, 60, 80))],
                         ["Chill", "Fine", "Sweating", "Cooked", "Well done"])


class ZeroDay(unittest.TestCase):
    def test_slow_pace_never_hits_zero(self):
        self.assertIsNone(cooked.zero_day(proj(150000)))

    def test_fast_pace_crosses_the_budget_line(self):
        # 3 days, HK$150 spent; HK$300 a day ahead against a budget pace of 125000 / 7 a day.
        p = proj(900000, avg=30000)
        zero = cooked.zero_day(p)
        # (15000 + 30000 k) * 7 > 125000 (3 + k)  ->  85000 k > 270000  ->  k = 4
        self.assertEqual(zero, {"day": 4, "date": p["projected"][3]["date"]})

    def test_not_ready(self):
        self.assertIsNone(cooked.zero_day({"ready": False}))


class Score(unittest.TestCase):
    def test_sum_of_three_factors(self):
        now = dict(OPENING, savings=37500)  # HK$125 of HK$500 savings used: 10 points
        budget30 = (WEEKLY * 30 + 3) // 7
        result = cooked.cooked_score(OPENING, now, proj(-(-budget30 * 110 // 100)), ["snack", "food"])
        self.assertEqual([f["points"] for f in result["factors"]], [30, 20, 10])
        self.assertEqual([f["max"] for f in result["factors"]], [50, 30, 20])
        self.assertEqual(result["score"], 60)
        self.assertEqual((result["level"], result["label"]), ("cooked", "Cooked"))
        for f in result["factors"]:
            self.assertIsInstance(f["points"], int)
            self.assertTrue(f["detail"])

    def test_no_budget_is_not_ready(self):
        self.assertFalse(cooked.cooked_score(None, None, {"ready": False}, [])["ready"])

    def test_projection_not_ready_still_scores_the_other_factors(self):
        result = cooked.cooked_score(OPENING, OPENING, {"ready": False, "reason": "few_days"}, ["snack"])
        self.assertTrue(result["ready"])
        self.assertEqual(result["score"], 10)
        self.assertIsNone(result["zero"])


class InState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = Service(open_books(Path(self._tmp.name)), FixedClock("2027-03-03"))

    def test_demo_sample_week_is_chill(self):
        c = self.svc.set_mode("demo")["cooked"]
        self.assertTrue(c["ready"])
        self.assertEqual(c["score"], 10)  # Snacks will not last the week: 10; pace 28% of budget: 0
        self.assertEqual(c["level"], "chill")
        self.assertIsNone(c["zero"])

    def test_fresh_live_is_not_ready(self):
        self.assertFalse(self.svc.get_state()["cooked"]["ready"])


class CookedDemoWeek(unittest.TestCase):
    """A third demo week for the video: the same budget, spent fast (a group dinner, a concert, a gift
    paid from Long-term Savings), so the curve is honestly red."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = Service(open_books(Path(self._tmp.name)), FixedClock("2027-03-03"))

    def test_scores_cooked_with_three_factors(self):
        state = self.svc.set_mode("demo", "cooked")
        self.assertEqual(state["scenario"], "cooked")
        self.assertEqual(state["projection"]["status"], "too_fast")
        c = state["cooked"]
        self.assertEqual([f["points"] for f in c["factors"]], [37, 30, 8])
        self.assertEqual((c["score"], c["level"], c["label"]), (75, "cooked", "Cooked"))
        self.assertEqual(c["zero"]["day"], 1)
        self.assertEqual(state["opening"], {"main": 77000, "snack": 8000, "fixed": 20000, "experience": 12000,
                                            "development": 8000, "savings": 50000})

    def test_the_three_weeks_go_up(self):
        scores = [self.svc.set_mode("demo", sc)["cooked"]["score"] for sc in ("sample", "over", "cooked")]
        self.assertEqual(scores, [10, 40, 75])
