# Price ranges: research report (15 Nov 2026)

`backend/ssust/data/price_ranges.json` holds per person price ranges for places on the map.
A record was added only when the prices were read on the page at its `source_url` on
15 Nov 2026. The range is the lowest and the highest price printed for the section named in
the record's `note` (for example "lunch dishes"). Nothing was guessed or filled from memory.
Check the file with `python tools/check_prices.py`.

## Added (11)

| Campus | Place | Range | Source |
| --- | --- | --- | --- |
| HKBU | Nan Yuan | HK$42 to HK$98 | HKBU Estates Office menu PDF (2025-07), rice and noodle dishes |
| HKBU | Bistro NTT | HK$68 to HK$168 | HKBU Estates Office lunch menu PDF (2025-10), + 10% service |
| HKBU | Harmony Lounge | HK$42 to HK$52 | HKBU Estates Office, The Street Cafe menu PDF (2025-09), meal boxes |
| HKUST | Asia Pacific Catering | HK$27.50 to HK$42 | HKUST Campus Services menu PDF (2025-06), lunch dishes |
| HKUST | Gold Rice Bowl | HK$29 to HK$60 | HKUST Campus Services menu PDF (2024-09) |
| HKUST | JoA | HK$45 to HK$65 | HKUST Campus Services menu PDF (2026-09) |
| HKUST | American Diner | HK$26 to HK$46 | HKUST Campus Services menu PDF (2024-07), breakfast sets |
| HKUST | WeBite Space | HK$21 to HK$38 | HKUST Campus Services menu PDF (2026-09) |
| HKUST | UniQue | HK$148 to HK$258 | HKUST Campus Services menu PDF (Aug to Sep 2026), lunch set |
| HKUST | Ebeneezer's | HK$39 to HK$57.50 | HKUST Campus Services menu PDF (2026-09) |
| HKUST | Subway | HK$34 to HK$47 | HKUST Campus Services menu PDF (2026-07), 6-inch subs and burritos |

## Skipped, and why

- **Every OpenRice listing** (the planned main source): the pages timed out (HTTP 504) for the
  page reader every time, so no OpenRice price bracket could be read.
- **Tripadvisor**: refused the page reader (HTTP 403).
- **TamJai SamGor (HKUST)**: the HKUST restaurants page prints "35 - 60" with no currency.
- **China Garden, Oliver's Super Sandwiches (HKUST)**: menu PDFs larger than the reader's 10 MB limit.
- **Starbucks, Pacific Coffee (both campuses)**: drink menus; no meal range to read.
- **Main Canteen, Harmony Cafeteria (HKBU)**: only an online ordering page and catering
  (party) menus, no regular menu prices.
- **HFC @ Scholars Court, Books n' Bites, Chapter Coffee (HKBU)**: no menu with prices on the official page.
- **BU Fiesta (HKBU)**: closed for renovation (official page).
- **Chains off campus (McDonald's, KFC, Cafe de Coral, Pepper Lunch, Gyu-Kaku, On-Yasai...)**:
  not reached in the time available.
- **CUHK, HKU, CityU**: not reached in the time available.
