"""Rewards for good money habits. Pure functions, integer cents, no I/O.

- streak: days in a row with at least one payment logged. Its shape changes at each level
  (square, star, diamond, hexagon, crown). It stays alive until today ends.
- week_stars: 1 to 5 stars for how a finished week was balanced. 3 stars means money was left.
- medals: per campus, how many different places a meal was logged at while it fit that day's
  food money (bronze, silver, gold). They reward eating well within budget, not eating out more.
- badges: one-time achievements built from the above.
"""

from datetime import date, timedelta

from .money import CATEGORIES, FUNDS, used

# (shape, name, days in a row needed)
STREAK_SHAPES = (
    ("square", "Square", 1),
    ("star", "Star", 3),
    ("diamond", "Diamond", 7),
    ("hexagon", "Hexagon", 14),
    ("crown", "Crown", 30),
)

# (medal, places within budget needed)
MEDALS = (("bronze", 3), ("silver", 7), ("gold", 15))

SAVER_CENTS = 50000  # HK$500 in Long-term Savings

# (id, name, how to earn it)
BADGES = (
    ("first_entry", "First entry", "Log your first payment."),
    ("planner", "Planner", "Set a weekly budget."),
    ("on_a_roll", "On a roll", "Log spending 3 days in a row."),
    ("full_week", "Full week", "Log spending 7 days in a row."),
    ("money_left", "Money left", "End a week with money left (3 stars or more)."),
    ("five_stars", "Five stars", "Get 5 stars for a week."),
    ("saver", "Saver", "Build HK$500 in Long-term Savings."),
    ("smart_explorer", "Smart explorer", "Earn a bronze medal near a campus."),
)


def _day(text):
    return date.fromisoformat(text)


def streak(dates, today):
    """The logging streak on `today` from the dates (YYYY-MM-DD) that have a payment.

    Returns {"days", "best", "loggedToday", "shape", "name", "next"}. `next` is the next shape
    ({"shape", "name", "at", "daysToGo"}) or None at the top level. Dates after today are ignored.
    """
    end = _day(today)
    days = {_day(d) for d in dates if _day(d) <= end}
    logged_today = end in days
    current = 0
    cursor = end if logged_today else end - timedelta(days=1)
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)
    best = run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    reached = [level for level in STREAK_SHAPES if level[2] <= current]
    ahead = [level for level in STREAK_SHAPES if level[2] > current]
    shape, name = (reached[-1][0], reached[-1][1]) if reached else (None, None)
    following = None
    if ahead:
        following = {"shape": ahead[0][0], "name": ahead[0][1], "at": ahead[0][2], "daysToGo": ahead[0][2] - current}
    return {"days": current, "best": best, "loggedToday": logged_today, "shape": shape, "name": name,
            "next": following}


def week_stars(opening, payments):
    """1 to 5 stars for a finished week, or None when it had no spending budget.

    1  some spending had no money to cover it
    2  Long-term Savings had to cover spending, or nothing was left
    3  money was left (also the most a week with a reallocation between funds can get)
    4  at least 10% of the spending budget left, no reallocation
    5  at least 20% left, no reallocation

    The spending budget is the five spending funds (Long-term Savings is not spending).
    """
    if opening is None or any(opening.get(fund) is None for fund in FUNDS):
        return None
    budget = sum(opening[fund] for fund in CATEGORIES)
    if budget <= 0:
        return None
    spent = sum(p["amount"] for p in payments)
    left = budget - spent
    uncovered = sum(p.get("uncovered", 0) for p in payments)
    from_savings = used(payments, "savings")
    moved = any(amount for p in payments for fund, amount in p.get("from", {}).items() if fund != p["category"])
    if uncovered > 0:
        stars, why = 1, "Some spending had no money left to cover it."
    elif from_savings > 0:
        stars, why = 2, "Long-term Savings had to cover some spending."
    elif left <= 0:
        stars, why = 2, "The whole spending budget was used."
    elif moved or left * 10 < budget:
        stars, why = 3, "Money was left at the end of the week."
    elif left * 5 < budget:
        stars, why = 4, "At least 10% of the budget was left, with no fund going over."
    else:
        stars, why = 5, "At least 20% of the budget was left, with no fund going over."
    return {"stars": stars, "why": why, "budget": budget, "spent": spent, "left": left}


def medal_for(count):
    """"bronze", "silver", "gold" or None for a number of places within budget."""
    medal = None
    for name, needed in MEDALS:
        if count >= needed:
            medal = name
    return medal


def medals(counts, campuses):
    """One row per campus ((id, name) pairs, in order) with its count, medal and the next one."""
    rows = []
    for campus, name in campuses:
        count = counts.get(campus, 0)
        ahead = [(medal, needed) for medal, needed in MEDALS if needed > count]
        rows.append({"campus": campus, "name": name, "count": count, "medal": medal_for(count),
                     "next": {"medal": ahead[0][0], "at": ahead[0][1]} if ahead else None})
    return rows


def badges(payments, budget_weeks, best_streak, stars, savings, medals):
    """Every badge with "earned" true or false.

    `payments`: payments logged; `budget_weeks`: weeks with a budget; `best_streak`: longest run of
    days; `stars`: the stars of finished weeks; `savings`: Long-term Savings pot in cents;
    `medals`: the campus rows from medals().
    """
    earned = {
        "first_entry": payments > 0,
        "planner": budget_weeks > 0,
        "on_a_roll": best_streak >= 3,
        "full_week": best_streak >= 7,
        "money_left": any(s >= 3 for s in stars),
        "five_stars": any(s == 5 for s in stars),
        "saver": savings >= SAVER_CENTS,
        "smart_explorer": any(row.get("medal") for row in medals),
    }
    return [{"id": badge, "name": name, "how": how, "earned": earned[badge]} for badge, name, how in BADGES]
