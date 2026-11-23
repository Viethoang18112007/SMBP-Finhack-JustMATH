# Verified dish prices

`verified_prices.json` holds real dish prices that someone has checked by hand. It ships
**empty**. Add a record only for a price you read on a real menu (photo, printed menu, the
restaurant's own website) or paid in person. Never guess, never copy an estimate, never
reuse an old price without checking it again.

## Record format

```json
{
  "records": [
    {
      "place": "<name as written on the shop sign or menu>",
      "osm_id": "<node/123456789, from the OpenStreetMap link of the place, or null>",
      "lat": <latitude, only needed when there is no osm_id>,
      "lng": <longitude, only needed when there is no osm_id>,
      "dish": "<the dish, as written on the menu>",
      "price_cents": <price in whole cents: HK$42.50 is 4250>,
      "currency": "HKD",
      "source": "<the menu URL, or the words: visited in person>",
      "verified_on": "<the date you checked it, YYYY-MM-DD>",
      "campus": "<hkbu | hkust | cuhk | hku | cityu>"
    }
  ]
}
```

Rules (the app checks every one; a bad record is rejected and listed in the server log,
never used):

- Required: `place`, `dish`, `price_cents`, `currency`, `source`, `verified_on`, `campus`.
- `price_cents` is a whole number above 0 (no decimals, no text). `currency` is `HKD`.
- `source` is not empty: a URL, or `visited in person`.
- `verified_on` is an ISO date (`2026-11-10`).
- Give `osm_id` (best: open the place on openstreetmap.org, the URL ends in `node/...` or
  `way/...`), or `lat` and `lng`. Without an id, a record matches a map place with the same
  name (case, accents and punctuation ignored) within 150 m.
- No other fields, except an optional free-text `note`.
- Several dishes for one place: add one record each. The map uses the cheapest one.

Check the file after editing it:

```sh
python tools/check_prices.py
```
