"""Regenerate backend/ssust/data/grocery_prices.json from the Consumer Council's Online Price
Watch open data (supermarket shelf prices, updated daily). Needs the internet.

    python tools/make_grocery_prices.py                 # download the feed
    python tools/make_grocery_prices.py --file feed.json  # a feed saved earlier

Each ingredient of the recipes is tied to one to four real products by their Price Watch code,
with the pack size read from the product name. The tool refuses a product whose Chinese name
does not contain that pack size (the product changed: check it by hand). It never makes up a
price: an ingredient without a product in the feed (spring onion, ginger...) is written with no
products, and the app shows "price unknown". Offers (buy 2 for X) are not applied: shelf prices
only. Standard library only.
"""

import argparse
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "ssust" / "data" / "grocery_prices.json"
FEED_URL = "https://online-price-watch.consumer.org.hk/opw/opendata/pricewatch.json"
SOURCE = "Consumer Council, Online Price Watch (open data, DATA.GOV.HK)"
CHAINS = {"WELLCOME": "Wellcome", "PARKNSHOP": "PARKnSHOP", "JASONS": "Market Place by Jasons", "AEON": "AEON",
          "DCHFOOD": "DCH Food Mart", "LUNGFUNG": "Lung Fung", "WATSONS": "Watsons", "MANNINGS": "Mannings",
          "SASA": "Sasa"}

# id: (English name, recipe unit, pantry item?, [(product code, pack quantity in the recipe unit,
#      text that must be in the Chinese product name)])
INGREDIENTS = {
    "rice": ("White rice", "g", False, [("P000004619", 1000, "1公斤"), ("P000003771", 2000, "2公斤"),
                                         ("P000004624", 2000, "2公斤")]),
    "egg": ("Eggs", "pc", False, [("P000003615", 12, "12隻"), ("P000005068", 10, "10隻"), ("P000004046", 10, "10隻"),
                                  ("P000001442", 8, "8隻")]),
    "tomato": ("Tomatoes", "g", False, [("P000001848", 454, "1磅")]),
    "tofu": ("Firm tofu", "g", False, [("P000000930", 340, "340克"), ("P000003124", 300, "300克")]),
    "instant_noodles": ("Instant noodles", "pack", False, [("P000000390", 5, "x 5"), ("P000000300", 5, "x 5")]),
    "garlic": ("Garlic", "bulb", False, [("P000002996", 3, "3個"), ("P000002997", 3, "3個")]),
    "baby_cabbage": ("Baby cabbage", "g", False, [("P000001812", 450, "450克")]),
    "broccoli": ("Broccoli", "head", False, [("P000001821", 1, "每個"), ("P000005077", 1, "每個")]),
    "carrot": ("Carrots", "g", False, [("P000001828", 1000, "1公斤")]),
    "potato": ("Potatoes", "g", False, [("P000001827", 907, "2磅")]),
    "mixed_veg": ("Frozen mixed vegetables", "g", False, [("P000004410", 500, "500克"), ("P000004158", 500, "500克")]),
    "shrimp": ("Frozen shrimp meat", "g", False, [("P000005109", 170, "170克"), ("P000005488", 180, "180克")]),
    "beef": ("Frozen sliced beef", "g", False, [("P000004140", 200, "200克")]),
    "chicken_wings": ("Frozen chicken wings", "g", False, [("P000004100", 907, "907克")]),
    "luncheon_meat": ("Luncheon meat", "g", False, [("p000000669", 198, "198克"), ("P000005238", 198, "198克")]),
    "fish_balls": ("Fish balls", "g", False, [("P000000532", 170, "170克")]),
    "sausage": ("Chicken sausages", "g", False, [("P000000132", 340, "340.2克")]),
    "tuna": ("Canned tuna", "g", False, [("P000003824", 95, "95克"), ("P000003955", 95, "95克")]),
    "bread": ("Sandwich bread", "slice", False, [("P000000229", 6, "6片"), ("P000003700", 8, "8片")]),
    "spaghetti": ("Spaghetti", "g", False, [("P000004017", 500, "500克"), ("P000002764", 500, "500克")]),
    "pasta_sauce": ("Tomato pasta sauce", "g", False, [("P000003897", 340, "340克"), ("P000003896", 340, "340克")]),
    "udon": ("Udon noodles", "g", False, [("P000001324", 800, "200克 x 4")]),
    "noodles": ("Shanghai noodles", "g", False, [("P000000047", 340, "340克"), ("P000004012", 340, "340克")]),
    "rice_vermicelli": ("Rice vermicelli", "g", False, [("P000003315", 454, "454克")]),
    "oats": ("Oats", "g", False, [("P000005285", 200, "200克"), ("P000002709", 200, "200克")]),
    "milk": ("Milk", "ml", False, [("P000003054", 1000, "1公升")]),
    "banana": ("Bananas", "g", False, [("P000001631", 454, "每磅")]),
    "chicken_broth": ("Chicken broth", "ml", False, [("P000003496", 500, "500毫升"), ("P000001735", 250, "250毫升")]),
    "curry_sauce": ("Curry sauce", "g", False, [("P000000710", 235, "235克")]),
    "cooking_oil": ("Cooking oil", "ml", True, [("P000005224", 1000, "1公升")]),
    "soy_sauce": ("Light soy sauce", "ml", True, [("P000000664", 500, "500毫升")]),
    "oyster_sauce": ("Oyster sauce", "g", True, [("P000001715", 555, "555克"), ("P000002475", 735, "735克")]),
    "sesame_oil": ("Sesame oil", "ml", True, [("P000004943", 150, "150毫升")]),
    "chili_bean_sauce": ("Chili bean sauce", "g", True, [("P000000715", 240, "240克")]),
    "mayonnaise": ("Mayonnaise", "g", True, [("P000003158", 300, "300克")]),
    "salt": ("Salt", "g", True, [("P000003685", 454, "454克"), ("P000004035", 454, "454克")]),
    "sugar": ("Sugar", "g", True, [("P000003687", 400, "400克"), ("P000000814", 400, "400克")]),
    "corn_starch": ("Corn starch", "g", True, [("P000001621", 227, "227克")]),
    # Not sold in the Price Watch list: always "price unknown" (wet market or greengrocer).
    "spring_onion": ("Spring onion", "g", False, []),
    "ginger": ("Ginger", "g", False, []),
}


def cents(text):
    whole, _, frac = str(text).strip().partition(".")
    if not whole.isdigit() or (frac and not frac.isdigit()) or len(frac) > 2:
        raise ValueError(f"not a price: {text!r}")
    return int(whole) * 100 + int(frac.ljust(2, "0") or "0")


def build(feed, fetched_on):
    by_code = {item["code"]: item for item in feed}
    problems = []
    out = {}
    for ing_id, (name, unit, pantry, products) in INGREDIENTS.items():
        kept = []
        for code, pack, must in products:
            item = by_code.get(code)
            if item is None:
                problems.append(f"{ing_id}: {code} is no longer in the feed")
                continue
            zh = item["name"]["zh-Hant"]
            if must not in zh:
                problems.append(f"{ing_id}: {code} name {zh!r} does not contain {must!r}")
                continue
            prices = {p["supermarketCode"]: cents(p["price"]) for p in item.get("prices", [])
                      if p.get("supermarketCode") in CHAINS}
            if not prices:
                problems.append(f"{ing_id}: {code} has no price")
                continue
            kept.append({"code": code, "brand": item["brand"]["en"], "name": item["name"]["en"], "nameZh": zh,
                         "pack": pack, "prices": dict(sorted(prices.items()))})
        out[ing_id] = {"name": name, "unit": unit, "pantry": pantry, "products": kept}
    data = {
        "source": SOURCE,
        "sourceUrl": FEED_URL,
        "checkedOn": fetched_on,
        "note": "Shelf prices of the listed products on that day; offers not applied. Prices change: estimate.",
        "chains": CHAINS,
        "ingredients": out,
    }
    return data, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--file", type=Path, help="a saved copy of the feed instead of downloading it")
    parser.add_argument("--date", default=date.today().isoformat(), help="the day the feed was read (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if args.file:
        feed = json.loads(args.file.read_text(encoding="utf-8"))
    else:
        request = urllib.request.Request(FEED_URL, headers={"User-Agent": "SSUST-price-tool/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            feed = json.load(response)
    data, problems = build(feed, args.date)
    for problem in problems:
        print(f"refused: {problem}", file=sys.stderr)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    priced = sum(1 for item in data["ingredients"].values() if item["products"])
    print(f"Wrote {OUT.relative_to(ROOT)}: {priced} of {len(data['ingredients'])} ingredients with a price.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
