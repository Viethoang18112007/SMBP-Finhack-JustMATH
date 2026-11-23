"""Does a food place fit today's food left? Pure functions, integer cents, no I/O.

Price bands are estimates of one meal per person:
    cheap      up to HK$50
    normal     above HK$50, up to HK$120
    expensive  above HK$120 (no top)

    fits   the top of the band <= food left
    tight  the bottom of the band <= food left < the top
    over   food left < the bottom of the band

Expensive has no top, so it is at best "tight". A place with no band, or a
week with no funds set (food left is None), gets no fit (None).
"""

BANDS = {
    "cheap": (1, 5000),
    "normal": (5001, 12000),
    "expensive": (12001, None),
}
FITS = ("fits", "tight", "over")
_RANK = {fit: rank for rank, fit in enumerate(FITS)}


def fit_for(band, remaining):
    """"fits", "tight", "over", or None for `band` against `remaining` cents."""
    if remaining is None or band not in BANDS:
        return None
    low, high = BANDS[band]
    if high is not None and high <= remaining:
        return "fits"
    if low <= remaining:
        return "tight"
    return "over"


def with_fit(places, remaining):
    """Copies of `places` with a "fit" each, fits first, then tight, over, no fit.

    The sort is stable, so places keep their distance order inside each group.
    """
    out = [dict(place, fit=fit_for(place.get("price"), remaining)) for place in places]
    out.sort(key=lambda place: _RANK.get(place["fit"], len(FITS)))
    return out


def bands_payload():
    """The band table for the client: {"cheap": {"min": 1, "max": 5000}, ...}."""
    return {band: {"min": low, "max": high} for band, (low, high) in BANDS.items()}


# P1.5: honest states for the map. A price band is only an estimate from the place type
# (or an OSM price tag): it never earns "Fits". Only a verified dish price (prices.py) can
# fit or be over budget.
#
#   fits      a verified dish price <= food left today
#   over      a verified dish price  > food left today
#   estimate  no verified price; the band could fit (label "May fit (estimate)")
#   unlikely  no verified price; even the bottom of the band is more than food left
#   unknown   no verified price and no band
#   verified  a verified price, but no budget set this week
#   chain_fits    a chain's published meal range: even its top is within food left
#   chain_tight   a chain's range: its bottom fits, its top does not
#   chain_over    a chain's range: even its bottom is more than food left
#   chain         a chain's range, but no budget set this week
#
# A chain price (prices.match_chain) is a real published price, but one range for every
# branch, so it is shown apart from verified dish prices and from a place's own menu range.
#
# Order (with a budget): see _ORDER below. Nearest first inside each group. With no budget
# set, everything stays in distance order.

TYPE_WORDS = {"fast_food": "fast food place", "food_court": "food court", "cafe": "cafe", "restaurant": "restaurant"}
ESTIMATE_NOTE = "not a real menu price"


def range_text(band):
    """The band as shown to people: "up to HK$50", "HK$50 to HK$120", "from HK$120"."""
    from .money import hk
    low, high = BANDS[band]
    if low <= 1:
        return f"up to {hk(high)}"
    if high is None:
        return f"from {hk(low - 1)}"
    return f"{hk(low - 1)} to {hk(high)}"


def _verified_view(place, remaining, best):
    from .money import hk
    price = best["price_cents"]
    tail = f" | source: {best['source']} | checked {best['verified_on']}"
    verified = {"dish": best["dish"], "priceCents": price, "source": best["source"], "verifiedOn": best["verified_on"]}
    if remaining is None:
        return "verified", "Verified price", f"Verified {hk(price)} dish{tail}", verified, (0, 0)
    if price <= remaining:
        return "fits", "Fits", f"Verified {hk(price)} dish - fits your {hk(remaining)}{tail}", verified, (0, price)
    why = f"Verified {hk(price)} dish - {hk(price - remaining)} over your {hk(remaining)}{tail}"
    return "over", "Over budget", why, verified, (7, price)


def _estimate_view(place, remaining):
    band = place.get("price")
    if band not in BANDS:
        return "unknown", "Price unknown", f"No price data - {ESTIMATE_NOTE}", (0, 0) if remaining is None else (3, 0)
    if place.get("priceSource") == "tag":
        basis = "from its OpenStreetMap price tag"
    else:
        basis = f"for a {TYPE_WORDS.get(place.get('amenity'), 'food place')}"
    why = f"Estimated {range_text(band)} {basis} - {ESTIMATE_NOTE}"
    band_fit = fit_for(band, remaining)
    if band_fit is None:
        return "estimate", "Estimated", why, (0, 0)
    if band_fit == "over":
        return "unlikely", "Likely over (estimate)", why, (2, 0)
    return "estimate", "May fit (estimate)", why, (1, _RANK[band_fit])


# Per-place price ranges read on that place's own menu (ranges.py) come after verified dish
# prices and before chain prices (prices.match_chain: one published range for every branch):
#   range_fits  max <= food left today   "Fits (HK$min to HK$max, menu)"
#   range_may   min <= food left < max   "May fit (HK$min to HK$max, menu)"
#   range_over  food left < min          "Over (HK$min to HK$max, menu)"
#   range       no budget set this week
# Order keys (lower first): verified fits 0, menu range fits 1, chain fits 2, menu range may fit 3,
# chain may fit 4, estimates that may fit 5, unlikely estimates 6, unknown 7, menu range or chain
# over 8, verified over budget 9.
_ORDER = {"fits": 0, "range_fits": 1, "chain_fits": 2, "range_may": 3, "chain_tight": 4, "estimate": 5,
          "unlikely": 6, "unknown": 7, "range_over": 8, "chain_over": 8, "over": 9}


def _range_view(remaining, record):
    from .money import hk
    low, high = record["min_cents"], record["max_cents"]
    span = f"{hk(low)} to {hk(high)}"
    why = f"{record['source_name']} menu lists {span} per person | checked {record['checked_on']}"
    if remaining is None:
        return "range", f"{span} per person (menu)", why, (0, 0)
    if high <= remaining:
        return "range_fits", f"Fits ({span}, menu)", why, (_ORDER["range_fits"], high)
    if low <= remaining:
        return "range_may", f"May fit ({span}, menu)", why, (_ORDER["range_may"], low)
    return "range_over", f"Over ({span}, menu)", why, (_ORDER["range_over"], low)


def _site(source):
    """"scmp.com" for a URL (the full links stay in the data), else the text as it is."""
    from urllib.parse import urlparse
    host = urlparse(source).netloc if source.startswith(("http://", "https://")) else ""
    return host.removeprefix("www.") or source


def _chain_view(chain, remaining):
    from .money import hk
    low, high = chain["low_cents"], chain["high_cents"]
    span = hk(low) if low == high else f"{hk(low)} to {hk(high)}"
    check = " | not yet checked in a shop" if chain["needs_check"] else ""
    tail = f" | source: {_site(chain['sources'][0])} | checked {chain['checked_on']}{check}"
    info = {"chain": chain["chain"], "what": chain["what"], "lowCents": low, "highCents": high,
            "sources": chain["sources"], "checkedOn": chain["checked_on"], "needsCheck": chain["needs_check"]}
    why = f"{chain['chain']} {chain['what'].lower()}: {span} (chain price){tail}"
    if remaining is None:
        return "chain", "Chain price", why, info, (0, 0)
    if high <= remaining:
        return "chain_fits", "Fits (chain price)", why, info, (0, high)
    if low <= remaining:
        return "chain_tight", "May fit (chain price)", why, info, (0, low)
    return "chain_over", "Over (chain price)", why, info, (0, low)


def _reorder(status, key):
    """Per-view keys mapped onto the order above, keeping the tie-breaker."""
    return (_ORDER[status], key[1]) if status in _ORDER else key


def rank_places(places, remaining, records, ranges=(), chains=()):
    """Copies of `places` with fit, status, label, why, verified, range, priceRange and chain, in the order above.

    Priority for one place: verified dish price > its own menu range > its chain's price > estimate.
    """
    from .prices import match_chain, match_place
    out = []
    for place in places:
        item = dict(place, fit=fit_for(place.get("price"), remaining))
        band = place.get("price")
        item["range"] = range_text(band) if band in BANDS else None
        matched = match_place(place, records)
        verified = price_range = chain_info = None
        found = [] if matched or not ranges else match_place(place, ranges)
        chain = None if matched or found else match_chain(place, chains)
        if matched:
            best = min(matched, key=lambda r: (r["price_cents"], r["verified_on"]))
            status, label, why, verified, key = _verified_view(place, remaining, best)
        elif found:
            record = max(found, key=lambda r: r["checked_on"])
            status, label, why, key = _range_view(remaining, record)
            price_range = {"min": record["min_cents"], "max": record["max_cents"],
                           "sourceName": record["source_name"], "sourceUrl": record["source_url"],
                           "checkedOn": record["checked_on"], "note": record["note"]}
        elif chain is not None:
            status, label, why, chain_info, key = _chain_view(chain, remaining)
        else:
            status, label, why, key = _estimate_view(place, remaining)
        if remaining is not None:
            key = _reorder(status, key)
        item.update(status=status, label=label, why=why, verified=verified, priceRange=price_range, chain=chain_info)
        out.append((key + (place.get("distanceKm", 0),), item))
    if remaining is None:
        out = [((0, 0, item.get("distanceKm", 0)), item) for _key, item in out]
    out.sort(key=lambda pair: pair[0])
    return [item for _key, item in out]
