"""Verified dish prices, typed in by hand from a real menu or a visit. Integer cents, HKD.

The data file (data/verified_prices.json) ships with no records: a price is only
added when someone has read it on a real menu or paid it in person, with the
source and the date. See data/VERIFIED_PRICES.md for the record format.

Every record is checked strictly. A bad record is rejected with a reason and
never used. A record applies to a map place by its OpenStreetMap id, or by the
same normalized name within MATCH_KM of the record's coordinates.
"""

import json
import re
import unicodedata
from pathlib import Path

from .dates import parse_day
from .places import CAMPUSES, haversine_km
from .validate import MAX_CENTS

VERIFIED_FILE = Path(__file__).resolve().parent / "data" / "verified_prices.json"
MATCH_KM = 0.15  # same name within 150 m counts as the same place
REQUIRED = ("place", "dish", "price_cents", "currency", "source", "verified_on", "campus")
OPTIONAL = ("osm_id", "lat", "lng", "note")
_OSM_ID = re.compile(r"(node|way|relation)/[0-9]{1,15}")
_MAX_TEXT = 300


def _text(raw, key, limit=80):
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    if len(value) > limit:
        raise ValueError(f"{key} is longer than {limit} characters")
    return value.strip()


def _coordinate(raw, key, bound):
    value = raw.get(key)
    if type(value) not in (int, float) or not -bound <= value <= bound:
        raise ValueError(f"{key} must be a number between -{bound} and {bound}")
    return float(value)


def validate_record(raw):
    """(record, None) for a usable record, or (None, reason)."""
    try:
        if not isinstance(raw, dict):
            raise ValueError("a record must be an object")
        unknown = sorted(set(raw) - set(REQUIRED) - set(OPTIONAL))
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(unknown)}")
        missing = [key for key in REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"missing field(s): {', '.join(missing)}")
        price = raw["price_cents"]
        if type(price) is not int or not 0 < price <= MAX_CENTS:
            raise ValueError("price_cents must be a whole number of cents above 0")
        if raw["currency"] != "HKD":
            raise ValueError("currency must be HKD")
        try:
            verified_on = parse_day(raw["verified_on"]).isoformat()
        except ValueError:
            raise ValueError("verified_on must be a date like 2026-11-10") from None
        if raw["campus"] not in CAMPUSES:
            raise ValueError(f"campus must be one of {', '.join(CAMPUSES)}")
        osm_id = raw.get("osm_id")
        if osm_id is not None and not (isinstance(osm_id, str) and _OSM_ID.fullmatch(osm_id)):
            raise ValueError("osm_id must look like node/123, way/123 or relation/123")
        has_point = raw.get("lat") is not None or raw.get("lng") is not None
        lat = _coordinate(raw, "lat", 90) if has_point else None
        lng = _coordinate(raw, "lng", 180) if has_point else None
        if osm_id is None and lat is None:
            raise ValueError("give an osm_id, or lat and lng, so the record can be matched to a place")
        record = {
            "place": _text(raw, "place"),
            "osm_id": osm_id,
            "lat": lat,
            "lng": lng,
            "dish": _text(raw, "dish"),
            "price_cents": price,
            "currency": "HKD",
            "source": _text(raw, "source", _MAX_TEXT),
            "verified_on": verified_on,
            "campus": raw["campus"],
        }
        record["name_key"] = normalize_name(record["place"])
        return record, None
    except ValueError as exc:
        return None, str(exc)


def validate_all(raws):
    """(records, problems) for a list of raw records; problems name the record by position (from 1)."""
    records, problems = [], []
    for number, raw in enumerate(raws, 1):
        record, problem = validate_record(raw)
        if problem:
            problems.append(f"record {number}: {problem}")
        else:
            records.append(record)
    return records, problems


def load_verified(path=VERIFIED_FILE):
    """(records, problems) from the data file. A missing file is simply empty."""
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name}: could not read it as JSON ({exc.__class__.__name__})"]
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        return [], [f'{path.name}: expected {{"records": [...]}}']
    return validate_all(data["records"])


def normalize_name(name):
    """Case, accents, punctuation and spacing ignored: "Café de Coral" == "CAFE DE CORAL"."""
    text = unicodedata.normalize("NFKD", str(name)).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text if ch.isalnum())


def match_place(place, records):
    """The verified records that apply to `place` (by OSM id, or same name within MATCH_KM)."""
    key = normalize_name(place.get("name", ""))
    found = []
    for record in records:
        if record["osm_id"] is not None and record["osm_id"] == place.get("id"):
            found.append(record)
        elif (record["lat"] is not None and key and record["name_key"] == key
              and "lat" in place and "lng" in place
              and haversine_km(record["lat"], record["lng"], place["lat"], place["lng"]) <= MATCH_KM):
            found.append(record)
    return found


# Chain prices: one typical meal range per chain, from published prices, used for every
# branch whose name contains one of the chain's names. Less exact than a verified dish
# (a branch can differ), so the map labels them as chain prices. Format: CHAIN_PRICES.md.

CHAIN_FILE = Path(__file__).resolve().parent / "data" / "chain_prices.json"
CHAIN_REQUIRED = ("chain", "names", "what", "low_cents", "high_cents", "sources", "checked_on", "needs_check")
CHAIN_OPTIONAL = ("note",)
_MIN_NAME_KEY = 2  # a name shorter than this would match far too many places


def validate_chain(raw):
    """(chain, None) for a usable chain record, or (None, reason)."""
    try:
        if not isinstance(raw, dict):
            raise ValueError("a chain must be an object")
        unknown = sorted(set(raw) - set(CHAIN_REQUIRED) - set(CHAIN_OPTIONAL))
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(unknown)}")
        missing = [key for key in CHAIN_REQUIRED if key not in raw]
        if missing:
            raise ValueError(f"missing field(s): {', '.join(missing)}")
        names = raw["names"]
        if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
            raise ValueError("names must be a list of non-empty names")
        keys = [normalize_name(n) for n in names]
        if any(len(key) < _MIN_NAME_KEY for key in keys):
            raise ValueError(f"each name needs at least {_MIN_NAME_KEY} letters or digits")
        low, high = raw["low_cents"], raw["high_cents"]
        for key, value in (("low_cents", low), ("high_cents", high)):
            if type(value) is not int or not 0 < value <= MAX_CENTS:
                raise ValueError(f"{key} must be a whole number of cents above 0")
        if low > high:
            raise ValueError("low_cents must not be above high_cents")
        sources = raw["sources"]
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s.strip() for s in sources):
            raise ValueError("sources must list at least one URL or 'visited in person'")
        try:
            checked_on = parse_day(raw["checked_on"]).isoformat()
        except ValueError:
            raise ValueError("checked_on must be a date like 2026-11-15") from None
        if type(raw["needs_check"]) is not bool:
            raise ValueError("needs_check must be true or false")
        return {
            "chain": _text(raw, "chain"),
            "keys": keys,
            "what": _text(raw, "what"),
            "low_cents": low,
            "high_cents": high,
            "sources": [s.strip() for s in sources],
            "checked_on": checked_on,
            "needs_check": raw["needs_check"],
        }, None
    except ValueError as exc:
        return None, str(exc)


def load_chains(path=CHAIN_FILE):
    """(chains, problems) from the chain file. A missing file is simply empty."""
    path = Path(path)
    if not path.is_file():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name}: could not read it as JSON ({exc.__class__.__name__})"]
    if not isinstance(data, dict) or not isinstance(data.get("chains"), list):
        return [], [f'{path.name}: expected {{"chains": [...]}}']
    chains, problems = [], []
    for number, raw in enumerate(data["chains"], 1):
        chain, problem = validate_chain(raw)
        if problem:
            problems.append(f"chain {number}: {problem}")
        else:
            chains.append(chain)
    return chains, problems


def match_chain(place, chains):
    """The chain whose name appears in the place's name (case, accents, punctuation ignored), or None.

    The longest matching name wins, so "TamJai SamGor" beats a shorter name of another chain.
    """
    key = normalize_name(place.get("name", ""))
    if not key:
        return None
    best, best_len = None, 0
    for chain in chains:
        for name_key in chain["keys"]:
            if name_key in key and len(name_key) > best_len:
                best, best_len = chain, len(name_key)
    return best
