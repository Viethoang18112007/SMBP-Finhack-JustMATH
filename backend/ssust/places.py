"""Places from OpenStreetMap around one of five campuses (HKBU, HKUST, CUHK, HKU, CityU).

Live mode asks the Overpass API and falls back to the bundled offline
snapshot (data/places_snapshot.json) when that fails. Demo mode only reads the
snapshot. Every payload says where it came from in `source`.

Price bands: an OSM price tag wins (`priceSource` "tag"); otherwise food gets
an estimate from its type (`priceSource` "type"); anything else is unknown
("none"). Whether a band fits today's food left is decided in fit.py.
"""

import functools
import json
import math
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

# Campus centres, checked against OpenStreetMap on 2026-11-12. HKBU: midpoint of its two
# adjacent Kowloon Tong campuses. CityU: the main Tat Chee Avenue campus.
CAMPUSES = {
    "hkbu": {"id": "hkbu", "name": "HKBU", "lat": 22.3379, "lng": 114.1815},
    "hkust": {"id": "hkust", "name": "HKUST", "lat": 22.3380, "lng": 114.2630},
    "cuhk": {"id": "cuhk", "name": "CUHK", "lat": 22.4200, "lng": 114.2069},
    "hku": {"id": "hku", "name": "HKU", "lat": 22.2829, "lng": 114.1368},
    "cityu": {"id": "cityu", "name": "CityU", "lat": 22.3371, "lng": 114.1731},
}
DEFAULT_CAMPUS = "hkust"
CENTER = CAMPUSES[DEFAULT_CAMPUS]
RADIUS_KM = ("0.5", "1", "3", "5", "10")
KINDS = ("food", "shop")
EARTH_KM = 6371.0
OVERPASS_URLS = (
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
SHOW_LIMIT = 60
SNAPSHOT_FILE = Path(__file__).resolve().parent / "data" / "places_snapshot.json"
SNAPSHOT_RADIUS_KM = 10.0
SNAPSHOT_LIMIT = 300
ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"
SNAPSHOT_TAGS = ("name", "name:en", "amenity", "shop", "cuisine", "price_range", "price", "charge")

FILTERS = {
    "food": '["amenity"~"^(restaurant|cafe|fast_food|food_court)$"]',
    "shop": '["shop"~"^(supermarket|convenience|mall|department_store|marketplace|clothes|general)$"]',
}

_cache = {}
_lock = threading.Lock()
_PRICE_KEYS = ("price_range", "price", "charge")
_EXPENSIVE = {"expensive", "high", "pricey", "$$$", "$$$$"}
_CHEAP = {"cheap", "inexpensive", "low", "$"}
_NORMAL = {"normal", "moderate", "medium", "mid", "$$"}
# The estimate when there is no price tag. Only food types are listed.
TYPE_BANDS = {"fast_food": "cheap", "food_court": "cheap", "cafe": "cheap", "restaurant": "normal"}


def price_band(tags):
    """Cheap, normal, or expensive only when a map tag says so.

    A missing tag, a fee flag, or a brand name stays unknown. Amounts are not
    turned into a band. band_for adds the estimate from the place type.
    """
    parts = [str(tags.get(key)) for key in _PRICE_KEYS if tags.get(key)]
    tokens = {token for token in re.split(r"[\s,;/|]+", " ".join(parts).strip().lower()) if token}
    if tokens & _EXPENSIVE:
        return "expensive"
    if tokens & _CHEAP:
        return "cheap"
    if tokens & _NORMAL:
        return "normal"
    return "unknown"


def band_for(tags):
    """(band, source): the price tag ("tag"), else the estimate from the type ("type"), else ("unknown", "none")."""
    band = price_band(tags)
    if band != "unknown":
        return band, "tag"
    estimate = TYPE_BANDS.get(tags.get("amenity"))
    if estimate:
        return estimate, "type"
    return "unknown", "none"


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = (math.radians(v) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def _point(element):
    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return center["lat"], center["lon"]
    return None


def select_places(elements, kind, radius_km, center=CENTER):
    """Named places within `radius_km` of `center`, nearest first (at most SHOW_LIMIT), and the total."""
    found = []
    for element in elements:
        tags = element.get("tags") or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        point = _point(element)
        if not name or point is None:
            continue
        lat, lng = point
        distance = haversine_km(center["lat"], center["lng"], lat, lng)
        if distance > radius_km + 1e-9:
            continue
        detail = tags.get("cuisine") if kind == "food" else tags.get("shop")
        band, source = band_for(tags)
        found.append({
            "id": f"{element.get('type', 'node')}/{element.get('id', name)}",
            "name": name,
            "detail": (detail or "").replace(";", ", "),
            "lat": lat,
            "lng": lng,
            "distanceKm": round(distance, 2),
            "amenity": tags.get("amenity") or "",
            "price": band,
            "priceSource": source,
        })
    found.sort(key=lambda item: (item["distanceKm"], item["name"]))
    return found[:SHOW_LIMIT], len(found)


def fetch_elements(kind, radius_km, center=CENTER):
    """Raw Overpass elements of `kind` within `radius_km` of `center` (needs the internet)."""
    meters = int(radius_km * 1000)
    lat, lng = center["lat"], center["lng"]
    query = f"""
[out:json][timeout:25];
(
  node{FILTERS[kind]}(around:{meters},{lat},{lng});
  way{FILTERS[kind]}(around:{meters},{lat},{lng});
);
out center;
"""
    payload = None
    last_error = None
    body = query.encode("utf-8")
    for url in OVERPASS_URLS:
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "User-Agent": "SSUST-demo/1.0 (local student demo)",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                payload = json.load(response)
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
    if payload is None:
        raise last_error
    return payload.get("elements") or []


def fetch_places(kind, radius_km, campus=DEFAULT_CAMPUS):
    """Live places around `campus`, cached per (campus, kind, radius). Callers must not change the result."""
    center = CAMPUSES[campus]
    key = (campus, kind, radius_km)
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    places, total = select_places(fetch_elements(kind, radius_km, center), kind, radius_km, center)
    result = {
        "center": center,
        "kind": kind,
        "radiusKm": radius_km,
        "sample": False,
        "source": "OpenStreetMap",
        "shown": len(places),
        "total": total,
        "places": places,
    }
    with _lock:
        _cache[key] = result
    return result


def nearest_named(elements, center, limit=SNAPSHOT_LIMIT, radius_km=SNAPSHOT_RADIUS_KM):
    """The nearest `limit` named elements within `radius_km` of `center`, tags trimmed to SNAPSHOT_TAGS."""
    kept = []
    for element in elements:
        tags = element.get("tags") or {}
        point = _point(element)
        if point is None or not (tags.get("name:en") or tags.get("name") or "").strip():
            continue
        distance = haversine_km(center["lat"], center["lng"], *point)
        if distance > radius_km:
            continue
        kept.append((distance, {
            "type": element.get("type", "node"),
            "id": element["id"],
            "lat": float(point[0]),
            "lon": float(point[1]),
            "tags": {key: tags[key] for key in SNAPSHOT_TAGS if key in tags},
        }))
    kept.sort(key=lambda item: (item[0], item[1]["id"]))
    return [element for _distance, element in kept[:limit]]


def make_snapshot(elements_by_campus, fetched_at):
    """The snapshot file's content: per campus and kind, the nearest SNAPSHOT_LIMIT named places.

    `elements_by_campus` is {campus id: {kind: raw Overpass elements}}; campuses keep CAMPUSES order.
    """
    campuses = {}
    for campus_id, center in CAMPUSES.items():
        if campus_id not in elements_by_campus:
            continue
        by_kind = elements_by_campus[campus_id]
        campuses[campus_id] = {
            "center": center,
            "kinds": {kind: nearest_named(by_kind[kind], center) for kind in KINDS},
        }
    return {
        "fetchedAt": fetched_at,
        "attribution": ATTRIBUTION,
        "radiusKm": SNAPSHOT_RADIUS_KM,
        "limit": SNAPSHOT_LIMIT,
        "campuses": campuses,
    }


@functools.lru_cache(maxsize=1)
def load_snapshot(path=SNAPSHOT_FILE):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def snapshot_places(kind, radius_km, campus=DEFAULT_CAMPUS):
    """Places around `campus` from the offline snapshot, in the same shape as fetch_places."""
    data = load_snapshot()
    center = CAMPUSES[campus]
    places, total = select_places(data["campuses"][campus]["kinds"][kind], kind, radius_km, center)
    return {
        "center": center,
        "kind": kind,
        "radiusKm": radius_km,
        "sample": False,
        "source": "snapshot",
        "fetchedAt": data["fetchedAt"],
        "attribution": data["attribution"],
        "shown": len(places),
        "total": total,
        "places": places,
    }


def places_for(kind, radius_km, live, fetcher=fetch_places, campus=DEFAULT_CAMPUS):
    """Demo: the snapshot only. Live: `fetcher(kind, radius_km, campus)`, or the snapshot if that fails."""
    if live:
        try:
            return fetcher(kind, radius_km, campus)
        except Exception:
            pass
    return snapshot_places(kind, radius_km, campus)
