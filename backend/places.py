"""Live places from OpenStreetMap, centred on HKUST.

Names and coordinates come from the Overpass API. There is no Google scrape
and no taste or price score, because OpenStreetMap does not provide one.
"""

import json
import math
import re
import threading
import urllib.error
import urllib.request

CENTER = {"name": "HKUST", "lat": 22.3380, "lng": 114.2630}
RADIUS_KM = ("0.5", "1", "3", "5", "10")
KINDS = ("food", "shop")
EARTH_KM = 6371.0
OVERPASS_URLS = (
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
SHOW_LIMIT = 60

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


def price_band(tags):
    """Cheap, normal, or expensive only when a map tag says so.

    A missing tag, a fee flag, or a brand name stays unknown. The screen
    draws that as blue. Amounts are not turned into a band.
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


def select_places(elements, kind, radius_km):
    found = []
    for element in elements:
        tags = element.get("tags") or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        point = _point(element)
        if not name or point is None:
            continue
        lat, lng = point
        distance = haversine_km(CENTER["lat"], CENTER["lng"], lat, lng)
        if distance > radius_km + 1e-9:
            continue
        detail = tags.get("cuisine") if kind == "food" else tags.get("shop")
        found.append({
            "id": f"{element.get('type', 'node')}/{element.get('id', name)}",
            "name": name,
            "detail": (detail or "").replace(";", ", "),
            "lat": lat,
            "lng": lng,
            "distanceKm": round(distance, 2),
            "price": price_band(tags),
        })
    found.sort(key=lambda item: (item["distanceKm"], item["name"]))
    return found[:SHOW_LIMIT], len(found)


def fetch_places(kind, radius_km):
    key = (kind, radius_km)
    with _lock:
        cached = _cache.get(key)
    if cached is not None:
        return cached
    meters = int(radius_km * 1000)
    query = f"""
[out:json][timeout:25];
(
  node{FILTERS[kind]}(around:{meters},{CENTER["lat"]},{CENTER["lng"]});
  way{FILTERS[kind]}(around:{meters},{CENTER["lat"]},{CENTER["lng"]});
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
    places, total = select_places(payload.get("elements") or [], kind, radius_km)
    result = {
        "center": CENTER,
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
