import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

from ssust import dates, money
from ssust.dates import FixedClock, LiveClock, monday_of, week_dates


class MondayOf(unittest.TestCase):
    def test_every_day_of_a_week_maps_to_its_monday(self):
        days = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12",
                "2026-11-13", "2026-11-14", "2026-11-15"]
        for day in days:
            with self.subTest(day=day):
                self.assertEqual(monday_of(day), "2026-11-09")

    def test_next_monday_starts_a_new_week(self):
        self.assertEqual(monday_of("2026-11-16"), "2026-11-16")

    def test_month_boundary(self):
        # Sunday 1 November 2026 belongs to the week of Monday 26 October.
        self.assertEqual(monday_of("2026-11-01"), "2026-10-26")
        self.assertEqual(monday_of("2026-10-31"), "2026-10-26")

    def test_year_boundary(self):
        # Friday 1 January 2027 belongs to the week of Monday 28 December 2026.
        self.assertEqual(monday_of("2027-01-01"), "2026-12-28")
        self.assertEqual(monday_of("2027-01-03"), "2026-12-28")
        self.assertEqual(monday_of("2027-01-04"), "2027-01-04")

    def test_leap_day(self):
        # Thursday 29 February 2028.
        self.assertEqual(monday_of("2028-02-29"), "2028-02-28")
        self.assertEqual(monday_of("2028-03-05"), "2028-02-28")

    def test_bad_input_raises_value_error(self):
        for bad in ["", "2026-13-01", "2026-02-30", "11/11/2026", "2026-11-11T00:00", None, 20261111]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    monday_of(bad)


class WeekDates(unittest.TestCase):
    def test_seven_days_from_monday(self):
        self.assertEqual(week_dates("2026-11-09"), [
            "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12",
            "2026-11-13", "2026-11-14", "2026-11-15",
        ])

    def test_crosses_month_and_year(self):
        self.assertEqual(week_dates("2026-12-28"), [
            "2026-12-28", "2026-12-29", "2026-12-30", "2026-12-31",
            "2027-01-01", "2027-01-02", "2027-01-03",
        ])

    def test_rejects_a_day_that_is_not_a_monday(self):
        with self.assertRaises(ValueError):
            week_dates("2026-11-11")


class Clocks(unittest.TestCase):
    def test_fixed_clock_returns_its_day(self):
        clock = FixedClock("2026-11-11")
        self.assertEqual(clock.today(), "2026-11-11")
        self.assertEqual(clock.today(), "2026-11-11")

    def test_demo_clock_is_the_sample_day(self):
        clock = FixedClock(money.SAMPLE_TODAY)
        self.assertEqual(monday_of(clock.today()), money.SAMPLE_WEEK_START)

    def test_fixed_clock_rejects_bad_dates(self):
        for bad in ["", "2026-02-30", "tomorrow", None]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    FixedClock(bad)

    def test_live_clock_uses_the_hong_kong_date(self):
        # Changed in P0.6: live "today" is the Hong Kong date, not the computer's local date.
        def hk_today():
            return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()
        before = hk_today()
        today = LiveClock().today()
        after = hk_today()
        self.assertIn(today, {before, after})


def at_utc(*parts):
    moment = datetime(*parts, tzinfo=timezone.utc)
    return lambda: moment


class HongKongTime(unittest.TestCase):
    """P0.6: live dates and weeks follow Asia/Hong_Kong (UTC+8, no DST) on any computer."""

    def test_one_minute_before_and_after_midnight_in_hong_kong(self):
        self.assertEqual(LiveClock(now=at_utc(2026, 11, 11, 15, 59)).today(), "2026-11-11")  # 23:59 HK
        self.assertEqual(LiveClock(now=at_utc(2026, 11, 11, 16, 1)).today(), "2026-11-12")  # 00:01 HK

    def test_sunday_to_monday_week_rollover(self):
        sunday = LiveClock(now=at_utc(2026, 11, 15, 15, 59)).today()  # Sun 23:59 HK
        monday = LiveClock(now=at_utc(2026, 11, 15, 16, 1)).today()  # Mon 00:01 HK
        self.assertEqual((sunday, monday_of(sunday)), ("2026-11-15", "2026-11-09"))
        self.assertEqual((monday, monday_of(monday)), ("2026-11-16", "2026-11-16"))

    def test_other_offsets_are_converted(self):
        new_york = timezone(timedelta(hours=-5))
        moment = datetime(2026, 11, 11, 11, 30, tzinfo=new_york)  # 16:30 UTC, 00:30 HK next day
        self.assertEqual(LiveClock(now=lambda: moment).today(), "2026-11-12")

    def test_naive_now_is_refused(self):
        with self.assertRaises(ValueError):
            LiveClock(now=lambda: datetime(2026, 11, 11, 12, 0)).today()

    def test_fixed_offset_fallback_without_a_tz_database(self):
        import zoneinfo
        with mock.patch("zoneinfo.ZoneInfo", side_effect=zoneinfo.ZoneInfoNotFoundError("no tzdata")):
            tz = dates.hong_kong_tz()
        self.assertEqual(tz.utcoffset(None), timedelta(hours=8))
        clock = LiveClock(now=at_utc(2026, 11, 11, 16, 1), tz=tz)
        self.assertEqual(clock.today(), "2026-11-12")

    def test_zone_and_fallback_agree(self):
        for hour in (0, 8, 15, 16, 23):
            now = at_utc(2026, 6, 30, hour, 0)
            with self.subTest(hour=hour):
                self.assertEqual(LiveClock(now=now).today(), LiveClock(now=now, tz=dates.HK_FIXED).today())


if __name__ == "__main__":
    unittest.main()
