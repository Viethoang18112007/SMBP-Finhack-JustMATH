"""SSUST money rules, in cents.

Five funds, from the ZUNO framework: Main meals, Snacks, Fixed Bills,
Experience, Development, and Long-term Savings.
Today's food line is fixed in the morning:
food left at the start of today, divided by the days left, including today.
A gap is covered in this order: Snacks, then Experience, then Development,
then Long-term Savings (a reallocation between the student's own funds: no money
moves anywhere). Fixed Bills never uses another fund.

Experience and Development are the flexible funds: they can cover a food day
that runs out, and whatever is left in them when the week ends moves to
Long-term Savings (week_close).
"""

import math

from .dates import week_dates

FUNDS = ("main", "snack", "fixed", "experience", "development", "savings")
CATEGORIES = ("main", "snack", "fixed", "experience", "development")
FOOD = frozenset({"main", "snack"})
FLEX = "flex"  # the cover choice that reallocates from Experience, then Development
FLEX_FUNDS = ("experience", "development")  # the flexible funds

# The suggested split of a weekly budget, in whole percent (sums to 100), and the lowest
# percent we suggest for a fund (a warning only: the student decides). A starting point
# for a student who eats out most days; every number is editable before the week starts.
SUGGESTED_SPLIT = {
    "main": 40,
    "snack": 5,
    "fixed": 15,
    "experience": 10,
    "development": 10,
    "savings": 20,
}
MIN_SPLIT = {
    "main": 25,
    "snack": 0,
    "fixed": 0,
    "experience": 0,
    "development": 0,
    "savings": 10,
}
SAMPLE_WEEK_START = "2026-11-09"
SAMPLE_TODAY = "2026-11-11"

SAMPLE_OPENING = {
    "main": 77000,
    "snack": 8000,
    "fixed": 20000,
    "experience": 12000,
    "development": 8000,
    "savings": 50000,
}


def js_round(value):
    # Same as JavaScript Math.round: halves go towards +infinity. floor(v + 1/2) == (floor(2v) + 1) // 2.
    return (math.floor(value * 2) + 1) // 2


def round_div(numerator, denominator):
    """numerator / denominator rounded like js_round, in integers only (denominator > 0)."""
    return (2 * numerator + denominator) // (2 * denominator)


FUND_NAMES = {
    "main": "Main meals",
    "snack": "Snacks",
    "fixed": "Fixed Bills",
    "experience": "Experience",
    "development": "Development",
    "savings": "Long-term Savings",
}


def hk(cents):
    """HK$ text for integer cents, the same as the frontend's hk(): HK$1,234 or HK$12.34."""
    sign = "-" if cents < 0 else ""
    dollars, rest = divmod(abs(cents), 100)
    return f"{sign}HK${dollars:,}" + (f".{rest:02d}" if rest else "")


def spent_by_fund(payments):
    """Cents taken from each fund by `payments` (reallocated amounts count for the fund they came from)."""
    return {fund: used(payments, fund) for fund in FUNDS}


def empty_from():
    return {fund: 0 for fund in FUNDS}


def sample_payments():
    return [
        {"id": "m1", "date": "2026-11-09", "amount": 6200, "category": "main", "note": "canteen", "from": {**empty_from(), "main": 6200}},
        {"id": "m2", "date": "2026-11-09", "amount": 1500, "category": "snack", "note": "tea", "from": {**empty_from(), "snack": 1500}},
        {"id": "m3", "date": "2026-11-10", "amount": 4800, "category": "main", "note": "lunch", "from": {**empty_from(), "main": 4800}},
        {"id": "m4", "date": "2026-11-10", "amount": 2500, "category": "snack", "note": "coffee", "from": {**empty_from(), "snack": 2500}},
    ]


def make_state(mode):
    base = {"mode": mode, "weekStart": SAMPLE_WEEK_START, "today": SAMPLE_TODAY}
    if mode == "empty":
        return {**base, "opening": {fund: None for fund in FUNDS}, "payments": []}
    if mode == "over":
        return {
            **base,
            "opening": {**SAMPLE_OPENING, "main": 11000, "snack": 4000, "experience": 0, "development": 0},
            "payments": sample_payments(),
        }
    if mode == "cooked":
        return {**base, "opening": dict(SAMPLE_OPENING), "payments": cooked_payments()}
    return {**base, "mode": "sample", "opening": dict(SAMPLE_OPENING), "payments": sample_payments()}


def cooked_payments():
    """The sample week spent fast: a group dinner, a concert, and a gift paid from Long-term Savings
    once Experience was used up. Demo only ("Cooked week")."""
    return sample_payments() + [
        {"id": "c1", "date": "2026-11-10", "amount": 12000, "category": "experience", "note": "concert",
         "from": {**empty_from(), "experience": 12000}},
        {"id": "c2", "date": "2026-11-10", "amount": 26000, "category": "main", "note": "group dinner",
         "from": {**empty_from(), "main": 26000}},
        {"id": "c3", "date": "2026-11-11", "amount": 10000, "category": "experience", "note": "birthday gift",
         "from": {**empty_from(), "savings": 10000}},
    ]


def used(payments, fund):
    return sum(p.get("from", {}).get(fund, 0) for p in payments)


def daily_impact(payment):
    taken = payment.get("from", {})
    return taken.get("main", 0) + taken.get("snack", 0)


def ready(state):
    return all(state["opening"][fund] is not None for fund in FUNDS)


def snapshot(state):
    dates = week_dates(state["weekStart"])
    days_left = sum(1 for day in dates if day >= state["today"])
    days_after = max(days_left - 1, 0)
    if not ready(state):
        return {
            "dates": dates,
            "daysLeft": days_left,
            "daysAfter": days_after,
            "ready": False,
            "allowance": None,
            "todayRemaining": None,
            "spentToday": 0,
            "loggedToday": 0,
            "tomorrow": None,
            "threshold": None,
            "notice": False,
            "overToday": False,
            "lifeAtStart": None,
            "lifeNow": None,
            "fundsNow": {fund: None for fund in FUNDS},
            "fundsAtStart": {fund: None for fund in FUNDS},
            "flexLeft": None,
        }
    before = [p for p in state["payments"] if p["date"] < state["today"]]
    today_rows = [p for p in state["payments"] if p["date"] == state["today"]]
    funds_at_start = {fund: state["opening"][fund] - used(before, fund) for fund in FUNDS}
    funds_now = {fund: state["opening"][fund] - used(state["payments"], fund) for fund in FUNDS}
    life_at_start = funds_at_start["main"] + funds_at_start["snack"]
    spent_today = sum(daily_impact(p) for p in today_rows)
    logged_today = sum(p["amount"] for p in today_rows if p["category"] in FOOD)
    allowance = round_div(life_at_start, days_left) if days_left else 0
    today_remaining = allowance - spent_today
    life_now = life_at_start - spent_today
    unspent = max(today_remaining, 0)
    future = life_now - unspent
    tomorrow = round_div(future, days_after) if days_after else 0
    threshold = round_div(allowance * 8, 10)  # 80%
    return {
        "dates": dates,
        "daysLeft": days_left,
        "daysAfter": days_after,
        "ready": True,
        "allowance": allowance,
        "todayRemaining": today_remaining,
        "spentToday": spent_today,
        "loggedToday": logged_today,
        "tomorrow": tomorrow,
        "threshold": threshold,
        "notice": allowance > 0 and spent_today >= threshold and spent_today <= allowance,
        "overToday": allowance == 0 or spent_today > allowance,
        "lifeAtStart": life_at_start,
        "lifeNow": life_now,
        "fundsNow": funds_now,
        "fundsAtStart": funds_at_start,
        "flexLeft": sum(max(funds_now[fund], 0) for fund in FLEX_FUNDS),
    }


def week_close(opening, payments):
    """What a finished week hands to Long-term Savings, in cents.

    `flexMoved`: what is left in the flexible funds (Experience + Development),
    moved to Long-term Savings when the week ends. `savingsKept`: what is left of
    the week's own Long-term Savings. `total` is the two together. A fund that
    went below zero adds nothing.
    """
    if opening is None or any(opening[fund] is None for fund in FUNDS):
        return {"flexMoved": 0, "savingsKept": 0, "total": 0}
    left = {fund: opening[fund] - used(payments, fund) for fund in FUNDS}
    flex = sum(max(left[fund], 0) for fund in FLEX_FUNDS)
    kept = max(left["savings"], 0)
    return {"flexMoved": flex, "savingsKept": kept, "total": flex + kept}


FULL = 10000  # a tank level in basis points: 10000 is a full fund


def _tank_tone(fund, allocation, remaining):
    """Colour state of a tank. Integer comparisons only: above 50% high, 20 to 50% mid, below low."""
    if allocation <= 0:
        return "none"
    if fund == "fixed":
        return "neutral"  # Fixed Bills never covers anything else: no alert colour
    if remaining <= 0:
        return "empty"
    if remaining * 2 > allocation:
        return "high"
    if remaining * 5 >= allocation:
        return "mid"
    return "low"


def fund_tanks(state):
    """One tank per fund: allocation and remaining in cents, the level (basis points, 0..FULL) and a
    display percent (0..100; never 0 while money is left, never 100 once some is spent). [] until ready."""
    if not ready(state):
        return []
    now = snapshot(state)["fundsNow"]
    tanks = []
    for fund in FUNDS:
        allocation = state["opening"][fund]
        remaining = now[fund]
        level = percent = 0
        if allocation > 0:
            kept = min(max(remaining, 0), allocation)
            level = round_div(kept * FULL, allocation)
            percent = round_div(kept * 100, allocation)
            if kept > 0:
                level, percent = max(level, 1), max(percent, 1)
            if kept < allocation:
                level, percent = min(level, FULL - 1), min(percent, 99)
        tanks.append({
            "fund": fund,
            "name": FUND_NAMES[fund],
            "allocation": allocation,
            "remaining": remaining,
            "level": level,
            "percent": percent,
            "tone": _tank_tone(fund, allocation, remaining),
        })
    return tanks


def _copy_with(state, payment):
    return {**state, "payments": [*state["payments"], payment]}


COVER_ORDER = ("snack", "experience", "development", "savings")  # Fixed Bills is never a cover


def _option(state, choice, hole, taken, base):
    """One cover choice. `base` is what the payment takes before any cover; `cover` is the rest."""
    payment = {
        "date": state["today"],
        "amount": sum(taken.values()),
        "category": "main",
        "from": taken,
    }
    view = snapshot(_copy_with(state, payment))
    return {
        "choice": choice,
        "hole": hole,
        "from": taken,
        "cover": {fund: taken[fund] - base[fund] for fund in COVER_ORDER if taken[fund] > base[fund]},
        "fundsAfter": view["fundsNow"],
        "tomorrowAfter": view["tomorrow"],
        "spentAfter": view["spentToday"],
        "todayRemainingAfter": view["todayRemaining"],
    }


def _food_options(state, amount, category, view):
    bal = view["fundsNow"]
    hit = min(amount, max(view["todayRemaining"], 0))
    taken = empty_from()
    if category == "main":
        taken["main"] = min(hit, bal["main"])
        spill = hit - taken["main"]
        taken["snack"] = min(spill, bal["snack"])
    else:
        taken["snack"] = min(hit, bal["snack"])
        spill = hit - taken["snack"]
        taken["main"] = min(spill, bal["main"])
    excess = amount - taken["main"] - taken["snack"]
    if excess == 0:
        spent_after = view["spentToday"] + taken["main"] + taken["snack"]
        level = 1 if view["allowance"] > 0 and spent_after >= view["threshold"] and spent_after <= view["allowance"] else 0
        return {"saveNow": True, "level": level, "from": taken}
    snack_left = bal["snack"] - taken["snack"]
    flex = bal["experience"] + bal["development"]
    options = []
    if snack_left >= excess:
        snack_take = dict(taken)
        snack_take["snack"] += excess
        options.append(_option(state, "snack", 1, snack_take, taken))
    if flex >= excess:
        flexed = dict(taken)
        flexed["experience"] = min(excess, bal["experience"])
        flexed["development"] = excess - flexed["experience"]
        options.append(_option(state, FLEX, 2, flexed, taken))
    if not options:
        ladder = dict(taken)
        snack_part = min(excess, snack_left)
        ladder["snack"] += snack_part
        rest = excess - snack_part
        ladder["experience"] = min(rest, bal["experience"])
        rest -= ladder["experience"]
        ladder["development"] = min(rest, bal["development"])
        rest -= ladder["development"]
        if rest > bal["savings"]:
            return {"error": "The five funds cannot cover this."}
        ladder["savings"] = rest
        hole = 3 if ladder["savings"] else 2
        options.append(_option(state, "savings" if hole == 3 else FLEX, hole, ladder, taken))
    return {"saveNow": False, "level": min(item["hole"] for item in options), "options": options}


def _flex_options(state, amount, category, view):
    bal = view["fundsNow"]
    other = "development" if category == "experience" else "experience"
    taken = empty_from()
    taken[category] = min(amount, bal[category])
    base = dict(taken)
    rest = amount - taken[category]
    if rest == 0:
        return {"saveNow": True, "level": 0, "from": taken}
    taken[other] = min(rest, bal[other])
    rest -= taken[other]
    if rest > bal["savings"]:
        return {"error": "The five funds cannot cover this."}
    taken["savings"] = rest
    hole = 3 if taken["savings"] else 2
    choice = "savings" if hole == 3 else FLEX
    return {"saveNow": False, "level": hole, "options": [_option(state, choice, hole, taken, base)]}


def plan(state, amount, category):
    view = snapshot(state)
    if not view["ready"]:
        return {"error": "Set the five funds first."}
    if category == "fixed":
        bal = view["fundsNow"]["fixed"]
        taken = empty_from()
        taken["fixed"] = min(amount, bal)
        return {"saveNow": True, "level": 0, "from": taken, "uncovered": amount - taken["fixed"]}
    if category in FOOD:
        return _food_options(state, amount, category, view)
    if category in ("experience", "development"):
        return _flex_options(state, amount, category, view)
    return {"error": "Unknown category."}

