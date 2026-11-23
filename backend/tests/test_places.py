import math
import re
import unittest
import urllib.error
from unittest import mock

from ssust.places import (CAMPUSES, CENTER, DEFAULT_CAMPUS, EARTH_KM, KINDS, SNAPSHOT_LIMIT,
                          SNAPSHOT_RADIUS_KM, band_for, haversine_km, load_snapshot, make_snapshot,
                          places_for, select_places, snapshot_places)


class Places(unittest.TestCase):
    def test_latitude_step_matches_the_earth_radius(self):
        expected = EARTH_KM * math.radians(0.008)
        got = haversine_km(CENTER["lat"], CENTER["lng"], CENTER["lat"] + 0.008, CENTER["lng"])
        self.assertAlmostEqual(got, expected, delta=0.01)

    def test_select_keeps_named_places_inside_the_radius(self):
        elements = [
            {"type": "node", "id": 1, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "Campus Cafe", "cuisine": "noodles"}},
            {"type": "node", "id": 2, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"cuisine": "ramen"}},
            {"type": "node", "id": 3, "lat": CENTER["lat"] + 0.05, "lon": CENTER["lng"], "tags": {"name": "Far Cafe"}},
            {"type": "way", "id": 4, "center": {"lat": CENTER["lat"] + 0.002, "lon": CENTER["lng"]}, "tags": {"name": "Mall Canteen"}},
        ]
        places, total = select_places(elements, "food", 1)
        self.assertEqual(total, 2)
        self.assertEqual([place["name"] for place in places], ["Campus Cafe", "Mall Canteen"])
        self.assertEqual(places[0]["detail"], "noodles")
        self.assertEqual(places[0]["price"], "unknown")

    def test_price_band_uses_only_an_explicit_label(self):
        elements = [
            {"type": "node", "id": 1, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "A", "price_range": "cheap"}},
            {"type": "node", "id": 2, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "B", "price": "expensive"}},
            {"type": "node", "id": 3, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "C", "price_range": "$$"}},
            {"type": "node", "id": 4, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "D", "fee": "yes"}},
            {"type": "node", "id": 5, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "E", "brand": "McDonald's"}},
        ]
        places, _total = select_places(elements, "food", 1)
        self.assertEqual(
            {place["name"]: place["price"] for place in places},
            {"A": "cheap", "B": "expensive", "C": "normal", "D": "unknown", "E": "unknown"},
        )



class Campuses(unittest.TestCase):
    # Checked against OpenStreetMap on 2026-11-12 (campus areas; HKBU is the midpoint of its
    # two adjacent Kowloon Tong campuses, CityU its main Tat Chee Avenue campus).
    OSM = {
        "hkbu": (22.3379, 114.1815),
        "hkust": (22.3380, 114.2630),
        "cuhk": (22.4200, 114.2069),
        "hku": (22.2829, 114.1368),
        "cityu": (22.3371, 114.1731),
    }

    def test_the_five_campuses(self):
        self.assertEqual(list(CAMPUSES), ["hkbu", "hkust", "cuhk", "hku", "cityu"])
        self.assertEqual([c["name"] for c in CAMPUSES.values()], ["HKBU", "HKUST", "CUHK", "HKU", "CityU"])
        self.assertEqual(DEFAULT_CAMPUS, "hkust")
        self.assertEqual(CENTER, CAMPUSES["hkust"])
        for campus_id, campus in CAMPUSES.items():
            with self.subTest(campus=campus_id):
                self.assertEqual(campus["id"], campus_id)
                lat, lng = self.OSM[campus_id]
                self.assertLess(haversine_km(campus["lat"], campus["lng"], lat, lng), 0.05)

    def test_distances_are_measured_from_the_chosen_campus(self):
        for campus_id, campus in CAMPUSES.items():
            with self.subTest(campus=campus_id):
                elements = [
                    {"type": "node", "id": 1, "lat": campus["lat"], "lon": campus["lng"], "tags": {"name": "Here"}},
                    {"type": "node", "id": 2, "lat": campus["lat"] + 0.009, "lon": campus["lng"],
                     "tags": {"name": "North"}},
                ]
                found, total = select_places(elements, "food", 3, campus)
                self.assertEqual(total, 2)
                self.assertEqual([(p["name"], p["distanceKm"]) for p in found], [("Here", 0.0), ("North", 1.0)])


class BandFor(unittest.TestCase):
    def test_type_estimate_when_there_is_no_price_tag(self):
        for amenity, band in (("fast_food", "cheap"), ("food_court", "cheap"), ("cafe", "cheap"),
                              ("restaurant", "normal")):
            with self.subTest(amenity=amenity):
                self.assertEqual(band_for({"amenity": amenity}), (band, "type"))

    def test_a_price_tag_always_wins(self):
        self.assertEqual(band_for({"amenity": "fast_food", "price_range": "expensive"}), ("expensive", "tag"))
        self.assertEqual(band_for({"amenity": "restaurant", "price": "$"}), ("cheap", "tag"))
        self.assertEqual(band_for({"price_range": "$$"}), ("normal", "tag"))

    def test_no_tag_and_no_known_type_is_unknown(self):
        for tags in ({}, {"amenity": "bar"}, {"shop": "supermarket"}, {"amenity": "pub", "brand": "X"}):
            with self.subTest(tags=tags):
                self.assertEqual(band_for(tags), ("unknown", "none"))

    def test_select_reports_the_price_source_and_amenity(self):
        elements = [
            {"type": "node", "id": 1, "lat": CENTER["lat"], "lon": CENTER["lng"],
             "tags": {"name": "Tagged", "amenity": "fast_food", "price_range": "expensive"}},
            {"type": "node", "id": 2, "lat": CENTER["lat"], "lon": CENTER["lng"],
             "tags": {"name": "Guessed", "amenity": "restaurant"}},
            {"type": "node", "id": 3, "lat": CENTER["lat"], "lon": CENTER["lng"], "tags": {"name": "Bare"}},
        ]
        found, _total = select_places(elements, "food", 1)
        self.assertEqual(
            {p["name"]: (p["price"], p["priceSource"], p["amenity"]) for p in found},
            {"Tagged": ("expensive", "tag", "fast_food"), "Guessed": ("normal", "type", "restaurant"),
             "Bare": ("unknown", "none", "")},
        )


class Snapshot(unittest.TestCase):
    """The bundled offline snapshot. Never touches the network."""

    def test_snapshot_has_the_required_fields(self):
        data = load_snapshot()
        self.assertRegex(data["fetchedAt"], r"^[0-9]{4}-[0-9]{2}-[0-9]{2}")
        self.assertIn("OpenStreetMap", data["attribution"])
        self.assertIn("ODbL", data["attribution"])
        self.assertEqual(data["radiusKm"], SNAPSHOT_RADIUS_KM)
        self.assertEqual(list(data["campuses"]), list(CAMPUSES))
        for campus_id, campus in CAMPUSES.items():
            self.assertEqual(data["campuses"][campus_id]["center"], campus)
            self.assertEqual(set(data["campuses"][campus_id]["kinds"]), set(KINDS))
            for kind in KINDS:
                elements = data["campuses"][campus_id]["kinds"][kind]
                with self.subTest(campus=campus_id, kind=kind):
                    self.assertTrue(0 < len(elements) <= SNAPSHOT_LIMIT)
                    for element in elements:
                        self.assertIn(element["type"], ("node", "way"))
                        self.assertIsInstance(element["id"], int)
                        self.assertIsInstance(element["lat"], float)
                        self.assertIsInstance(element["lon"], float)
                        self.assertTrue(element["tags"].get("name:en") or element["tags"].get("name"))
                        if kind == "food":
                            self.assertIn("amenity", element["tags"])
                    distances = [haversine_km(campus["lat"], campus["lng"], e["lat"], e["lon"]) for e in elements]
                    self.assertLessEqual(max(distances), SNAPSHOT_RADIUS_KM + 1e-9)

    def test_radius_filter_on_snapshot_data(self):
        for kind in KINDS:
            totals = []
            for radius in (0.5, 1.0, 3.0, 10.0):
                with self.subTest(kind=kind, radius=radius):
                    data = snapshot_places(kind, radius)
                    self.assertEqual((data["source"], data["kind"], data["radiusKm"]), ("snapshot", kind, radius))
                    self.assertEqual(data["center"], CENTER)
                    self.assertTrue(data["fetchedAt"])
                    self.assertIn("ODbL", data["attribution"])
                    self.assertEqual(data["shown"], len(data["places"]))
                    self.assertTrue(all(p["distanceKm"] <= radius for p in data["places"]))
                    totals.append(data["total"])
            self.assertEqual(totals, sorted(totals))
            self.assertGreater(totals[-1], 0)

    def test_every_campus_has_food_and_shops_nearby(self):
        for campus_id, campus in CAMPUSES.items():
            for kind in KINDS:
                with self.subTest(campus=campus_id, kind=kind):
                    data = snapshot_places(kind, 3.0, campus_id)
                    self.assertEqual(data["center"], campus)
                    self.assertGreater(data["total"], 0)
                    for place in data["places"]:
                        self.assertIn(place["priceSource"], ("tag", "type", "none"))
                        if kind == "food":
                            self.assertNotEqual(place["priceSource"], "none")

    def test_make_snapshot_keeps_the_nearest_named_places_per_campus(self):
        hkbu, hku = CAMPUSES["hkbu"], CAMPUSES["hku"]

        def node(i, campus, dlat, name="N"):
            return {"type": "node", "id": i, "lat": campus["lat"] + dlat, "lon": campus["lng"],
                    "tags": {"name": name, "amenity": "cafe", "opening_hours": "24/7"}}

        elements = {
            "hkbu": {"food": [node(2, hkbu, 0.002), node(1, hkbu, 0.001), node(3, hkbu, 0.2), node(4, hkbu, 0, "")],
                     "shop": []},
            "hku": {"food": [node(5, hku, 0.0)], "shop": []},
        }
        snap = make_snapshot(elements, "2026-11-12T00:00:00+00:00")
        self.assertEqual(list(snap["campuses"]), ["hkbu", "hku"])
        self.assertEqual(snap["campuses"]["hkbu"]["center"], hkbu)
        self.assertEqual([e["id"] for e in snap["campuses"]["hkbu"]["kinds"]["food"]], [1, 2])
        self.assertEqual(snap["campuses"]["hkbu"]["kinds"]["food"][0]["tags"], {"name": "N", "amenity": "cafe"})
        self.assertEqual([e["id"] for e in snap["campuses"]["hku"]["kinds"]["food"]], [5])


class PlacesFor(unittest.TestCase):
    LIVE = {"source": "OpenStreetMap", "kind": "food", "places": []}

    def test_demo_never_calls_the_fetcher(self):
        fetcher = mock.Mock(side_effect=AssertionError("network"))
        data = places_for("food", 3.0, live=False, fetcher=fetcher, campus="cuhk")
        self.assertEqual(data["source"], "snapshot")
        self.assertEqual(data["center"], CAMPUSES["cuhk"])
        fetcher.assert_not_called()

    def test_live_uses_the_fetcher(self):
        fetcher = mock.Mock(return_value=self.LIVE)
        self.assertEqual(places_for("food", 3.0, live=True, fetcher=fetcher, campus="hku"), self.LIVE)
        fetcher.assert_called_once_with("food", 3.0, "hku")

    def test_live_falls_back_when_the_fetcher_fails(self):
        for error in (urllib.error.URLError("offline"), TimeoutError(), OSError(), ValueError(), RuntimeError()):
            with self.subTest(error=type(error).__name__):
                data = places_for("shop", 1.0, live=True, fetcher=mock.Mock(side_effect=error), campus="cityu")
                self.assertEqual((data["source"], data["kind"], data["radiusKm"]), ("snapshot", "shop", 1.0))
                self.assertEqual(data["center"], CAMPUSES["cityu"])


if __name__ == "__main__":
    unittest.main()
