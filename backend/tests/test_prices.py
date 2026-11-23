"""Verified dish prices: strict loading, matching to places, and the three honest states.

Every record below is an obviously fake test fixture ("Test Noodles A", example.test URLs).
The shipped data file has no records until real, sourced prices are added by hand.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ssust import fit, prices

GOOD = {
    "place": "Test Noodles A",
    "osm_id": "node/101",
    "dish": "Test dish",
    "price_cents": 4200,
    "currency": "HKD",
    "source": "https://example.test/menu-a",
    "verified_on": "2026-11-10",
    "campus": "hkust",
}


def place(pid, name, km, price="normal", source="type", lat=22.3380, lng=114.2630, amenity="restaurant"):
    return {"id": pid, "name": name, "distanceKm": km, "price": price, "priceSource": source,
            "lat": lat, "lng": lng, "amenity": amenity, "detail": ""}


class Validation(unittest.TestCase):
    def test_good_record(self):
        record, problem = prices.validate_record(GOOD)
        self.assertIsNone(problem)
        self.assertEqual(record["price_cents"], 4200)

    def test_coordinates_instead_of_an_osm_id(self):
        raw = {**GOOD, "lat": 22.3381, "lng": 114.2631}
        del raw["osm_id"]
        record, problem = prices.validate_record(raw)
        self.assertIsNone(problem)
        self.assertIsNone(record["osm_id"])

    def test_bad_records_are_rejected_with_a_reason(self):
        bad = [
            {k: v for k, v in GOOD.items() if k != "price_cents"},
            {**GOOD, "price_cents": 0},
            {**GOOD, "price_cents": -100},
            {**GOOD, "price_cents": 42.0},
            {**GOOD, "price_cents": "4200"},
            {**GOOD, "price_cents": True},
            {**GOOD, "price_cents": 10 ** 10},
            {**GOOD, "currency": "USD"},
            {**GOOD, "source": ""},
            {**GOOD, "source": "   "},
            {**GOOD, "verified_on": "2026-13-01"},
            {**GOOD, "verified_on": "10/11/2026"},
            {**GOOD, "campus": "mit"},
            {**GOOD, "osm_id": "node/abc"},
            {**GOOD, "place": ""},
            {**GOOD, "dish": None},
            {k: v for k, v in GOOD.items() if k != "osm_id"},  # neither an OSM id nor coordinates
            {**GOOD, "osm_id": None, "lat": 95, "lng": 114.2},
            {**GOOD, "price": 4200},  # unknown key (a typo of price_cents)
            "not a record",
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                record, problem = prices.validate_record(raw)
                self.assertIsNone(record)
                self.assertIsInstance(problem, str)
                self.assertTrue(problem)


class Loading(unittest.TestCase):
    def write(self, content):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "verified_prices.json"
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def test_good_records_load_and_bad_ones_are_reported(self):
        path = self.write({"records": [GOOD, {**GOOD, "price_cents": 0}, {**GOOD, "osm_id": "node/102"}]})
        records, problems = prices.load_verified(path)
        self.assertEqual([r["osm_id"] for r in records], ["node/101", "node/102"])
        self.assertEqual(len(problems), 1)
        self.assertIn("record 2", problems[0])

    def test_missing_file_is_empty(self):
        self.assertEqual(prices.load_verified(Path(tempfile.gettempdir()) / "no-such-ssust-file.json"), ([], []))

    def test_broken_file_is_reported(self):
        for content in ("{not json", json.dumps([GOOD]), json.dumps({"records": "x"})):
            with self.subTest(content=content):
                records, problems = prices.load_verified(self.write(content))
                self.assertEqual(records, [])
                self.assertEqual(len(problems), 1)

    def test_shipped_file_has_no_invented_prices(self):
        records, problems = prices.load_verified(prices.VERIFIED_FILE)
        self.assertEqual((records, problems), ([], []))
        self.assertTrue((prices.VERIFIED_FILE.parent / "VERIFIED_PRICES.md").is_file())


class Matching(unittest.TestCase):
    def test_normalized_names(self):
        self.assertEqual(prices.normalize_name("  McDonald's "), prices.normalize_name("mcdonalds"))
        self.assertEqual(prices.normalize_name("Café de Coral"), prices.normalize_name("CAFE DE CORAL"))
        self.assertNotEqual(prices.normalize_name("Cafe A"), prices.normalize_name("Cafe B"))

    def test_match_by_osm_id(self):
        records, _ = prices.validate_all([GOOD])
        self.assertEqual(len(prices.match_place(place("node/101", "Another name", 0.2), records)), 1)
        self.assertEqual(prices.match_place(place("node/999", "Another name", 0.2), records), [])

    def test_match_by_name_and_distance(self):
        near = {**GOOD, "osm_id": None, "lat": 22.3381, "lng": 114.2631}  # about 15 m away
        far = {**GOOD, "osm_id": None, "lat": 22.3420, "lng": 114.2630}  # about 450 m away
        records, _ = prices.validate_all([near])
        self.assertEqual(len(prices.match_place(place("node/5", "test noodles a", 0.1), records)), 1)
        self.assertEqual(prices.match_place(place("node/5", "Test Noodles B", 0.1), records), [])
        records, _ = prices.validate_all([far])
        self.assertEqual(prices.match_place(place("node/5", "Test Noodles A", 0.1), records), [])


class HonestStates(unittest.TestCase):
    """The P1.5 example: budget HK$60 | A verified 42 | B verified 55 | C estimated 50 to 120 | D verified 78."""

    def setUp(self):
        raw = [
            {**GOOD, "place": "Test A", "osm_id": "node/1", "price_cents": 4200},
            {**GOOD, "place": "Test B", "osm_id": "node/2", "price_cents": 5500, "source": "visited in person"},
            {**GOOD, "place": "Test D", "osm_id": "node/4", "price_cents": 7800},
        ]
        self.records, problems = prices.validate_all(raw)
        self.assertEqual(problems, [])
        # Distance order on purpose: the far verified-fit place must still come first.
        self.places = [place("node/4", "Test D", 0.1), place("node/3", "Test C", 0.2),
                       place("node/2", "Test B", 0.3), place("node/1", "Test A", 0.4)]

    def test_order_and_labels(self):
        out = fit.rank_places(self.places, 6000, self.records)
        self.assertEqual([p["name"] for p in out], ["Test A", "Test B", "Test C", "Test D"])
        self.assertEqual([p["status"] for p in out], ["fits", "fits", "estimate", "over"])
        self.assertEqual([p["label"] for p in out],
                         ["Fits", "Fits", "May fit (estimate)", "Over budget"])
        self.assertEqual(out[0]["why"],
                         "Verified HK$42 dish - fits your HK$60 | source: https://example.test/menu-a | checked 2026-11-10")
        self.assertEqual(out[1]["why"],
                         "Verified HK$55 dish - fits your HK$60 | source: visited in person | checked 2026-11-10")
        self.assertEqual(out[2]["why"], "Estimated HK$50 to HK$120 for a restaurant - not a real menu price")
        self.assertEqual(out[3]["why"],
                         "Verified HK$78 dish - HK$18 over your HK$60 | source: https://example.test/menu-a | checked 2026-11-10")
        self.assertEqual(out[0]["verified"], {"dish": "Test dish", "priceCents": 4200,
                                              "source": "https://example.test/menu-a", "verifiedOn": "2026-11-10"})
        self.assertIsNone(out[2]["verified"])

    def test_cheapest_verified_fit_first_then_nearest(self):
        raw = [{**GOOD, "osm_id": "node/1", "price_cents": 4200}, {**GOOD, "osm_id": "node/2", "price_cents": 4200}]
        records, _ = prices.validate_all(raw)
        out = fit.rank_places([place("node/1", "X", 0.9), place("node/2", "Y", 0.1)], 6000, records)
        self.assertEqual([p["name"] for p in out], ["Y", "X"])

    def test_a_place_with_several_verified_dishes_uses_the_cheapest(self):
        raw = [{**GOOD, "dish": "Big", "price_cents": 9000}, {**GOOD, "dish": "Small", "price_cents": 3000}]
        records, _ = prices.validate_all(raw)
        [out] = fit.rank_places([place("node/101", "Test Noodles A", 0.1)], 6000, records)
        self.assertEqual((out["status"], out["verified"]["dish"]), ("fits", "Small"))

    def test_an_estimate_never_fits(self):
        for band in ("cheap", "normal", "expensive", "unknown"):
            for remaining in (None, -100, 0, 1, 5000, 12000, 10 ** 8):
                with self.subTest(band=band, remaining=remaining):
                    [out] = fit.rank_places([place("node/9", "Z", 0.1, price=band)], remaining, [])
                    self.assertNotIn(out["status"], ("fits", "over"))
                    self.assertIsNone(out["verified"])
                    self.assertIn("not a real menu price", out["why"])
                    self.assertNotEqual(out["label"], "Fits")

    def test_estimate_that_cannot_fit_comes_before_verified_over(self):
        records, _ = prices.validate_all([{**GOOD, "osm_id": "node/1", "price_cents": 9000}])
        out = fit.rank_places([place("node/1", "Verified", 0.1), place("node/2", "Pricey", 0.2, price="expensive")],
                              6000, records)
        self.assertEqual([(p["name"], p["status"], p["label"]) for p in out],
                         [("Pricey", "unlikely", "Likely over (estimate)"), ("Verified", "over", "Over budget")])

    def test_no_budget_set(self):
        out = fit.rank_places(self.places, None, self.records)
        self.assertEqual({p["status"] for p in out}, {"verified", "estimate"})
        self.assertEqual([p["name"] for p in out], ["Test D", "Test C", "Test B", "Test A"])  # distance order

    def test_input_is_not_changed(self):
        before = json.dumps(self.places)
        fit.rank_places(self.places, 6000, self.records)
        self.assertEqual(json.dumps(self.places), before)


if __name__ == "__main__":
    unittest.main()
