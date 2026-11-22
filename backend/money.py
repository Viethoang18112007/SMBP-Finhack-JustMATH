"""SSUST money rules, in cents.

Five funds, from the ZUNO framework: Main meals, Snacks, Fixed Bills,
Experience, Development, and Long-term Savings.
Today's food line is fixed in the morning:
food left at the start of today, divided by the days left, including today.
A gap is covered in this order: Snacks, then Experience, then Development,
then Long-term Savings. Fixed Bills never borrows.
"""

import math

FUNDS = ("main", "snack", "fixed", "experience", "development", "savings")
CATEGORIES = ("main", "snack", "fixed", "experience", "development")
FOOD = frozenset({"main", "snack"})
SAMPLE_WEEK_START = "2026-11-09"
SAMPLE_TODAY = "2026-11-11"
MAX_CENTS = 100_000_000

SAMPLE_OPENING = {
    "main": 77000,
    "snack": 8000,
    "fixed": 20000,
    "experience": 12000,
    "development": 8000,
    "savings": 50000,
}


def js_round(value):
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def add_days(iso, n):
    from datetime import date, timedelta
    year, month, day = (int(part) for part in iso.split("-"))
    return (date(year, month, day) + timedelta(days=n)).isoformat()


def week_dates(start):
    return [add_days(start, i) for i in range(7)]


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
    return {**base, "mode": "sample", "opening": dict(SAMPLE_OPENING), "payments": sample_payments()}


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
        }
    before = [p for p in state["payments"] if p["date"] < state["today"]]
    today_rows = [p for p in state["payments"] if p["date"] == state["today"]]
    funds_at_start = {fund: state["opening"][fund] - used(before, fund) for fund in FUNDS}
    funds_now = {fund: state["opening"][fund] - used(state["payments"], fund) for fund in FUNDS}
    life_at_start = funds_at_start["main"] + funds_at_start["snack"]
    spent_today = sum(daily_impact(p) for p in today_rows)
    logged_today = sum(p["amount"] for p in today_rows if p["category"] in FOOD)
    allowance = js_round(life_at_start / days_left) if days_left else 0
    today_remaining = allowance - spent_today
    life_now = life_at_start - spent_today
    unspent = max(today_remaining, 0)
    future = life_now - unspent
    tomorrow = js_round(future / days_after) if days_after else 0
    threshold = js_round(allowance * 0.8)
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
    }


def _copy_with(state, payment):
    return {**state, "payments": [*state["payments"], payment]}


def _option(state, choice, hole, taken):
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
        options.append(_option(state, "snack", 1, snack_take))
    if flex >= excess:
        borrowed = dict(taken)
        borrowed["experience"] = min(excess, bal["experience"])
        borrowed["development"] = excess - borrowed["experience"]
        options.append(_option(state, "borrow", 2, borrowed))
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
        options.append(_option(state, "savings" if hole == 3 else "borrow", hole, ladder))
    return {"saveNow": False, "level": min(item["hole"] for item in options), "options": options}


def _flex_options(state, amount, category, view):
    bal = view["fundsNow"]
    other = "development" if category == "experience" else "experience"
    taken = empty_from()
    taken[category] = min(amount, bal[category])
    rest = amount - taken[category]
    if rest == 0:
        return {"saveNow": True, "level": 0, "from": taken}
    taken[other] = min(rest, bal[other])
    rest -= taken[other]
    if rest > bal["savings"]:
        return {"error": "The five funds cannot cover this."}
    taken["savings"] = rest
    hole = 3 if taken["savings"] else 2
    choice = "savings" if hole == 3 else "borrow"
    return {"saveNow": False, "level": hole, "options": [_option(state, choice, hole, taken)]}


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


def parse_amount(raw):
    if not isinstance(raw, str):
        return None
    cleaned = raw.replace("HK$", "").replace("hk$", "").replace(",", "").strip()
    if not cleaned or cleaned.count(".") > 1:
        return None
    whole, _, frac = cleaned.partition(".")
    if not whole.isdigit() or (frac and (not frac.isdigit() or len(frac) > 2)):
        return None
    cents = int(whole) * 100 + int(frac.ljust(2, "0") or "0")
    if cents <= 0 or cents > MAX_CENTS:
        return None
    return cents


def clean_note(raw):
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError("Note must be text.")
    note = "".join(ch for ch in raw if ch.isprintable() and ch not in "<>")
    return note.strip()[:40]
