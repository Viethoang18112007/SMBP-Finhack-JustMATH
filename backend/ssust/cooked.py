""""How cooked are you": a score from 0 to 100 built from three plain factors. Pure functions,
integer math, no I/O. Rules a person can check by hand, not a model.

    pace     0 to 50  projected 30 day spending as a percent of the 30 day budget (projection.py):
                      1 point per whole percent above 80% (80% or less: 0; 130% or more: 50)
    runout   0 to 30  10 points per fund that will not last until Sunday at this week's pace
                      (assistant.insights warnings)
    savings  0 to 20  share of this week's Long-term Savings already used to cover overspending:
                      used x 40 / savings (half of it used or more: 20)

Levels: Chill under 20, Fine under 40, Sweating under 60, Cooked under 80, Well done from 80.

The zero point: at the projected pace, the first day ahead (1 to 30) where cumulative spending
passes the cumulative budget (the budget pace line of the chart), shown as "You hit HK$0 around
day X". None when the pace stays under the budget for the next 30 days.
"""

from .money import hk

PACE_MAX, RUNOUT_MAX, SAVINGS_MAX = 50, 30, 20
PACE_FROM_PCT = 80
RUNOUT_EACH = 10
LEVELS = ((20, "chill", "Chill"), (40, "fine", "Fine"), (60, "sweating", "Sweating"),
          (80, "cooked", "Cooked"), (None, "well_done", "Well done"))


def pace_points(projected30, budget30):
    if projected30 is None or not budget30 or budget30 <= 0:
        return 0
    pct = projected30 * 100 // budget30
    return max(0, min(PACE_MAX, pct - PACE_FROM_PCT))


def runout_points(funds):
    return min(RUNOUT_MAX, RUNOUT_EACH * max(funds, 0))


def savings_points(used, savings):
    if savings <= 0 or used <= 0:
        return 0
    return min(SAVINGS_MAX, used * 40 // savings)


def level_for(score):
    """(level id, label) for a score from 0 to 100."""
    for bound, level, label in LEVELS:
        if bound is None or score < bound:
            return level, label
    raise AssertionError("unreachable")


def zero_day(proj):
    """{"day": k, "date": iso} for the first day ahead where projected cumulative spending passes the
    cumulative budget, or None. Exact integers: (total + avg k) x 7 > weekly x (days + k)."""
    if not proj or not proj.get("ready"):
        return None
    total = proj["real"][-1]["cents"]
    avg, weekly, days = proj["avgDaily"], proj["weekly"], proj["days"]
    for k, point in enumerate(proj["projected"], start=1):
        if (total + avg * k) * 7 > weekly * (days + k):
            return {"day": k, "date": point["date"]}
    return None


def cooked_score(opening, funds_now, proj, runout_funds):
    """The score, its level and its three factors. `runout_funds`: the funds (or "food") that will
    not last the week. Not ready without a budget for the week."""
    if opening is None or funds_now is None:
        return {"ready": False, "score": 0, "level": "chill", "label": "Chill", "factors": [], "zero": None}
    ready = bool(proj and proj.get("ready"))
    pace = pace_points(proj["projected30"], proj["budget30"]) if ready else 0
    if ready:
        pct = proj["projected30"] * 100 // proj["budget30"] if proj["budget30"] else 0
        pace_detail = (f"At this pace: {hk(proj['projected30'])} in 30 days, {pct}% of your "
                       f"{hk(proj['budget30'])} budget (points start above {PACE_FROM_PCT}%).")
    else:
        pace_detail = "Not enough days yet for a 30 day projection: 0 points."
    n = len(runout_funds)
    runout = runout_points(n)
    runout_detail = (f"{n} fund{'s' if n != 1 else ''} will not last until Sunday at this pace "
                     f"({RUNOUT_EACH} points each)." if n else "Every fund lasts until Sunday at this pace.")
    used = max(opening["savings"] - funds_now["savings"], 0)
    savings = savings_points(used, opening["savings"])
    savings_detail = (f"{hk(used)} of {hk(opening['savings'])} Long-term Savings already used this week."
                      if used else "Long-term Savings untouched this week.")
    score = pace + runout + savings
    level, label = level_for(score)
    return {
        "ready": True,
        "score": score,
        "level": level,
        "label": label,
        "factors": [
            {"id": "pace", "name": "Spending pace", "points": pace, "max": PACE_MAX, "detail": pace_detail},
            {"id": "runout", "name": "Funds running out", "points": runout, "max": RUNOUT_MAX, "detail": runout_detail},
            {"id": "savings", "name": "Savings used", "points": savings, "max": SAVINGS_MAX, "detail": savings_detail},
        ],
        "zero": zero_day(proj) if ready else None,
    }
