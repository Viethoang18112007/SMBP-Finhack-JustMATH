"""Groceries: what to cook, what to buy, what it costs, and the trip to the shop.

groceries.py is pure (no I/O apart from loading its three data files). Money is integer cents;
quantities may be fractions (a quarter of a garlic bulb). Every price comes from the sourced
table or is "unknown"; every fare from the sourced fare table, marked as an estimate.
"""

import copy
import unittest
from fractions import Fraction

from ssust import groceries

PRICES = {
    "source": "Test source", "sourceUrl": "https://example.org/feed.json", "checkedOn": "2026-11-26",
    "chains": {"WELLCOME": "Wellcome", "PARKNSHOP": "PARKnSHOP", "AEON": "AEON"},
    "ingredients": {
        "rice": {"name": "White rice", "unit": "g", "pantry": False, "products": [
            {"code": "R1", "brand": "A", "name": "Rice 1kg", "nameZh": "米 1公斤", "pack": 1000,
             "prices": {"PARKNSHOP": 2300}},
            {"code": "R2", "brand": "B", "name": "Rice 2kg", "nameZh": "米 2公斤", "pack": 2000,
             "prices": {"WELLCOME": 3000, "AEON": 3600}}]},
        "egg": {"name": "Eggs", "unit": "pc", "pantry": False, "products": [
            {"code": "E1", "brand": "C", "name": "Eggs 10", "nameZh": "蛋 10隻", "pack": 10,
             "prices": {"WELLCOME": 2500, "PARKNSHOP": 2800, "AEON": 2990}}]},
        "oil": {"name": "Cooking oil", "unit": "ml", "pantry": True, "products": [
            {"code": "O1", "brand": "D", "name": "Oil 1L", "nameZh": "油 1公升", "pack": 1000,
             "prices": {"WELLCOME": 3000, "PARKNSHOP": 3000}}]},
        "ginger": {"name": "Ginger", "unit": "g", "pantry": False, "products": []},
        "garlic": {"name": "Garlic", "unit": "bulb", "pantry": False, "products": [
            {"code": "G1", "brand": "E", "name": "Garlic 3", "nameZh": "蒜 3個", "pack": 3, "prices": {"PARKNSHOP": 390}}]},
    },
}
RECIPE = {"id": "test_rice", "name": "Test rice", "nameZh": "", "minutes": 10, "steps": "Cook.",
          "ingredients": [["rice", 100], ["egg", 2], ["oil", 10], ["ginger", 5], ["garlic", 0.25]]}
FARES = groceries.load_fares()


class Basket(unittest.TestCase):
    def item(self, result, ing):
        return next(i for i in result["items"] if i["id"] == ing)

    def test_one_serving_at_a_chain(self):
        result = groceries.basket(RECIPE, 1, PRICES, chain="PARKNSHOP")
        rice = self.item(result, "rice")
        self.assertEqual((rice["status"], rice["product"]["code"], rice["packs"], rice["buyCents"]), ("chain", "R1", 1, 2300))
        self.assertEqual(rice["usedCents"], 230)  # 100 g of a HK$23 kilo
        egg = self.item(result, "egg")
        self.assertEqual((egg["buyCents"], egg["usedCents"]), (2800, 560))
        # Pantry items are not bought for one meal: shown with their share only.
        oil = self.item(result, "oil")
        self.assertTrue(oil["pantry"])
        self.assertEqual(oil["usedCents"], 30)
        garlic = self.item(result, "garlic")
        self.assertEqual((garlic["qty"], garlic["usedCents"]), ("1/4", 33))  # 390 / 3 / 4 = 32.5 -> 33
        ginger = self.item(result, "ginger")
        self.assertEqual(ginger["status"], "unknown")
        self.assertIsNone(ginger["buyCents"])
        self.assertEqual(result["totalCents"], 2300 + 2800 + 390)
        self.assertEqual(result["unknown"], ["Ginger"])
        self.assertFalse(result["complete"])
        for i in result["items"]:
            for key in ("buyCents", "usedCents", "packCents"):
                self.assertTrue(i[key] is None or type(i[key]) is int, (i["id"], key))

    def test_pantry_can_be_included(self):
        result = groceries.basket(RECIPE, 1, PRICES, chain="PARKNSHOP", include_pantry=True)
        self.assertEqual(result["totalCents"], 2300 + 2800 + 390 + 3000)

    def test_servings_scale_and_whole_packs(self):
        result = groceries.basket(RECIPE, 6, PRICES, chain="WELLCOME")
        egg = self.item(result, "egg")
        self.assertEqual((egg["qty"], egg["packs"], egg["buyCents"]), ("12", 2, 5000))
        self.assertEqual(egg["usedCents"], 3000)
        rice = self.item(result, "rice")
        self.assertEqual((rice["qty"], rice["packs"], rice["buyCents"]), ("600", 1, 3000))

    def test_cheapest_pack_for_what_is_needed(self):
        # 1.5 kg of rice at PARKnSHOP: two 1 kg bags (HK$46) is the only product there.
        result = groceries.basket({**RECIPE, "ingredients": [["rice", 1500]]}, 1, PRICES, chain="PARKNSHOP")
        self.assertEqual(self.item(result, "rice")["buyCents"], 4600)

    def test_product_not_sold_at_this_chain(self):
        result = groceries.basket(RECIPE, 1, PRICES, chain="AEON")
        garlic = self.item(result, "garlic")
        self.assertEqual(garlic["status"], "other_chain")
        self.assertEqual(garlic["chain"], "PARKNSHOP")
        self.assertEqual(garlic["buyCents"], 390)

    def test_unknown_store_gets_the_typical_supermarket_price(self):
        result = groceries.basket(RECIPE, 1, PRICES, chain=None)
        egg = self.item(result, "egg")
        self.assertEqual(egg["status"], "typical")
        # Lower median of the chains' prices: 2500, 2800, 2990 -> 2800.
        self.assertEqual(egg["buyCents"], 2800)
        rice = self.item(result, "rice")
        # Best per chain: PARKnSHOP 2300, Wellcome 3000, AEON 3600 -> 3000.
        self.assertEqual(rice["buyCents"], 3000)

    def test_bad_servings_and_unknown_ingredient(self):
        for bad in (0, 11, 2.5, True, "2"):
            with self.subTest(servings=bad), self.assertRaises(ValueError):
                groceries.basket(RECIPE, bad, PRICES)
        broken = {**RECIPE, "ingredients": [["caviar", 10]]}
        with self.assertRaises(ValueError):
            groceries.basket(broken, 1, PRICES)

    def test_round_half_up_in_cents(self):
        self.assertEqual(groceries.share_cents(390, Fraction(1, 4), 3), 33)
        self.assertEqual(groceries.share_cents(100, Fraction(1, 3), 1), 33)
        self.assertEqual(groceries.share_cents(5, Fraction(1, 2), 1), 3)


class Fit(unittest.TestCase):
    def test_against_main_meals(self):
        self.assertEqual(groceries.budget_fit(5000, 8000), {"status": "fits", "leftCents": 3000, "mainLeftCents": 8000})
        self.assertEqual(groceries.budget_fit(9000, 8000)["status"], "over")
        self.assertEqual(groceries.budget_fit(9000, 8000)["leftCents"], -1000)
        self.assertEqual(groceries.budget_fit(100, None), {"status": "no_budget", "leftCents": None, "mainLeftCents": None})


class Transport(unittest.TestCase):
    def test_walk_is_free(self):
        trip = groceries.trip(0.8, "walk", FARES)
        self.assertEqual(trip["cents"], 0)
        self.assertEqual(trip["streetKm"], "1.04")
        self.assertEqual(trip["minutes"], 13)

    def test_taxi_meter(self):
        taxi = FARES["taxi"]
        self.assertEqual(groceries.taxi_cents(1500, taxi), 2900)
        self.assertEqual(groceries.taxi_cents(2000, taxi), 2900)
        self.assertEqual(groceries.taxi_cents(2001, taxi), 3110)
        self.assertEqual(groceries.taxi_cents(3000, taxi), 2900 + 5 * 210)
        # 35 steps of HK$2.1 reach HK$102.5 exactly; after that HK$1.4 a step.
        self.assertEqual(groceries.taxi_cents(2000 + 35 * 200, taxi), 10250)
        self.assertEqual(groceries.taxi_cents(2000 + 36 * 200, taxi), 10390)

    def test_taxi_trip_round_trip_and_estimate(self):
        one = groceries.trip(2.0, "taxi", FARES, round_trip=False)
        both = groceries.trip(2.0, "taxi", FARES, round_trip=True)
        self.assertEqual(one["streetKm"], "2.60")
        self.assertEqual(one["cents"], 2900 + 3 * 210)
        self.assertEqual(both["cents"], 2 * one["cents"])
        self.assertTrue(both["estimate"])
        self.assertIn("td.gov.hk", both["sourceUrl"])
        self.assertEqual(both["checkedOn"], "2026-11-26")

    def test_mtr_bands(self):
        self.assertEqual(groceries.trip(3, "mtr", FARES, fare="student", round_trip=False)["cents"], 320)
        self.assertEqual(groceries.trip(3, "mtr", FARES, fare="adult", round_trip=True)["cents"], 1180)
        self.assertEqual(groceries.trip(8, "mtr", FARES, fare="student", round_trip=False)["cents"], 460)
        self.assertEqual(groceries.trip(30, "mtr", FARES, fare="student", round_trip=False)["cents"], 650)
        mtr = groceries.trip(3, "mtr", FARES)
        self.assertTrue(mtr["needsCheck"])
        self.assertIn("opendata.mtr.com.hk", mtr["sourceUrl"])

    def test_bad_input(self):
        for args in ((-1, "walk"), (1, "boat"), (float("nan"), "taxi"), (1e6, "taxi")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                groceries.trip(*args, FARES)
        with self.assertRaises(ValueError):
            groceries.trip(1, "mtr", FARES, fare="vip")


class Compare(unittest.TestCase):
    def test_cheaper_basket_but_dearer_trip(self):
        result = groceries.compare([
            {"id": "a", "name": "Far Wellcome", "groceriesCents": 4000, "tripCents": 1200},
            {"id": "b", "name": "Near PARKnSHOP", "groceriesCents": 4500, "tripCents": 0},
        ])
        self.assertEqual(result["best"], "b")
        self.assertEqual(result["savesCents"], 700)
        self.assertIn("Far Wellcome", result["text"])
        self.assertIn("cheaper basket", result["text"])
        self.assertIn("HK$12", result["text"])

    def test_same_total(self):
        result = groceries.compare([
            {"id": "a", "name": "A", "groceriesCents": 1000, "tripCents": 0},
            {"id": "b", "name": "B", "groceriesCents": 1000, "tripCents": 0},
        ])
        self.assertIsNone(result["best"])
        self.assertEqual(result["savesCents"], 0)

    def test_one_store_needs_no_verdict(self):
        self.assertIsNone(groceries.compare([{"id": "a", "name": "A", "groceriesCents": 1, "tripCents": 0}]))


class Chains(unittest.TestCase):
    def test_names(self):
        for name, chain in (("惠康 Wellcome", "WELLCOME"), ("百佳 PARKnSHOP", "PARKNSHOP"), ("PARKnSHOP Super", "PARKNSHOP"),
                            ("Market Place by Jasons", "JASONS"), ("AEON STYLE", "AEON"), ("永旺", "AEON"),
                            ("DCH Food Mart", "DCHFOOD"), ("大昌食品市場", "DCHFOOD"), ("7-Eleven", None), ("fusion", None),
                            ("Kowloon City Market", None)):
            with self.subTest(name=name):
                self.assertEqual(groceries.chain_for(name), chain)


class ShippedData(unittest.TestCase):
    """The files in backend/ssust/data: no price without a source, every recipe can be priced."""

    def test_prices_are_sourced_and_valid(self):
        data = groceries.load_prices()
        self.assertEqual(groceries.check_prices(data), [])
        self.assertIn("consumer.org.hk", data["sourceUrl"])
        self.assertRegex(data["checkedOn"], r"^\d{4}-\d{2}-\d{2}$")
        priced = [i for i in data["ingredients"].values() if i["products"]]
        self.assertGreaterEqual(len(priced), 30)
        unknown = [k for k, i in data["ingredients"].items() if not i["products"]]
        self.assertIn("spring_onion", unknown)  # not in the feed: shown as "price unknown", never guessed

    def test_check_refuses_bad_records(self):
        data = copy.deepcopy(PRICES)
        data["ingredients"]["egg"]["products"][0]["prices"]["WELLCOME"] = 25.0
        data["ingredients"]["rice"]["products"][0]["pack"] = 0
        del data["checkedOn"]
        problems = groceries.check_prices(data)
        self.assertEqual(len(problems), 3, problems)

    def test_recipes(self):
        recipes = groceries.load_recipes()
        prices = groceries.load_prices()
        self.assertGreaterEqual(len(recipes), 10)
        self.assertLessEqual(len(recipes), 15)
        self.assertEqual(len({r["id"] for r in recipes}), len(recipes))
        for recipe in recipes:
            with self.subTest(recipe=recipe["id"]):
                for ing, qty in recipe["ingredients"]:
                    self.assertIn(ing, prices["ingredients"])
                    self.assertGreater(qty, 0)
                result = groceries.basket(recipe, 2, prices, chain="WELLCOME")
                self.assertGreater(result["totalCents"], 0)

    def test_fares_are_sourced(self):
        fares = groceries.load_fares()
        for mode in ("taxi", "mtr"):
            self.assertTrue(fares[mode]["source"])
            self.assertTrue(fares[mode]["sourceUrl"].startswith("https://"))
            self.assertRegex(fares[mode]["checkedOn"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn("needsCheck", fares[mode])
