"""The map compares one meal with one meal's share of today's food money, not the whole day."""

import unittest
from datetime import datetime, timezone

from ssust import fit
from ssust.dates import FixedClock, LiveClock


class MealsLeft(unittest.TestCase):
    def test_by_hong_kong_hour(self):
        for hour, meals in ((0, 3), (7, 3), (10, 3), (11, 2), (15, 2), (16, 1), (23, 1)):
            with self.subTest(hour=hour):
                self.assertEqual(fit.meals_left(hour), meals)

    def test_per_meal(self):
        self.assertIsNone(fit.per_meal(None, 2))
        self.assertEqual(fit.per_meal(14000, 2), 7000)
        self.assertEqual(fit.per_meal(10000, 3), 3333)
        self.assertEqual(fit.per_meal(0, 3), 0)
        self.assertEqual(fit.per_meal(-500, 2), -500)  # already over: nothing to share


class ClockHour(unittest.TestCase):
    def test_live_hour_is_hong_kong_time(self):
        clock = LiveClock(now=lambda: datetime(2026, 11, 23, 2, 30, tzinfo=timezone.utc))
        self.assertEqual((clock.today(), clock.hour()), ("2026-11-23", 10))

    def test_fixed_clock_is_noon_by_default(self):
        self.assertEqual(FixedClock("2026-11-11").hour(), 12)
        self.assertEqual(FixedClock("2026-11-11", hour=8).hour(), 8)


if __name__ == "__main__":
    unittest.main()
