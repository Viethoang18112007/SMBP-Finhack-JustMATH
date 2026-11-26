"""Groceries: what to cook, what to buy, what it costs, and what the trip costs. Pure rules.

Data (backend/ssust/data):
- recipes.json: cheap student meals, ingredient quantities for one serving.
- grocery_prices.json: real supermarket shelf prices from the Consumer Council's Online Price
  Watch (source, URL and date in the file; tools/make_grocery_prices.py refreshes it). An
  ingredient with no product there has no price: it is shown as "price unknown", never guessed.
- transport_fares.json: the urban taxi meter table (Transport Department) and MTR Octopus fare
  bands from the MTR fare table (open data), each with its source and date. Trips are estimates.

Money is integer cents. Quantities may be fractions (a quarter of a garlic bulb): they use
fractions.Fraction, and a share of a pack is rounded half up to the cent. Distances are
straight lines (haversine, offline) times a street factor.
"""

import functools
import json
import math
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
MAX_SERVINGS = 10
MAX_KM = 100
MODES = ("walk", "mtr", "taxi")
FARE_TYPES = ("student", "adult")

# OSM names of supermarket chains that have prices in the Price Watch feed. Other formats of a
# group (fusion, Taste, ...) may price differently, so they are not matched.
_CHAIN_WORDS = (
    ("WELLCOME", ("wellcome", "惠康")),
    ("PARKNSHOP", ("parknshop", "百佳")),
    ("JASONS", ("jasons", "market place")),
    ("AEON", ("aeon", "永旺")),
    ("DCHFOOD", ("dch food", "大昌食品")),
    ("LUNGFUNG", ("lung fung", "龍豐")),
)


def chain_for(name):
    """The Price Watch chain code for a store name, or None."""
    text = (name or "").lower()
    for code, words in _CHAIN_WORDS:
        if any(word in text for word in words):
            return code
    return None


def _load(name):
    with open(DATA / name, encoding="utf-8") as handle:
        return json.load(handle)


@functools.lru_cache(maxsize=1)
def load_prices():
    return _load("grocery_prices.json")


@functools.lru_cache(maxsize=1)
def load_recipes():
    return _load("recipes.json")["recipes"]


@functools.lru_cache(maxsize=1)
def load_fares():
    return _load("transport_fares.json")


def check_prices(data):
    """Problems in a price table ([] when every price is whole cents with a source and a date)."""
    problems = []
    for key in ("source", "sourceUrl", "checkedOn"):
        if not isinstance(data.get(key), str) or not data.get(key):
            problems.append(f"missing {key}")
    for ing_id, ing in data.get("ingredients", {}).items():
        for product in ing.get("products", []):
            if type(product.get("pack")) not in (int, float) or not product["pack"] > 0:
                problems.append(f"{ing_id}/{product.get('code')}: bad pack size")
            for chain, cents in product.get("prices", {}).items():
                if type(cents) is not int or cents <= 0:
                    problems.append(f"{ing_id}/{product.get('code')}/{chain}: price must be whole cents")
    return problems


def _qty(value):
    if type(value) not in (int, float) or isinstance(value, bool) or not value > 0:
        raise ValueError("A quantity must be a number above 0.")
    return Fraction(str(value))


def _qty_text(qty):
    return str(qty.numerator) if qty.denominator == 1 else f"{qty.numerator}/{qty.denominator}"


def share_cents(price_cents, qty, pack):
    """The cost of `qty` out of a pack of `pack` at `price_cents`, rounded half up to the cent."""
    exact = Fraction(price_cents) * Fraction(qty) / Fraction(str(pack))
    return math.floor(exact + Fraction(1, 2))


def _offers(ing, need):
    """[(buy cents, chain, product, packs)] for every product and chain, in file order."""
    offers = []
    for product in ing["products"]:
        pack = Fraction(str(product["pack"]))
        packs = math.ceil(need / pack)
        for chain, cents in product["prices"].items():
            offers.append((packs * cents, chain, product, packs))
    return offers


def _pick(ing, need, chain):
    """(status, offer) for one ingredient at a chain, or ("unknown", None)."""
    offers = _offers(ing, need)
    if not offers:
        return "unknown", None
    if chain is not None:
        here = [o for o in offers if o[1] == chain]
        if here:
            return "chain", min(here, key=lambda o: o[0])
    # Typical supermarket price: each chain's cheapest offer, then the lower median of those.
    best = {}
    for offer in offers:
        if offer[1] not in best or offer[0] < best[offer[1]][0]:
            best[offer[1]] = offer
    ranked = sorted(best.values(), key=lambda o: (o[0], o[1]))
    return ("other_chain" if chain is not None else "typical"), ranked[(len(ranked) - 1) // 2]


def basket(recipe, servings, prices, chain=None, include_pantry=False):
    """The shopping list for `servings` of `recipe` at a store of `chain` (None: any store).

    Each item: qty needed, the product chosen, whole packs to buy and their cost (buyCents), and
    the share of the pack this meal uses (usedCents). Pantry items (oil, sauces, salt) last many
    meals: they count in the total only with `include_pantry`. Unknown prices stay None.
    """
    if type(servings) is not int or not 1 <= servings <= MAX_SERVINGS:
        raise ValueError(f"Servings must be a whole number from 1 to {MAX_SERVINGS}.")
    items = []
    total = used_total = 0
    unknown = []
    for ing_id, per_serving in recipe["ingredients"]:
        ing = prices["ingredients"].get(ing_id)
        if ing is None:
            raise ValueError(f"Unknown ingredient: {ing_id}.")
        need = _qty(per_serving) * servings
        status, offer = _pick(ing, need, chain)
        item = {"id": ing_id, "name": ing["name"], "unit": ing["unit"], "qty": _qty_text(need), "pantry": ing["pantry"],
                "status": status, "product": None, "chain": None, "packs": None, "packCents": None, "buyCents": None,
                "usedCents": None}
        if offer is None:
            unknown.append(ing["name"])
        else:
            buy, offer_chain, product, packs = offer
            price = product["prices"][offer_chain]
            item.update({"product": {"code": product["code"], "brand": product["brand"], "name": product["name"],
                                     "nameZh": product["nameZh"], "pack": product["pack"]},
                         "chain": offer_chain, "packs": packs, "packCents": price, "buyCents": buy,
                         "usedCents": share_cents(price, need, product["pack"])})
            used_total += item["usedCents"]
            if include_pantry or not ing["pantry"]:
                total += buy
        items.append(item)
    return {"recipe": recipe["id"], "servings": servings, "chain": chain, "items": items, "totalCents": total,
            "usedCents": used_total, "unknown": unknown, "complete": not unknown, "includePantry": include_pantry}


def budget_fit(total_cents, main_left_cents):
    """The groceries against what is left in Main meals this week."""
    if main_left_cents is None:
        return {"status": "no_budget", "leftCents": None, "mainLeftCents": None}
    left = main_left_cents - total_cents
    return {"status": "fits" if left >= 0 else "over", "leftCents": left, "mainLeftCents": main_left_cents}


def taxi_cents(street_meters, taxi):
    """The urban taxi meter for a distance (no waiting time, tolls or extras)."""
    amount = taxi["flagCents"]
    steps = max(0, math.ceil((street_meters - taxi["flagMeters"]) / taxi["stepMeters"]))
    for _ in range(steps):
        amount += taxi["stepCents"] if amount < taxi["thresholdCents"] else taxi["afterStepCents"]
    return amount


def trip(distance_km, mode, fares, fare="student", round_trip=True):
    """The estimated cost of going to a store `distance_km` away (straight line) and back."""
    if type(distance_km) not in (int, float) or isinstance(distance_km, bool) or not 0 <= distance_km <= MAX_KM:
        raise ValueError(f"The distance must be between 0 and {MAX_KM} km.")
    if mode not in MODES:
        raise ValueError("Pick walk, MTR or taxi.")
    if fare not in FARE_TYPES:
        raise ValueError("Pick a student or adult fare.")
    street_m = math.ceil(distance_km * 1000 * fares["roadFactorPct"] / 100)
    legs = 2 if round_trip else 1
    result = {"mode": mode, "roundTrip": round_trip, "fare": fare, "streetKm": f"{street_m / 1000:.2f}",
              "estimate": True, "minutes": None, "source": None, "sourceUrl": None, "checkedOn": fares["checkedOn"],
              "needsCheck": False, "note": fares["roadNote"]}
    if mode == "walk":
        one = 0
        result["minutes"] = math.ceil(street_m * 60 / (fares["walk"]["kmPerHour"] * 1000))
        result["note"] = fares["walk"]["note"]
    elif mode == "taxi":
        taxi = fares["taxi"]
        one = taxi_cents(street_m, taxi)
        result.update(source=taxi["source"], sourceUrl=taxi["sourceUrl"], checkedOn=taxi["checkedOn"],
                      needsCheck=taxi["needsCheck"], note=taxi["note"])
    else:
        mtr = fares["mtr"]
        band = next(b for b in mtr["bands"] if b["maxKm"] is None or distance_km <= b["maxKm"])
        one = band[f"{fare}Cents"]
        result.update(source=mtr["source"], sourceUrl=mtr["sourceUrl"], checkedOn=mtr["checkedOn"],
                      needsCheck=mtr["needsCheck"], note=mtr["note"])
    result["oneWayCents"] = one
    result["cents"] = one * legs
    return result


def _hk(cents):
    dollars, rest = divmod(abs(cents), 100)
    return f"HK${dollars:,}" + (f".{rest:02d}" if rest else "")


def compare(options):
    """Which store is worth going to: groceries + trip for two or more stores.

    `options` are {id, name, groceriesCents, tripCents}. Returns None for a single store.
    """
    if len(options) < 2:
        return None
    totals = sorted(options, key=lambda o: (o["groceriesCents"] + o["tripCents"], o["id"]))
    best, other = totals[0], totals[1]
    saves = (other["groceriesCents"] + other["tripCents"]) - (best["groceriesCents"] + best["tripCents"])
    if saves == 0:
        return {"best": None, "savesCents": 0, "text": "Both cost the same in total: pick the closer one."}
    text = f"{best['name']} is {_hk(saves)} cheaper in total (groceries + trip)."
    basket_gap = best["groceriesCents"] - other["groceriesCents"]
    if basket_gap > 0:
        text += (f" {other['name']} has the cheaper basket ({_hk(basket_gap)} less) but its trip costs "
                 f"{_hk(other['tripCents'] - best['tripCents'])} more, so it is not worth the trip.")
    return {"best": best["id"], "savesCents": saves, "text": text}
