"""Regenerate the offline places snapshot (needs the internet; run by hand).

    python tools/make_places_snapshot.py

For each campus (HKBU, HKUST, CUHK, HKU, CityU) and each kind (food, shops),
keeps the nearest 300 named places within 10 km and writes
backend/ssust/data/places_snapshot.json with the fetch date and the ODbL
attribution. Demo mode and the live fallback read that file.

Gentle on the public Overpass servers: one request at a time, a pause after
each one, and small circles first (2 km, then 5, then 10 km only when the
smaller circle has fewer than 300 named places; the nearest 300 inside a
smaller circle are also the nearest 300 inside 10 km). If a request fails,
nothing is written and the old file stays.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ssust import places  # noqa: E402

PAUSE_SECONDS = 8
STEPS_KM = (2.0, 5.0, places.SNAPSHOT_RADIUS_KM)


def fetch_nearest(kind, center):
    for radius in STEPS_KM:
        print(f"  {kind} within {radius:g} km...", flush=True)
        elements = places.fetch_elements(kind, radius, center)
        time.sleep(PAUSE_SECONDS)
        named = places.nearest_named(elements, center, radius_km=radius)
        if len(named) >= places.SNAPSHOT_LIMIT or radius >= places.SNAPSHOT_RADIUS_KM:
            return elements
    return elements


def main():
    elements = {}
    for campus_id, center in places.CAMPUSES.items():
        print(f"{center['name']}:", flush=True)
        elements[campus_id] = {kind: fetch_nearest(kind, center) for kind in places.KINDS}
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    snapshot = places.make_snapshot(elements, fetched_at)
    places.SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    places.SNAPSHOT_FILE.write_text(text, encoding="utf-8", newline="\n")
    for campus_id, campus in snapshot["campuses"].items():
        counts = ", ".join(f"{kind} {len(campus['kinds'][kind])}" for kind in places.KINDS)
        print(f"{campus_id}: {counts}")
    print(f"Wrote {places.SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()
