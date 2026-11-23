"""Price ranges per person read on a public page: validation, fit at the boundaries, order."""

import json
import tempfile
import unittest
from pathlib import Path

from ssust import fit
from ssust.ranges import RANGES_FILE, counts_by_campus, load_ranges, validate_range

GOOD = {
    "place": "Sample Canteen", "campus": "hkbu", "osm_id": "node/1",
    "min_cents": 3000, "max_cents": 6000,
    "source_name": "Sample official menu", "source_url": "https://example.edu/menu.pdf", "checked_on": "2026-11-15",
}


def place(pid="node/1", name="Sample Canteen", band="cheap", km=0.1):
    return {"id": pid, "name": name, "price": band, "priceSource": "type", "amenity": "restaurant",
            "lat": 22.3, "lng": 114.1, "distanceKm": km}


class Validation(unittest.TestCase):
    def test_good_record(self):
        record, problem = validate_range(GOOD)
        self.assertIsNone(problem)
        self.assertEqual((record["min_cents"], record["max_cents"]), (3000, 6000))

    def test_bad_records_are_rejected_with_a_reason(self):
        cases = {
            "min_cents": {**GOOD, "min_cents": 0},
            "max_cents": {**GOOD, "max_cents": 60.5},
            "not be above": {**GOOD, "min_cents": 7000},
            "https": {**GOOD, "source_url": "http://example.edu/menu"},
            "checked_on": {**GOOD, "checked_on": "15/11/2026"},
            "campus": {**GOOD, "campus": "mit"},
            "osm_id": {**GOOD, "osm_id": "123"},
            "unknown": {**GOOD, "guess": True},
            "missing": {k: v for k, v in GOOD.items() if k != "source_name"},
            "lat and lng": {k: v for k, v in GOOD.items() if k != "osm_id"},
        }
        for words, raw in cases.items():
            with self.subTest(words=words):
                record, problem = validate_range(raw)
                self.assertIsNone(record)
                self.assertIn(words, problem)

    def test_shipped_file_is_clean_and_cited(self):
        records, problems = load_ranges(RANGES_FILE)
        self.assertEqual(problems, [])
        for record in records:
            self.assertTrue(record["source_url"].startswith("https://"))
        self.assertEqual(sum(counts_by_campus(records).values()), len(records))

    def test_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(load_ranges(path)[0], [])
            path.write_text(json.dumps({"records": [GOOD, {"place": "x"}]}), encoding="utf-8")
            records, problems = load_ranges(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(len(problems), 1)


class RangeFit(unittest.TestCase):
    def setUp(self):
        self.ranges = [validate_range(GOOD)[0]]

    def status(self, remaining):
        [item] = fit.rank_places([place()], remaining, [], self.ranges)
        return item

    def test_fits_when_the_top_is_within_today(self):
        item = self.status(6000)
        self.assertEqual(item["status"], "range_fits")
        self.assertEqual(item["label"], "Fits (HK$30 to HK$60, menu)")
        self.assertEqual(item["priceRange"]["sourceUrl"], GOOD["source_url"])

    def test_may_fit_between_min_and_max(self):
        self.assertEqual(self.status(5999)["status"], "range_may")
        item = self.status(3000)
        self.assertEqual((item["status"], item["label"]), ("range_may", "May fit (HK$30 to HK$60, menu)"))

    def test_over_below_min(self):
        item = self.status(2999)
        self.assertEqual((item["status"], item["label"]), ("range_over", "Over (HK$30 to HK$60, menu)"))

    def test_no_budget(self):
        self.assertEqual(self.status(None)["status"], "range")

    def test_verified_price_still_wins(self):
        verified = [{"osm_id": "node/1", "lat": None, "lng": None, "name_key": "samplecanteen", "dish": "Rice",
                     "price_cents": 4000, "source": "menu", "verified_on": "2026-11-15"}]
        [item] = fit.rank_places([place()], 5000, verified, self.ranges)
        self.assertEqual(item["status"], "fits")

    def test_no_range_keeps_the_estimate(self):
        [item] = fit.rank_places([place(pid="node/2", name="Other")], 5000, [], self.ranges)
        self.assertEqual(item["status"], "estimate")

    def test_order_fits_may_fit_estimates_likely_over(self):
        ranges = [validate_range({**GOOD, "osm_id": f"node/{i}", "place": f"P{i}", "min_cents": lo, "max_cents": hi})[0]
                  for i, lo, hi in ((1, 1000, 2000), (2, 3000, 9000), (3, 9000, 12000))]
        places = [place("node/3", "P3", km=0.1), place("node/4", "Est", km=0.2), place("node/2", "P2", km=0.3),
                  place("node/1", "P1", km=0.4)]
        ranked = fit.rank_places(places, 5000, [], ranges)
        self.assertEqual([p["status"] for p in ranked], ["range_fits", "range_may", "estimate", "range_over"])


def chain(low, high, name="Test Chain"):
    from ssust import prices
    record, problem = prices.validate_chain({"chain": name, "names": [name], "what": "Sets", "low_cents": low,
                                             "high_cents": high, "sources": ["https://example.test/chain"],
                                             "checked_on": "2026-11-15", "needs_check": True})
    assert problem is None, problem
    return record


class MergedPriority(unittest.TestCase):
    """One place: verified dish > its own menu range > its chain price > estimate."""

    def test_menu_range_beats_the_chain_price(self):
        ranges = [validate_range(GOOD)[0]]
        [item] = fit.rank_places([place(name="Sample Canteen")], 5000, [], ranges, chains=[chain(100, 200, "Sample Canteen")])
        self.assertEqual(item["status"], "range_may")
        self.assertIsNone(item["chain"])
        self.assertIsNotNone(item["priceRange"])

    def test_chain_price_beats_the_estimate(self):
        [item] = fit.rank_places([place(pid="node/7", name="Test Chain Kowloon")], 5000, [], [], chains=[chain(3000, 4000)])
        self.assertEqual((item["status"], item["label"]), ("chain_fits", "Fits (chain price)"))
        self.assertIsNone(item["priceRange"])

    def test_chain_boundaries(self):
        record = chain(3000, 6000)
        for remaining, status, label in ((6000, "chain_fits", "Fits (chain price)"),
                                         (5999, "chain_tight", "May fit (chain price)"),
                                         (3000, "chain_tight", "May fit (chain price)"),
                                         (2999, "chain_over", "Over (chain price)")):
            with self.subTest(remaining=remaining):
                [item] = fit.rank_places([place(pid="node/8", name="Test Chain")], remaining, [], [], chains=[record])
                self.assertEqual((item["status"], item["label"]), (status, label))

    def test_full_order(self):
        verified = [
            {"osm_id": "node/10", "lat": None, "lng": None, "name_key": "vfits", "dish": "Rice", "price_cents": 4000,
             "source": "menu", "verified_on": "2026-11-15"},
            {"osm_id": "node/19", "lat": None, "lng": None, "name_key": "vover", "dish": "Set", "price_cents": 9000,
             "source": "menu", "verified_on": "2026-11-15"},
        ]
        ranges = [validate_range({**GOOD, "osm_id": f"node/{i}", "place": f"R{i}", "min_cents": lo, "max_cents": hi})[0]
                  for i, lo, hi in ((11, 1000, 2000), (13, 3000, 9000), (18, 9000, 12000))]
        chains = [chain(2000, 3000, "Chainfit"), chain(4000, 8000, "Chainmay"), chain(9500, 9900, "Chainover")]
        places = [
            place("node/19", "VOver", km=0.01), place("node/18", "R18", km=0.02),
            place("node/30", "Chainover Shop", km=0.03), place("node/17", "Unknown", km=0.04),
            place("node/16", "Dear", km=0.05), place("node/15", "Cheap", km=0.06),
            place("node/14", "Chainmay Shop", km=0.07), place("node/13", "R13", km=0.08),
            place("node/12", "Chainfit Shop", km=0.09), place("node/11", "R11", km=0.10),
            place("node/10", "VFits", km=0.11),
        ]
        places[3]["price"] = None
        places[4]["price"] = "expensive"
        ranked = fit.rank_places(places, 5000, verified, ranges, chains=chains)
        self.assertEqual([p["status"] for p in ranked],
                         ["fits", "range_fits", "chain_fits", "range_may", "chain_tight", "estimate", "unlikely",
                          "unknown", "range_over", "chain_over", "over"])


if __name__ == "__main__":
    unittest.main()
