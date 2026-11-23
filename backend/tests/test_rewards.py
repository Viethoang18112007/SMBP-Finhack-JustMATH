"""Rewards: the logging streak and its shape, last week's stars, badges and campus medals."""

import unittest

from ssust import money, rewards


def pay(date, amount, category="main", **taken):
    source = taken or {category: amount}
    return {"date": date, "amount": amount, "category": category,
            "from": {**money.empty_from(), **source}, "uncovered": 0}


OPENING = {"main": 50000, "snack": 10000, "fixed": 20000, "experience": 10000, "development": 10000, "savings": 20000}
SPENDING = 100000  # the five spending funds above


class Streak(unittest.TestCase):
    def test_no_payments(self):
        got = rewards.streak([], "2026-11-23")
        self.assertEqual(got["days"], 0)
        self.assertIsNone(got["shape"])
        self.assertEqual(got["next"], {"shape": "square", "name": "Square", "at": 1, "daysToGo": 1})

    def test_counts_back_from_today(self):
        got = rewards.streak(["2026-11-21", "2026-11-22", "2026-11-23"], "2026-11-23")
        self.assertEqual((got["days"], got["shape"], got["loggedToday"]), (3, "star", True))
        self.assertEqual(got["next"]["shape"], "diamond")
        self.assertEqual(got["next"]["daysToGo"], 4)

    def test_still_alive_until_today_ends(self):
        got = rewards.streak(["2026-11-21", "2026-11-22"], "2026-11-23")
        self.assertEqual((got["days"], got["loggedToday"]), (2, False))
        self.assertEqual(got["shape"], "square")

    def test_broken_streak(self):
        got = rewards.streak(["2026-11-20"], "2026-11-23")
        self.assertEqual(got["days"], 0)
        self.assertEqual(got["best"], 1)

    def test_shapes_change_at_each_level(self):
        days = [f"2026-10-{d:02d}" for d in range(1, 32)]
        expected = {1: "square", 2: "square", 3: "star", 6: "star", 7: "diamond", 13: "diamond",
                    14: "hexagon", 29: "hexagon", 30: "crown", 31: "crown"}
        for n, shape in expected.items():
            with self.subTest(days=n):
                got = rewards.streak(days[:n], days[n - 1])
                self.assertEqual((got["days"], got["shape"]), (n, shape))
        self.assertIsNone(rewards.streak(days, "2026-10-31")["next"])

    def test_best_run_and_future_dates_ignored(self):
        dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-10", "2026-11-30"]
        got = rewards.streak(dates + dates, "2026-11-10")
        self.assertEqual((got["days"], got["best"]), (1, 4))


class WeekStars(unittest.TestCase):
    def test_no_budget(self):
        self.assertIsNone(rewards.week_stars(None, []))
        self.assertIsNone(rewards.week_stars({fund: 0 for fund in money.FUNDS}, []))

    def stars(self, payments):
        return rewards.week_stars(OPENING, payments)["stars"]

    def test_five_stars_with_a_fifth_left_and_no_reallocation(self):
        self.assertEqual(self.stars([pay("2026-11-16", 80000)]), 5)

    def test_four_stars_with_a_tenth_left(self):
        self.assertEqual(self.stars([pay("2026-11-16", 85000)]), 4)

    def test_three_stars_when_money_is_left(self):
        got = rewards.week_stars(OPENING, [pay("2026-11-16", 95000)])
        self.assertEqual((got["stars"], got["left"], got["budget"]), (3, 5000, SPENDING))

    def test_a_reallocation_caps_at_three(self):
        moved = pay("2026-11-16", 20000, "snack", snack=10000, experience=10000)
        self.assertEqual(self.stars([moved]), 3)

    def test_two_stars_when_nothing_is_left(self):
        self.assertEqual(self.stars([pay("2026-11-16", SPENDING)]), 2)

    def test_two_stars_when_savings_covered(self):
        gift = pay("2026-11-16", 5000, "experience", savings=5000)
        self.assertEqual(self.stars([gift]), 2)

    def test_one_star_when_spending_had_no_cover(self):
        over = {**pay("2026-11-16", 9000), "uncovered": 1000}
        self.assertEqual(self.stars([over]), 1)

    def test_every_answer_explains_itself(self):
        for payments in ([], [pay("2026-11-16", SPENDING)], [{**pay("2026-11-16", 1), "uncovered": 1}]):
            with self.subTest(payments=payments):
                got = rewards.week_stars(OPENING, payments)
                self.assertIn(got["stars"], range(1, 6))
                self.assertIsInstance(got["why"], str)
                self.assertTrue(got["why"])


class Medals(unittest.TestCase):
    def test_levels(self):
        for count, medal in ((0, None), (2, None), (3, "bronze"), (6, "bronze"), (7, "silver"), (15, "gold"), (40, "gold")):
            with self.subTest(count=count):
                self.assertEqual(rewards.medal_for(count), medal)

    def test_one_row_per_campus(self):
        rows = rewards.medals({"hkbu": 4, "hkust": 0}, [("hkbu", "HKBU"), ("hkust", "HKUST")])
        self.assertEqual(rows[0], {"campus": "hkbu", "name": "HKBU", "count": 4, "medal": "bronze",
                                   "next": {"medal": "silver", "at": 7}})
        self.assertEqual(rows[1]["medal"], None)
        self.assertEqual(rows[1]["next"], {"medal": "bronze", "at": 3})
        self.assertIsNone(rewards.medals({"hkbu": 20}, [("hkbu", "HKBU")])[0]["next"])


class Badges(unittest.TestCase):
    def test_all_listed_and_none_earned_at_the_start(self):
        got = rewards.badges(payments=0, budget_weeks=0, best_streak=0, stars=[], savings=0, medals=[])
        self.assertEqual([b["id"] for b in got], [b[0] for b in rewards.BADGES])
        self.assertFalse(any(b["earned"] for b in got))
        for badge in got:
            self.assertTrue(badge["name"] and badge["how"])

    def test_each_badge_has_its_rule(self):
        got = rewards.badges(payments=1, budget_weeks=1, best_streak=7, stars=[3, 5], savings=50000,
                             medals=[{"medal": "bronze"}])
        self.assertTrue(all(b["earned"] for b in got))
        some = {b["id"]: b["earned"] for b in rewards.badges(payments=2, budget_weeks=1, best_streak=3, stars=[2],
                                                             savings=49999, medals=[{"medal": None}])}
        self.assertEqual(some, {"first_entry": True, "planner": True, "on_a_roll": True, "full_week": False,
                                "money_left": False, "five_stars": False, "saver": False, "smart_explorer": False})


if __name__ == "__main__":
    unittest.main()
