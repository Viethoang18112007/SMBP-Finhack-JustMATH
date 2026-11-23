"""Price ranges per person, read on a public page (a menu or a listing). Integer cents, HKD.

Each record in data/price_ranges.json says which place it is, the lowest and highest price
per person as printed on the page, the page (source_name, source_url) and the day it was read
(checked_on). A record is added only when the range was read on that page; nothing is guessed.
Every record is checked strictly; a bad record is rejected with a reason and never used.
Records match map places like verified prices do (prices.match_place: OSM id, or the same name
within prices.MATCH_KM of the record's point).
"""

import json
from pathlib import Path

from .dates import parse_day
from .places import CAMPUSES
from .prices import _OSM_ID, _coordinate, _text, normalize_name
from .validate import MAX_CENTS

RANGES_FILE = Path(__file__).resolve().parent / "data" / "price_ranges.json"
REQUIRED = ("place", "campus", "min_cents", "max_cents", "source_name", "source_url", "checked_on")
OPTIONAL = ("osm_id", "lat", "lng", "note")


def validate_range(raw):
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
        low, high = raw["min_cents"], raw["max_cents"]
        for key, value in (("min_cents", low), ("max_cents", high)):
            if type(value) is not int or not 0 < value <= MAX_CENTS:
                raise ValueError(f"{key} must be a whole number of cents above 0")
        if low > high:
            raise ValueError("min_cents must not be above max_cents")
        url = raw["source_url"]
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 400 or any(c.isspace() for c in url):
            raise ValueError("source_url must be an https:// link")
        try:
            checked = parse_day(raw["checked_on"]).isoformat()
        except ValueError:
            raise ValueError("checked_on must be a date like 2026-11-15") from None
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
        note = raw.get("note")
        if note is not None:
            note = _text(raw, "note", 200)
        record = {
            "place": _text(raw, "place"),
            "campus": raw["campus"],
            "osm_id": osm_id,
            "lat": lat,
            "lng": lng,
            "min_cents": low,
            "max_cents": high,
            "source_name": _text(raw, "source_name"),
            "source_url": url,
            "checked_on": checked,
            "note": note,
        }
        record["name_key"] = normalize_name(record["place"])
        return record, None
    except ValueError as exc:
        return None, str(exc)


def validate_ranges(raws):
    records, problems = [], []
    for number, raw in enumerate(raws, 1):
        record, problem = validate_range(raw)
        if problem:
            problems.append(f"record {number}: {problem}")
        else:
            records.append(record)
    return records, problems


def load_ranges(path=RANGES_FILE):
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
    return validate_ranges(data["records"])


def counts_by_campus(records):
    counts = {campus: 0 for campus in CAMPUSES}
    for record in records:
        counts[record["campus"]] += 1
    return counts
