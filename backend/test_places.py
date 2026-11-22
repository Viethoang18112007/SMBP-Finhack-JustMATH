import math
import unittest
from places import CENTER, EARTH_KM, haversine_km, select_places


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


if __name__ == "__main__":
    unittest.main()
