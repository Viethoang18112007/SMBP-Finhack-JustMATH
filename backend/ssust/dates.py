"""Dates and clocks. Days are ISO strings ("YYYY-MM-DD"); weeks run Monday to Sunday.

Live "today" is the date in Hong Kong (Asia/Hong_Kong), whatever the computer's
time zone. Without a time zone database (Windows without the tzdata package),
a fixed UTC+8 offset is used: Hong Kong has no daylight saving time, so it is exact.
"""

import re
from datetime import date, datetime, timedelta, timezone

_ISO_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def parse_day(text):
    """Return a date for a strict "YYYY-MM-DD" string, or raise ValueError."""
    if not isinstance(text, str) or not _ISO_DAY.fullmatch(text):
        raise ValueError("Expected a date like 2026-11-11.")
    return date.fromisoformat(text)


def monday_of(day):
    """The Monday that starts the week containing `day`."""
    value = parse_day(day)
    return (value - timedelta(days=value.weekday())).isoformat()


def week_dates(monday):
    """The seven days of the week starting on `monday`."""
    start = parse_day(monday)
    if start.weekday() != 0:
        raise ValueError("A week starts on a Monday.")
    return [(start + timedelta(days=i)).isoformat() for i in range(7)]


HK_FIXED = timezone(timedelta(hours=8), "HKT")


def hong_kong_tz():
    """Asia/Hong_Kong from the tz database, or the fixed UTC+8 offset when there is none."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Hong_Kong")
    except Exception:  # ImportError, ZoneInfoNotFoundError (no tz database)
        return HK_FIXED


HK_TZ = hong_kong_tz()


def _utc_now():
    return datetime.now(timezone.utc)


class LiveClock:
    """Today's date in Hong Kong. `now` (returns an aware datetime) is injectable for tests."""

    def __init__(self, now=None, tz=None):
        self._now = now or _utc_now
        self._tz = tz or HK_TZ

    def today(self):
        moment = self._now()
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("now() must return a time-zone-aware datetime.")
        return moment.astimezone(self._tz).date().isoformat()

    def hour(self):
        """The hour (0 to 23) in Hong Kong now, for the meals still to come today."""
        return self._now().astimezone(self._tz).hour


class FixedClock:
    """Always the same day (and hour, noon by default). Used by demo mode and by tests."""

    def __init__(self, day, hour=12):
        self._day = parse_day(day).isoformat()
        self._hour = hour

    def today(self):
        return self._day

    def hour(self):
        return self._hour
