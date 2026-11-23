"""The SSUST assistant: quick entries in plain words, typo checks, and spending analysis.

Offline rules only (no AI service, no network): a parser turns "$50 KFC dinner" into an
amount, a fund and a note; a check flags amounts that look like a typo; the analysis
projects this week's spending pace and warns before a fund runs out. Integer cents.
"""

import math
import re

from . import money, prices
from .dates import week_dates

# Words that point to a fund (English and Chinese). Checked after chain names.
KEYWORDS = {
    "snack": ("coffee", "latte", "cappuccino", "americano", "milk tea", "bubble", "boba", "tea", "snack",
              "dessert", "cake", "bread", "bun", "drink", "juice", "ice cream", "chips", "咖啡", "奶茶",
              "茶", "甜品", "零食", "麵包", "雪糕", "飲品"),
    "main": ("breakfast", "brunch", "lunch", "dinner", "supper", "meal", "rice", "noodle", "congee", "canteen",
             "restaurant", "burger", "pizza", "sushi", "ramen", "dim sum", "hotpot", "bbq", "sandwich",
             "早餐", "午餐", "晚餐", "宵夜", "飯", "麵", "粥", "米線", "點心", "火鍋", "茶餐廳", "餐廳"),
    "fixed": ("rent", "phone bill", "mobile plan", "bill", "mtr", "bus", "minibus", "octopus", "top-up", "top up",
              "topup", "electricity", "water bill", "internet", "wifi", "hall fee", "tuition", "insurance",
              "交租", "租", "電話費", "八達通", "車費", "增值", "學費"),
    "experience": ("movie", "cinema", "film", "concert", "ticket", "game", "steam", "trip", "travel", "party",
                   "karaoke", "ktv", "gift", "clothes", "shoes", "shopping", "museum", "bowling", "netflix",
                   "spotify", "戲", "電影", "演唱會", "旅行", "禮物", "衫", "飛"),
    "development": ("book", "textbook", "course", "udemy", "coursera", "class", "tutorial", "workshop",
                    "stationery", "printing", "print", "notebook", "exam fee", "書", "課程", "文具", "影印"),
}
# Chains that are drinks or snacks rather than a meal.
SNACK_CHAINS = frozenset({"Starbucks", "Pacific Coffee", "Loud Tea"})
# Above these amounts (cents) a payment for the fund probably has a typo (an extra 0).
TYPICAL_MAX = {"main": 30000, "snack": 10000, "fixed": 1500000, "experience": 200000, "development": 300000}
_AMOUNT = re.compile(r"(?:hk\$|\$)\s*(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s*(?:hkd|hk\$|dollars?|蚊|元|圓)?",
                     re.IGNORECASE)
_MAX_TEXT = 120


def _cents(text):
    text = text.replace(",", "")
    whole, _, frac = text.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2]) if whole.isdigit() else None


def _find_amount(text):
    """(cents, span) for the first amount in `text`, preferring one written with $ or HK$."""
    found = []
    for match in _AMOUNT.finditer(text):
        raw = match.group(1) or match.group(2)
        if raw is None:
            continue
        cents = _cents(raw)
        if cents is None:
            continue
        found.append((0 if match.group(1) else 1, match.start(), cents, match.span()))
    if not found:
        return None, None
    found.sort()
    _, _, cents, span = found[0]
    return cents, span


def _category(words, chain):
    """(fund, reason, confident)."""
    low = words.lower()
    if chain is not None:
        fund = "snack" if chain["chain"] in SNACK_CHAINS else "main"
        return fund, f"{chain['chain']} is a {'drinks' if fund == 'snack' else 'food'} chain", True
    hits = []
    for fund, keys in KEYWORDS.items():
        for key in keys:
            if key in low:
                hits.append((len(key), fund, key))
    if hits:
        hits.sort(reverse=True)
        _, fund, key = hits[0]
        return fund, f'"{key}"', True
    return "main", "no clear clue, so Main meals", False


def check_typo(cents, fund, chain=None):
    """A suggestion when the amount looks like a typo, else None: {"reason", "suggestion"}."""
    if chain is not None and cents > chain["high_cents"] * 3:
        guess = cents // 10
        return {"reason": f"{money.hk(cents)} is a lot for {chain['chain']} (meals there are about "
                          f"{money.hk(chain['low_cents'])} to {money.hk(chain['high_cents'])}).",
                "suggestion": guess if guess >= 100 else None}
    limit = TYPICAL_MAX.get(fund)
    if limit and cents > limit:
        guess = cents // 10
        return {"reason": f"{money.hk(cents)} is unusually high for {money.FUND_NAMES[fund]}.",
                "suggestion": guess if guess >= 100 else None}
    return None


def _find_chain(words, chains):
    """The chain named anywhere in `words`: a run of words that is exactly one of its names."""
    parts = words.split()
    for size in range(len(parts), 0, -1):  # longest run first: "Pizza Hut" before "Pizza"
        for start in range(len(parts) - size + 1):
            key = prices.normalize_name(" ".join(parts[start:start + size]))
            for chain in chains:
                if key in chain["keys"]:
                    return chain
    return None


def parse_entry(text, chains=()):
    """Read a quick entry like "$50 KFC dinner" or "奶茶 28".

    Returns {"ok": True, "amount", "category", "note", "reason", "confident", "typo"} or
    {"ok": False, "error"}. Nothing is saved: the client confirms first.
    """
    if not isinstance(text, str) or not text.strip():
        return {"ok": False, "error": "Type what you paid, like $50 KFC dinner."}
    text = " ".join(text.split())[:_MAX_TEXT]
    cents, span = _find_amount(text)
    if cents is None or cents <= 0:
        return {"ok": False, "error": "Add an amount, like $50 KFC dinner."}
    rest = (text[:span[0]] + " " + text[span[1]:]).strip(" -,:")
    rest = " ".join(rest.split())
    chain = _find_chain(rest, chains)
    fund, reason, confident = _category(rest, chain)
    note = rest[:40] if rest else money.FUND_NAMES[fund]
    return {"ok": True, "amount": cents, "category": fund, "note": note, "reason": reason,
            "confident": confident, "typo": check_typo(cents, fund, chain),
            "chain": chain["chain"] if chain else None}


# Spending analysis

def _spent_by(payments, key):
    out = {}
    for p in payments:
        out[p[key]] = out.get(p[key], 0) + p["amount"]
    return out


def _day_name(iso):
    from datetime import date
    return date.fromisoformat(iso).strftime("%a %d %b").replace(" 0", " ")


def insights(state, previous=None):
    """Warnings and a breakdown for the week in `state` (with "view"); `previous` is last week's state.

    Pace = what a fund has used so far ÷ days so far (today included). A fund whose pace
    would empty it before Sunday gets a warning with the day it runs out.
    """
    view = state["view"]
    if not view["ready"]:
        return {"ready": False, "warnings": [], "breakdown": [], "notes": []}
    dates = week_dates(state["weekStart"])
    today = state["today"]
    days_so_far = sum(1 for d in dates if d <= today) or 1
    opening, now = state["opening"], view["fundsNow"]
    warnings = []

    def projection(name, budget, used, key):
        if budget <= 0 or used <= 0:
            return
        per_day = used / days_so_far
        projected = round(per_day * 7)
        if projected <= budget:
            return
        day_index = min(math.ceil(budget / per_day), 7) - 1
        runs_out = dates[max(day_index, 0)]
        when = "already used up" if used >= budget else f"runs out around {_day_name(runs_out)}"
        warnings.append({
            "fund": key,
            "level": "high" if used >= budget or day_index < 5 else "medium",
            "title": f"{name}: {when}",
            "text": (f"At this pace ({money.hk(round(per_day))} a day) you would spend {money.hk(projected)} "
                     f"this week, {money.hk(projected - budget)} more than the {money.hk(budget)} set."),
        })

    food_budget = opening["main"] + opening["snack"]
    food_used = food_budget - now["main"] - now["snack"]
    projection("Food and drinks", food_budget, food_used, "food")
    for fund in ("snack", "experience", "development"):
        projection(money.FUND_NAMES[fund], opening[fund], opening[fund] - now[fund], fund)

    payments = state["payments"]
    total = sum(p["amount"] for p in payments)
    by_fund = _spent_by(payments, "category")
    breakdown = [{"fund": f, "name": money.FUND_NAMES[f], "spent": by_fund[f],
                  "share": round(by_fund[f] * 100 / total) if total else 0}
                 for f in sorted(by_fund, key=by_fund.get, reverse=True)]
    by_note = {}
    for p in payments:
        label = (p.get("note") or money.FUND_NAMES[p["category"]]).strip()
        by_note[label] = by_note.get(label, 0) + p["amount"]
    top = sorted(by_note.items(), key=lambda kv: kv[1], reverse=True)[:3]
    by_day = _spent_by(payments, "date")
    peak = max(by_day.items(), key=lambda kv: kv[1]) if by_day else None

    notes = []
    if peak:
        notes.append(f"Your biggest day so far was {_day_name(peak[0])} ({money.hk(peak[1])}).")
    if top:
        notes.append("Most money went to: " + ", ".join(f"{name} ({money.hk(c)})" for name, c in top) + ".")
    if previous and previous.get("view", {}).get("ready"):
        prev_dates = week_dates(previous["weekStart"])
        same_days = set(prev_dates[:days_so_far])
        prev_total = sum(p["amount"] for p in previous["payments"] if p["date"] in same_days)
        if prev_total:
            diff = total - prev_total
            word = "more" if diff > 0 else "less"
            notes.append(f"By this day last week you had spent {money.hk(prev_total)}; this week is "
                         f"{money.hk(abs(diff))} {word}.")
    flex_left = view.get("flexLeft") or 0
    if flex_left:
        notes.append(f"Keep {money.hk(flex_left)} in your flexible funds until Sunday and it moves to Long-term Savings.")
    if not warnings:
        headline = "On track: at this pace every fund lasts the week."
    else:
        headline = f"{len(warnings)} fund{'s' if len(warnings) > 1 else ''} will not last the week at this pace."
    return {"ready": True, "headline": headline, "warnings": warnings, "breakdown": breakdown,
            "notes": notes, "total": total, "daysSoFar": days_so_far}
