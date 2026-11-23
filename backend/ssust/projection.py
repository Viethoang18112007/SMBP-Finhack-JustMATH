"""The 30 day spending projection. Pure functions, integer cents, no I/O.

From the payments that still count (voided ones left out):
- real: cumulative spending per day, from the first day with a payment to today (included);
- avgDaily: average spending per day over the last WINDOW days (or all days if fewer);
- projected: cumulative spending for the next DAYS_AHEAD days at that average;
- pace: the weekly spending budget / 7 per day. The spending budget is the five spending funds;
  Long-term Savings is left out, because it is not meant to be spent;
- status: projected 30 day spending compared with pace x 30, thresholds in STATUS_PCT.
Fewer than MIN_DAYS days of data: no projection.
"""

from datetime import date, timedelta

from .money import FUNDS, round_div

DAYS_AHEAD = 30
WINDOW = 14
MIN_DAYS = 2
# Projected 30 day spending as a percent of the 30 day budget: at most 90 is comfortable,
# at most 105 is on track, above that is spending too fast.
STATUS_PCT = {"comfortable": 90, "on_track": 105}
LABELS = {"comfortable": "Comfortable", "on_track": "On track", "too_fast": "Spending too fast"}
SPENDING_FUNDS = tuple(fund for fund in FUNDS if fund != "savings")


def _day(iso):
    return date.fromisoformat(iso)


def status_for(projected30, weekly):
    """Exact integer comparison of projected30 with pct% of weekly * 30 / 7."""
    for status in ("comfortable", "on_track"):
        if projected30 * 7 * 100 <= STATUS_PCT[status] * weekly * DAYS_AHEAD:
            return status
    return "too_fast"


def project(payments, today, opening):
    """The projection payload for `today` (ISO date). `opening`: this week's fund amounts."""
    counted = [p for p in payments if not p.get("voidedAt") and p["date"] <= today]
    if opening is None or any(opening.get(fund) is None for fund in FUNDS):
        return {"ready": False, "reason": "no_budget", "days": 0}
    if not counted:
        return {"ready": False, "reason": "few_days", "days": 0}
    first = min(p["date"] for p in counted)
    end = _day(today)
    days = (end - _day(first)).days + 1
    if days < MIN_DAYS:
        return {"ready": False, "reason": "few_days", "days": days}
    by_day = {}
    for p in counted:
        by_day[p["date"]] = by_day.get(p["date"], 0) + p["amount"]
    real = []
    total = 0
    for i in range(days):
        iso = (_day(first) + timedelta(days=i)).isoformat()
        total += by_day.get(iso, 0)
        real.append({"date": iso, "cents": total})
    window = min(days, WINDOW)
    window_start = (end - timedelta(days=window - 1)).isoformat()
    avg = round_div(sum(c for d, c in by_day.items() if d >= window_start), window)
    projected = [{"date": (end + timedelta(days=k)).isoformat(), "cents": total + avg * k}
                 for k in range(1, DAYS_AHEAD + 1)]
    weekly = sum(opening[fund] for fund in SPENDING_FUNDS)
    projected30 = avg * DAYS_AHEAD
    status = status_for(projected30, weekly)
    return {
        "ready": True,
        "days": days,
        "window": window,
        "real": real,
        "avgDaily": avg,
        "projected": projected,
        "pace": round_div(weekly, 7),
        "weekly": weekly,
        "projected30": projected30,
        "budget30": round_div(weekly * DAYS_AHEAD, 7),
        "status": status,
        "label": LABELS[status],
        "thresholds": dict(STATUS_PCT),
    }
