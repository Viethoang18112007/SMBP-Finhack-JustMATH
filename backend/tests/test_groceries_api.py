"""The Groceries mode of the Map tab over HTTP: stores, recipes, the plan (basket + trip + fit)."""

import json
import unittest

from ssust import groceries, places
from ssust.server import FRONTEND
from tests.test_api import ApiTest


def demo_stores(test, radius="3"):
    status, data = test.get(f"/api/places?kind=grocery&radius={radius}")
    test.assertEqual(status, 200, data)
    return data


class GroceryApi(ApiTest):
    def setUp(self):
        super().setUp()
        self.post("/api/mode", {"mode": "demo"})

    def get(self, path):
        status, _headers, body = self.request("GET", path)
        return status, json.loads(body)

    def post(self, path, body):
        status, _headers, raw = self.request("POST", path, body)
        return status, json.loads(raw)

    def test_stores_offline_in_demo(self):
        data = demo_stores(self)
        self.assertEqual(data["source"], "snapshot")
        self.assertGreater(len(data["places"]), 3)
        for store in data["places"]:
            self.assertIn(store["detail"], places.GROCERY_SHOPS | {"marketplace"})
            self.assertIn("chain", store)
        chains = {s["chain"] for s in data["places"]}
        self.assertTrue(chains & {"WELLCOME", "PARKNSHOP"}, chains)
        self.fetcher.assert_not_called()

    def test_catalogue_with_sources(self):
        status, data = self.get("/api/groceries")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["recipes"]), len(groceries.load_recipes()))
        self.assertIn("consumer.org.hk", data["prices"]["sourceUrl"])
        self.assertEqual(data["prices"]["checkedOn"], groceries.load_prices()["checkedOn"])
        self.assertIn("td.gov.hk", data["fares"]["taxi"]["sourceUrl"])
        self.assertIn("main", data["budget"])

    def plan(self, **body):
        base = {"recipe": "tomato_egg_rice", "servings": 2, "radius": "3", "mode": "walk", "fare": "student",
                "roundTrip": True, "includePantry": False}
        base.update(body)
        return self.post("/api/groceries/plan", base)

    def test_plan_two_stores(self):
        stores = demo_stores(self)["places"]
        wellcome = next(s for s in stores if s["chain"] == "WELLCOME")
        other = next(s for s in stores if s["chain"] != "WELLCOME")
        status, data = self.plan(stores=[wellcome["id"], other["id"]], mode="taxi")
        self.assertEqual(status, 200, data)
        self.assertEqual([s["id"] for s in data["stores"]], [wellcome["id"], other["id"]])
        first = data["stores"][0]
        self.assertEqual(first["basket"]["chain"], "WELLCOME")
        self.assertEqual(first["totalCents"], first["basket"]["totalCents"] + first["trip"]["cents"])
        self.assertTrue(first["trip"]["estimate"])
        self.assertIsNotNone(data["compare"])
        self.assertIn(data["fit"]["status"], ("fits", "over"))
        # The demo week has money in Main meals; the fit compares the groceries with it.
        self.assertEqual(data["fit"]["mainLeftCents"], data["budget"]["main"])

    def test_plan_without_a_store_uses_typical_prices(self):
        status, data = self.plan(stores=[])
        self.assertEqual(status, 200, data)
        self.assertEqual(data["stores"], [])
        self.assertEqual(data["basket"]["chain"], None)
        self.assertTrue(any(i["status"] == "unknown" for i in data["basket"]["items"]))  # spring onion

    def test_origin_changes_the_distance(self):
        stores = demo_stores(self)["places"]
        store = stores[0]
        _, near = self.plan(stores=[store["id"]], origin={"lat": store["lat"], "lng": store["lng"]})
        self.assertEqual(near["stores"][0]["distanceKm"], 0)

    def test_bad_plans(self):
        store = demo_stores(self)["places"][0]["id"]
        for body in ({"recipe": "caviar"}, {"servings": 0}, {"servings": 11}, {"servings": "2"},
                     {"mode": "helicopter"}, {"fare": "vip"}, {"roundTrip": "yes"}, {"radius": "7"},
                     {"stores": ["node/1", "node/2", "node/3"]}, {"stores": ["way/999999999999"]},
                     {"stores": [store, store]}, {"stores": "node/1"},
                     {"origin": {"lat": 51.5, "lng": -0.1}}, {"origin": {"lat": "22.3", "lng": 114.1}},
                     {"includePantry": 1}):
            with self.subTest(body=body):
                status, data = self.plan(**body)
                self.assertEqual(status, 400, data)

    def test_live_uses_the_fetcher_then_the_snapshot(self):
        self.post("/api/mode", {"mode": "live"})
        status, data = self.get("/api/places?kind=grocery&radius=1")
        self.assertEqual(status, 200)
        self.assertEqual(data["source"], "snapshot")  # the stub fetcher fails
        self.assertEqual(self.fetcher.call_args[0][0], "grocery")


class GroceryUi(unittest.TestCase):
    def setUp(self):
        self.map = (FRONTEND / "js" / "screens" / "map.js").read_text(encoding="utf-8")
        self.groc = (FRONTEND / "js" / "screens" / "groceries.js").read_text(encoding="utf-8")

    def test_mode_on_the_map(self):
        self.assertIn('data-kind="grocery"', self.map + self.groc)
        self.assertIn("groceriesPanel", self.map)

    def test_honest_labels(self):
        for needle in ("price unknown", "Estimate", "Source:", "groceries + trip", "Main meals"):
            self.assertIn(needle, self.groc)
        self.assertIn("/api/groceries/plan", (FRONTEND / "js" / "actions.js").read_text(encoding="utf-8")
                      + self.groc)
