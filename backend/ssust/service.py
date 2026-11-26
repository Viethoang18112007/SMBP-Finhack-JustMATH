"""The app's actions: read the week, switch mode, set funds, add a payment.

Glue between the store, the clock and the money rules. Week dates come from
dates.py; every budget calculation stays in money.py. Amounts are integer cents.

Live mode uses the clock it is given. Demo mode is always on money.SAMPLE_TODAY
and keeps its own database file. Errors the user can fix raise ServiceError.
"""

import json
import math
import re
import uuid
from datetime import datetime, timezone

from . import assistant, backup, cooked, fit, groceries, money, places, prices, projection, ranges, receipt, rewards
from .dates import FixedClock, monday_of, week_dates
from .store import INBOX_SOURCES, REQUEST_ID, WALLET_SOURCE, merchant_key
from .validate import MAX_CENTS, clean_note, parse_amount

SCENARIOS = ("sample", "empty", "over", "cooked")
CHOICES = ("snack", money.FLEX, "savings")
# Older clients sent this name for the Experience/Development cover; it is still accepted.
LEGACY_CHOICES = {"borrow": money.FLEX}
CUSTOM = "custom"
PLACE_ID = re.compile(r"(node|way|relation)/[0-9]{1,20}")
FEEDBACK_CHARS = 500
# iOS can run the Wallet automation twice for one tap (card picked, then paid). Within this many
# seconds, taps of the same card on the same phone are one item, and a later amount fills it in.
TAP_WINDOW_SECONDS = 120
OCTOPUS_NAMES = ("octopus", "八達通", "八达通")
UNKNOWN_DETAIL = "Tap received without amount: open SSUST to add it."


class ServiceError(ValueError):
    """Bad input or an action the budget rules refuse. The message is safe to show.

    `details` (JSON-ready, e.g. {"field": "main", "minimum": 30000}) goes to the client too.
    """

    def __init__(self, message, **details):
        super().__init__(message)
        self.details = details


def _check_funds(amounts):
    if not isinstance(amounts, dict) or set(amounts) != set(money.FUNDS):
        raise ServiceError("Set all six funds.")
    for fund in money.FUNDS:
        value = amounts[fund]
        if type(value) is not int or not 0 <= value <= MAX_CENTS:
            raise ServiceError("Each fund needs a number of 0 or more.", field=fund)
    return {fund: amounts[fund] for fund in money.FUNDS}


def _check_not_below_spent(opening, payments):
    """A fund can't be set below what this week's payments already took from it."""
    spent = money.spent_by_fund(payments)
    for fund in money.FUNDS:
        if opening[fund] < spent[fund]:
            name = money.FUND_NAMES[fund]
            raise ServiceError(
                f"{name} already has {money.hk(spent[fund])} spent this week. "
                f"Set it to at least {money.hk(spent[fund])}.",
                field=fund, minimum=spent[fund])


def _place(place):
    """A map place sent with a payment ({"id": "node/123", "name": ...}), checked, or None."""
    if place is None:
        return None
    if not isinstance(place, dict) or not isinstance(place.get("id"), str) or not PLACE_ID.fullmatch(place["id"]):
        raise ServiceError("Unknown place.")
    try:
        name = clean_note(place.get("name"))
    except ValueError:
        raise ServiceError("Unknown place.") from None
    if not name:
        raise ServiceError("Unknown place.")
    return {"id": place["id"], "name": name}


def _feedback_text(text):
    """Printable text and line breaks only, no angle brackets, trimmed, at most FEEDBACK_CHARS."""
    if not isinstance(text, str):
        raise ServiceError("Feedback must be text.")
    cleaned = "".join(ch for ch in text if (ch.isprintable() or ch == "\n") and ch not in "<>").strip()
    if len(cleaned) > FEEDBACK_CHARS:
        raise ServiceError(f"Keep it under {FEEDBACK_CHARS} characters.")
    return cleaned


def _decimal_text(text):
    """Digits with one "." as the decimal point, from digits with "," and "." in any local style:
    "38,50" (French), "1.234,50" (German), "1,234.50" or "1,234" (English). None when unclear."""
    if "," in text and "." in text:
        point = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if point == "," else ",", "")
        return text.replace(",", ".") if text.count(point) == 1 else None
    if "," in text:
        if re.fullmatch(r"-?\d+,\d{1,2}", text):
            return text.replace(",", ".")
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):
            return text.replace(",", "")
        return None
    return text


def wallet_amount(raw):
    """Integer cents from what an iOS Shortcut sends for a Wallet transaction, or None.

    Text like "HK$38.00", "38,00 $HK" (an iPhone in French), "38.00 HKD" or "HK$ 1,234.50", or a
    JSON number (38.5). A number is read through its shortest decimal text, never as a float sum.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        text = str(raw)
    elif isinstance(raw, float):
        text = repr(raw)
        if "e" in text.lower() or "n" in text.lower():  # exponent, nan, inf
            return None
    elif isinstance(raw, str):
        # Keep digits and separators: currency signs, letters and every kind of space go.
        text = _decimal_text("".join(ch for ch in raw if (ch.isascii() and ch.isdigit()) or ch in ",.-"))
        if not text:
            return None
    else:
        return None
    return parse_amount(text)


def _shown(raw):
    """What a Shortcut sent as the amount, as short printable text for the setup check."""
    if isinstance(raw, str):
        text = "".join(ch if ch.isprintable() else " " for ch in raw)
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        text = repr(raw)
    elif raw is None:
        text = "(nothing)"
    else:
        text = f"({type(raw).__name__})"
    return text.replace("<", " ").replace(">", " ").strip()[:40]


def is_octopus_card(card):
    """True when a Wallet card name looks like an Octopus card. Only used for the label."""
    return isinstance(card, str) and any(name in card.casefold() for name in OCTOPUS_NAMES)


def _sent(value):
    """Whether a Shortcut field was present and not empty (for the Settings diagnostics)."""
    return value is not None and not (isinstance(value, str) and not value.strip())


def _text_or_none(value):
    """A Shortcut text field cleaned as the app stores it, or None when empty or not text."""
    if not isinstance(value, str):
        return None
    try:
        return clean_note(value) or None
    except ValueError:
        return None


def _zero_amount(raw):
    """True when a Shortcut amount is exactly zero (0, 0.0, "HK$0.00"): a tap that carried no amount."""
    if isinstance(raw, bool):
        return False
    if isinstance(raw, (int, float)):
        return raw == 0
    if isinstance(raw, str):
        text = _decimal_text("".join(ch for ch in raw if (ch.isascii() and ch.isdigit()) or ch in ",.-"))
        return bool(text) and parse_amount(text, allow_zero=True) == 0
    return False


def _utc(stamp):
    """A stored ISO time as an aware UTC datetime, or None."""
    try:
        when = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _wallet_last(s):
    """The last message from the Apple Pay automation (Settings shows it), or None."""
    try:
        last = json.loads(s.get_meta("wallet_last") or "null")
    except ValueError:
        return None
    return last if isinstance(last, dict) else None


def _campus(s):
    """The campus stored in this book's meta (each mode keeps its own), or the default."""
    campus = s.get_meta("campus")
    return campus if campus in places.CAMPUSES else places.DEFAULT_CAMPUS


def _connected(s):
    """Which simulated payment sources are switched on in this book (Settings > Connected payments)."""
    try:
        saved = json.loads(s.get_meta("connected") or "{}")
    except ValueError:
        saved = {}
    return {source: saved.get(source) is True for source in INBOX_SOURCES}


class Service:
    def __init__(self, books, clock, verified=None, price_ranges=None, chains=None):
        """`verified`: checked verified-price records and `chains`: checked chain prices (prices.py);
        `price_ranges`: checked per-place range records (ranges.py). By default all come from the
        shipped data files."""
        self._books = books
        self._verified = prices.load_verified()[0] if verified is None else list(verified)
        self._ranges = ranges.load_ranges()[0] if price_ranges is None else list(price_ranges)
        self._chains = prices.load_chains()[0] if chains is None else list(chains)
        self._live_clock = clock
        self._demo_clock = FixedClock(money.SAMPLE_TODAY)

    def mode(self):
        """The current mode, "live" or "demo" (stored in the live file)."""
        with self._books["live"].session() as s:
            return s.get_mode()

    # helpers

    def _today(self, mode):
        clock = self._demo_clock if mode == "demo" else self._live_clock
        return clock.today()

    def _build(self, s, mode, today, week):
        """The state for `week` read through an open session `s`."""
        opening = s.get_week(week)
        current = week == monday_of(today)
        prefill = None
        if opening is None and current:
            previous = s.previous_week(week)
            prefill = previous[1] if previous else None
        state = {
            "mode": mode,
            "scenario": s.get_meta("scenario") if mode == "demo" else None,
            "weekStart": week,
            "today": today,
            "opening": opening or {fund: None for fund in money.FUNDS},
            "payments": s.payments(week),
        }
        state["view"] = money.snapshot(state)
        state["tanks"] = money.fund_tanks(state)
        state["needsFunds"] = opening is None
        state["prefill"] = prefill
        state["weeks"] = s.weeks()
        state["closed"] = money.week_close(opening, state["payments"]) if week < monday_of(today) else None
        state["insights"] = assistant.insights(state, self._previous_week(s, week)) if current else None
        state["savingsPot"] = self._savings_pot(s, monday_of(today))
        state["split"] = {"suggested": dict(money.SUGGESTED_SPLIT), "minimum": dict(money.MIN_SPLIT)}
        state["projection"] = self._projection(s, today, opening if current else None)
        ready = current and state["view"]["ready"]
        runout = [w["fund"] for w in state["insights"]["warnings"]] if ready and state["insights"] else []
        state["cooked"] = cooked.cooked_score(opening if ready else None, state["view"]["fundsNow"] if ready else None,
                                              state["projection"], runout)
        state["inbox"] = self._inbox(s) if current else []
        state["walletLast"] = _wallet_last(s)
        state["connected"] = _connected(s)
        state["campus"] = _campus(s)
        state["campuses"] = [{"id": c["id"], "name": c["name"]} for c in places.CAMPUSES.values()]
        state["rewards"] = self._rewards(s, today, state["savingsPot"]["total"]) if current else None
        # No budget data at all on the server: a new phone, or a wiped disk the app can restore.
        state["fresh"] = s.is_fresh()
        return state

    @staticmethod
    def _rewards(s, today, savings):
        """The streak, last week's stars, campus medals and badges for the current week's state."""
        current = monday_of(today)
        weeks = [w for w in s.weeks() if w < current]  # weeks that have ended, oldest first
        stars = []
        for week in weeks:
            rated = rewards.week_stars(s.get_week(week), s.payments(week))
            if rated:
                stars.append({**rated, "weekStart": week})
        streak = rewards.streak(s.payment_dates(), today)
        medals = rewards.medals(s.visit_counts(), [(c["id"], c["name"]) for c in places.CAMPUSES.values()])
        last = stars[-1] if stars and stars[-1]["weekStart"] == weeks[-1] else None
        return {
            "streak": streak,
            "lastWeek": last,
            "medals": medals,
            "badges": rewards.badges(payments=s.payment_count(), budget_weeks=len(s.weeks()),
                                     best_streak=streak["best"], stars=[r["stars"] for r in stars],
                                     savings=savings, medals=medals),
        }

    def _inbox(self, s):
        """Pending incoming payments, each with the fund to pre-select: the last one used at that
        merchant, else the assistant's guess from the merchant name (with its reason)."""
        out = []
        for item in s.inbox("pending"):
            guess, reason, chain = assistant.guess_fund(item["merchant"], self._chains)
            remembered = s.merchant_fund(item["merchant"])
            fund = remembered or guess
            if remembered:
                reason = "used last time at this merchant"
            # The typo check runs before Confirm too (an extra 0 on a simulated tap). Without an
            # amount it runs on Confirm, on the amount the student types.
            unknown = item["amount"] is None
            typo = None if unknown else assistant.typo_for(item["amount"], fund, guess, chain)
            octopus = is_octopus_card(item["card"])
            label = "Octopus tap" if octopus else f"{item['card']} tap"
            out.append({**item, "suggestedFund": fund, "suggestedReason": reason, "typo": typo,
                        "amountUnknown": unknown, "octopus": octopus, "label": label})
        return out

    @staticmethod
    def _projection(s, today, opening):
        """The 30 day projection from every payment that still counts, across all weeks."""
        if opening is None:
            return {"ready": False, "reason": "no_budget", "days": 0}
        payments = [p for week in s.weeks() if week <= today for p in s.payments(week)]
        return projection.project(payments, today, opening)

    @staticmethod
    def _previous_week(s, week):
        """The stored week before `week`, as the small state assistant.insights compares with, or None."""
        earlier = [w for w in s.weeks() if w < week]
        if not earlier:
            return None
        prev = {"weekStart": earlier[-1], "today": week_dates(earlier[-1])[-1],
                "opening": s.get_week(earlier[-1]), "payments": s.payments(earlier[-1])}
        prev["view"] = money.snapshot(prev)
        return prev

    @staticmethod
    def _savings_pot(s, current):
        """Long-term Savings built up by the weeks that have ended (before `current`).

        Each ended week adds what was left of its own Long-term Savings plus what was
        left in its flexible funds. `lastFlexMoved` is the flexible part of the most
        recent ended week, so the app can say where the money came from.
        """
        total = last_flex = 0
        last_week = None
        for week in s.weeks():  # oldest first
            if week >= current:
                break
            closed = money.week_close(s.get_week(week), s.payments(week))
            total += closed["total"]
            last_week, last_flex = week, closed["flexMoved"]
        return {"total": total, "lastFlexMoved": last_flex, "lastWeek": last_week}

    # actions
    def get_state(self, week=None):
        mode = self.mode()
        today = self._today(mode)
        current = monday_of(today)
        if week is None:
            week = current
        else:
            try:
                week_dates(week)
            except ValueError:
                raise ServiceError("A week starts on a Monday, like 2026-11-09.") from None
            if week > current:
                raise ServiceError("That week has not started yet.")
        with self._books[mode].session() as s:
            return self._build(s, mode, today, week)

    def set_mode(self, mode, scenario=None):
        if mode == "live":
            if scenario is not None:
                raise ServiceError("Live mode has no scenario.")
        elif mode == "demo":
            scenario = "sample" if scenario is None else scenario
            if scenario not in SCENARIOS:
                raise ServiceError("Unknown demo week.")
            self._seed_demo(scenario)
        else:
            raise ServiceError("Unknown mode.")
        with self._books["live"].session(write=True) as s:
            s.set_mode(mode)
        return self.get_state()

    def _seed_demo(self, scenario):
        v1 = money.make_state(scenario)
        with self._books["demo"].session(write=True) as s:
            s.reset()
            s.set_meta("scenario", scenario)
            if money.ready(v1):
                s.set_week(v1["weekStart"], v1["opening"])
            for payment in v1["payments"]:
                s.add_payment(payment)

    def set_campus(self, campus):
        """Save the map's campus for the current mode."""
        if not isinstance(campus, str) or campus not in places.CAMPUSES:
            raise ServiceError("Unknown campus.")
        with self._books[self.mode()].session(write=True) as s:
            s.set_meta("campus", campus)
        return self.get_state()

    def places(self, kind, radius_km, fetcher):
        """Places around the saved campus. Food also gets today's food left and a fit per place.

        Live asks `fetcher(kind, radius_km, campus)` and falls back to the snapshot;
        demo reads the snapshot only. The fetcher's answer is never changed (it is cached).
        """
        mode = self.mode()
        state = self.get_state()
        data = places.places_for(kind, radius_km, mode == "live", fetcher, state["campus"])
        if kind == places.GROCERY_KIND:
            names = groceries.load_prices()["chains"]
            data = dict(data)
            data["places"] = [{**p, "chain": groceries.chain_for(p["name"]),
                               "chainName": names.get(groceries.chain_for(p["name"]))} for p in data["places"]]
            return data
        if kind != "food":
            return data
        remaining = state["view"]["todayRemaining"]
        clock = self._demo_clock if mode == "demo" else self._live_clock
        meals = fit.meals_left(clock.hour())
        meal = fit.per_meal(remaining, meals)
        data = dict(data)
        data["places"] = fit.rank_places(data["places"], meal, self._verified, self._ranges, self._chains)
        data["budget"] = {"remaining": remaining, "mealsLeft": meals, "perMeal": meal,
                          "bands": fit.bands_payload(), "verifiedRecords": len(self._verified),
                          "rangeRecords": len(self._ranges), "chainRecords": len(self._chains)}
        return data

    # Groceries: what to cook, what to buy, and the trip (the Map's Groceries mode)
    def _main_left(self):
        view = self.get_state()["view"]
        return view["fundsNow"]["main"] if view.get("ready") else None

    def groceries_catalogue(self):
        """The recipes, where the prices and fares come from, and Main meals left this week."""
        price_data = groceries.load_prices()
        fares = groceries.load_fares()
        meta = ("source", "sourceUrl", "checkedOn", "note", "needsCheck")
        return {
            "recipes": groceries.load_recipes(),
            "prices": {key: price_data.get(key) for key in ("source", "sourceUrl", "checkedOn", "note")},
            "fares": {mode: {key: fares[mode].get(key) for key in meta} for mode in ("taxi", "mtr")},
            "budget": {"main": self._main_left()},
        }

    def groceries_plan(self, recipe_id, servings, store_ids, radius, origin, mode, fare, round_trip,
                       include_pantry, fetcher):
        """The shopping list for a recipe, at up to two stores picked on the map, with the trip to
        each from `origin` (or the campus), the total, the fit against Main meals and the verdict."""
        recipe = next((r for r in groceries.load_recipes() if r["id"] == recipe_id), None)
        if recipe is None:
            raise ServiceError("Unknown recipe.")
        if type(servings) is not int or not 1 <= servings <= groceries.MAX_SERVINGS:
            raise ServiceError(f"Servings: a whole number from 1 to {groceries.MAX_SERVINGS}.")
        if mode not in groceries.MODES or fare not in groceries.FARE_TYPES:
            raise ServiceError("Pick walk, MTR or taxi, and a student or adult fare.")
        if not isinstance(round_trip, bool) or not isinstance(include_pantry, bool):
            raise ServiceError("Send roundTrip and includePantry as true or false.")
        if radius not in places.RADIUS_KM:
            raise ServiceError("Unknown map filter.")
        if (not isinstance(store_ids, list) or len(store_ids) > 2
                or not all(isinstance(s, str) for s in store_ids) or len(set(store_ids)) != len(store_ids)):
            raise ServiceError("Pick up to two different stores.")
        state = self.get_state()
        start = places.CAMPUSES[state["campus"]]
        if origin is not None:
            if not isinstance(origin, dict) or set(origin) != {"lat", "lng"} or any(
                    type(origin[k]) not in (int, float) or not math.isfinite(origin[k]) for k in ("lat", "lng")):
                raise ServiceError("Send the start point as {lat, lng}.")
            # Hong Kong only: the fares are Hong Kong fares.
            if not (22.1 <= origin["lat"] <= 22.6 and 113.8 <= origin["lng"] <= 114.5):
                raise ServiceError("The start point must be in Hong Kong.")
            start = {"lat": origin["lat"], "lng": origin["lng"]}
        found = {p["id"]: p for p in self.places(places.GROCERY_KIND, float(radius), fetcher)["places"]}
        price_data = groceries.load_prices()
        fares = groceries.load_fares()
        stores = []
        for store_id in store_ids:
            store = found.get(store_id)
            if store is None:
                raise ServiceError("That store is not on the map any more. Reload the map.")
            distance = places.haversine_km(start["lat"], start["lng"], store["lat"], store["lng"])
            bask = groceries.basket(recipe, servings, price_data, store["chain"], include_pantry)
            trip = groceries.trip(distance, mode, fares, fare, round_trip)
            stores.append({"id": store["id"], "name": store["name"], "chain": store["chain"],
                           "chainName": store["chainName"], "detail": store["detail"],
                           "distanceKm": round(distance, 2), "basket": bask, "trip": trip,
                           "totalCents": bask["totalCents"] + trip["cents"]})
        typical = groceries.basket(recipe, servings, price_data, None, include_pantry)
        main_left = self._main_left()
        cheapest = min((s["basket"]["totalCents"] for s in stores), default=typical["totalCents"])
        verdict = groceries.compare([{"id": s["id"], "name": s["name"], "groceriesCents": s["basket"]["totalCents"],
                                      "tripCents": s["trip"]["cents"]} for s in stores])
        return {"recipe": recipe, "servings": servings, "basket": typical, "stores": stores, "compare": verdict,
                "fit": groceries.budget_fit(cheapest, main_left), "budget": {"main": main_left},
                "prices": {key: price_data.get(key) for key in ("source", "sourceUrl", "checkedOn", "note")}}

    def parse_entry(self, text):
        """A quick entry ("$50 KFC dinner") read into amount, fund and note. Saves nothing."""
        return assistant.parse_entry(text, self._chains)

    def scan_receipt(self, text):
        """OCR text of a receipt -> total and merchant (receipt.py) -> fund, reason and typo check
        (assistant.parse_entry on the merchant name). Saves nothing: the client pre-fills Add payment.

        Raises ValueError for text that is too long."""
        found = receipt.parse_receipt(text)
        if not found["found"]:
            return {**found, "entry": None}
        merchant = found.get("merchant") or ""
        entry = assistant.parse_entry(f"{money.hk(found['amount'])} {merchant}", self._chains)
        if entry.get("ok"):
            entry["note"] = merchant[:40] if merchant else entry["note"]
        return {**found, "entry": entry if entry.get("ok") else None}

    def insights(self):
        """Pace warnings and a breakdown for the current week, compared with the week before."""
        return self.get_state()["insights"]

    def set_funds(self, amounts):
        """Live: this week's opening amounts, payments kept. Demo: a fresh custom week."""
        opening = _check_funds(amounts)
        mode = self.mode()
        week = monday_of(self._today(mode))
        with self._books[mode].session(write=True) as s:
            if mode == "demo":
                s.reset()
                s.set_meta("scenario", CUSTOM)
            else:
                _check_not_below_spent(opening, s.payments(week))
            s.set_week(week, opening)
        return self.get_state()

    # inbox (connected payments, simulated in this demo)
    def set_connected(self, source, on):
        if source not in INBOX_SOURCES or not isinstance(on, bool):
            raise ServiceError("Unknown payment source.")
        with self._books[self.mode()].session(write=True) as s:
            connected = _connected(s)
            connected[source] = on
            s.set_meta("connected", json.dumps(connected, sort_keys=True))
        return self.get_state()

    def inbox_add(self, source, amount, merchant, card, external_id):
        """Add an incoming payment to review. The same external id is added once.

        Returns {"item", "created", "state"}. Nothing is spent until the student confirms it.
        """
        if source not in INBOX_SOURCES:
            raise ServiceError("Unknown payment source.")
        if type(amount) is not int or not 0 < amount <= MAX_CENTS:
            raise ServiceError("Enter an amount greater than zero.")
        try:
            merchant = clean_note(merchant)
            card = clean_note(card)
        except ValueError as exc:
            raise ServiceError(str(exc)) from None
        if not merchant or not card:
            raise ServiceError("A merchant and a card are needed.")
        if not (isinstance(external_id, str) and REQUEST_ID.fullmatch(external_id)):
            raise ServiceError("Bad external id.")
        mode = self.mode()
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._books[mode].session(write=True) as s:
            item_id, created = s.add_inbox({"externalId": external_id, "source": source, "amount": amount,
                                            "merchant": merchant, "card": card, "receivedAt": stamp})
            item = s.get_inbox(item_id)
        return {"item": item, "created": created, "state": self.get_state()}

    def wallet_tap(self, amount, merchant=None, card=None, now=None):
        """A real Apple Pay payment from an iOS Shortcuts automation ("When I tap any card in
        Wallet"). It waits in To review like the others; nothing is spent until it is confirmed.

        - A valid amount: a new item (the Shortcut has no id of its own), or it fills in the amount
          of this card's amount-unknown item from the last TAP_WINDOW_SECONDS.
        - No amount (or zero) but a card or merchant: a real tap whose amount iOS did not give
          (Octopus). Kept as an amount-unknown item, one per card within the window.
        - Nothing at all: a run by hand from the Shortcuts editor, so only "the link works".

        Settings keeps which fields arrived (names only, plus the card name), never the values.
        """
        now = now or datetime.now(timezone.utc)
        stamp = now.isoformat(timespec="seconds")
        cents = wallet_amount(amount)
        sent_merchant = _text_or_none(merchant)
        sent_card = _text_or_none(card)
        received = {"amount": _sent(amount), "merchant": _sent(merchant), "card": _sent(card)}
        card = sent_card or "Apple Pay"
        merchant = sent_merchant or ("Octopus tap" if is_octopus_card(sent_card) else "Apple Pay payment")
        no_amount = not _sent(amount) or _zero_amount(amount)
        unknown = no_amount and bool(sent_card or sent_merchant)
        with self._books[self.mode()].session(write=True) as s:
            recent = self._recent_tap(s, card, now)
            # Kept so Settings can show what the automation last sent, accepted or not.
            if unknown:
                if recent is None:  # else the same tap fired twice: one item is enough
                    s.add_inbox({"externalId": f"wallet-{uuid.uuid4().hex}", "source": WALLET_SOURCE, "amount": None,
                                 "merchant": merchant, "card": card, "receivedAt": stamp})
                last = {"at": stamp, "ok": True, "amountUnknown": True, "detail": UNKNOWN_DETAIL}
            elif no_amount:
                # A run by hand from the Shortcuts editor: no payment, so no amount, but it got here.
                last = {"at": stamp, "ok": False, "linkOk": True,
                        "detail": "Test run: the link works. A real Apple Pay payment adds the amount."}
            elif cents is None or cents > MAX_CENTS:
                last = {"at": stamp, "ok": False, "amount": _shown(amount),
                        "detail": "The amount was not understood. Use Shortcut Input > Amount."}
            else:
                if recent is not None and recent["amount"] is None:
                    s.set_inbox_amount(recent["id"], cents, sent_merchant)
                    merchant = sent_merchant or recent["merchant"]
                else:
                    s.add_inbox({"externalId": f"wallet-{uuid.uuid4().hex}", "source": WALLET_SOURCE, "amount": cents,
                                 "merchant": merchant, "card": card, "receivedAt": stamp})
                last = {"at": stamp, "ok": True, "amount": _shown(amount), "detail": f"{money.hk(cents)} from {merchant}"}
            last["received"] = received
            last["cardName"] = sent_card
            s.set_meta("wallet_last", json.dumps(last))
        if not last["ok"]:
            raise ServiceError("Enter an amount greater than zero.")
        if unknown:
            return {"ok": True, "amount": None, "amountUnknown": True, "merchant": merchant, "message": UNKNOWN_DETAIL}
        return {"ok": True, "amount": cents, "merchant": merchant}

    @staticmethod
    def _recent_tap(s, card, now):
        """This card's latest pending wallet item from the last TAP_WINDOW_SECONDS, or None."""
        key = merchant_key(card)
        for item in reversed(s.wallet_pending()):
            when = _utc(item["receivedAt"])
            if (merchant_key(item["card"]) == key and when is not None
                    and abs((now - when).total_seconds()) <= TAP_WINDOW_SECONDS):
                return item
        return None

    def shortcut_today(self):
        """One line for a Shortcuts widget: what is left today, the streak and what waits for review."""
        state = self.get_state()
        view = state["view"]
        if not view["ready"]:
            return "SSUST: set your weekly budget in the app."
        left = view["todayRemaining"]
        parts = [f"SSUST: {money.hk(left)} left today" if left >= 0 else f"SSUST: {money.hk(-left)} over today"]
        streak = state["rewards"]["streak"]["days"] if state["rewards"] else 0
        if streak:
            parts.append(f"{streak} day streak")
        if state["inbox"]:
            parts.append(f"{len(state['inbox'])} to review")
        return " · ".join(parts)

    def widget(self):
        """What the iOS home screen widget shows: today's money left, today's spending against the
        allowance, every fund, today's last payments, the streak and the count waiting for review.
        Integer cents plus the HK$ text, so the widget never formats or computes money."""
        state = self.get_state()
        view = state["view"]
        streak = state["rewards"]["streak"] if state["rewards"] else None
        ready = bool(view["ready"])
        left = view["todayRemaining"] if ready else 0
        allowance = view["allowance"] if ready else 0
        spent = view["spentToday"] if ready else 0
        if allowance > 0:
            ratio = min(1000, spent * 1000 // allowance)
        else:
            ratio = 1000 if spent > 0 else 0
        funds = [{"fund": t["fund"], "name": t["name"], "left": t["remaining"], "leftText": money.hk(t["remaining"]),
                  "allocationText": money.hk(t["allocation"]), "level": max(0, min(1000, t["level"] // 10))}
                 for t in (state["tanks"] or [])] if ready else []
        today = [p for p in state["payments"] if p["date"] == state["today"]]
        today.sort(key=lambda p: p["id"], reverse=True)
        payments = [{"label": p["note"] or money.FUND_NAMES[p["category"]], "amountText": money.hk(p["amount"]),
                     "fund": p["category"]} for p in today[:3]]
        return {"ready": ready, "left": left, "leftText": money.hk(abs(left)), "over": left < 0,
                "allowanceText": money.hk(allowance), "spentText": money.hk(spent), "spentRatio": ratio,
                "tomorrowText": money.hk(view["tomorrow"]) if ready else money.hk(0), "daysLeft": view["daysLeft"],
                "funds": funds, "payments": payments,
                "streak": streak["days"] if streak else 0, "shape": (streak["shape"] if streak else None) or "square",
                "toReview": len(state["inbox"])}

    def _pending(self, item_id):
        if type(item_id) is not int or not 0 < item_id < 2 ** 63:
            raise ServiceError("Unknown item.")
        with self._books[self.mode()].session() as s:
            item = s.get_inbox(item_id)
        if item is None:
            raise ServiceError("Unknown item.")
        if item["status"] != "pending":
            raise ServiceError("This payment was already reviewed.")
        return item

    def inbox_confirm(self, item_id, category, choice=None, request_id=None, amount=None, typo_checked=False):
        """Confirm an incoming payment into a fund, through exactly the same logic as add_payment
        (overspend step included). Until a payment is saved, the item stays pending.

        An item without an amount (a wallet tap iOS gave none) needs `amount` (integer cents > 0)
        and goes through the typo check first: {"needsTypoCheck": True, "typo"} until the student
        confirms again with typo_checked=True. An item that has its amount keeps it."""
        item = self._pending(item_id)
        if item["amount"] is None:
            if type(amount) is not int or not 0 < amount <= MAX_CENTS:
                raise ServiceError("Enter an amount greater than zero.")
            if category not in money.CATEGORIES:
                raise ServiceError("Unknown fund.")
            guess, _, chain = assistant.guess_fund(item["merchant"], self._chains)
            typo = assistant.typo_for(amount, category, guess, chain)
            if typo and typo_checked is not True:
                return {"needsTypoCheck": True, "typo": typo, "needsConfirm": False, "state": self.get_state()}
        elif amount is not None and amount != item["amount"]:
            raise ServiceError("This payment already has its amount.")
        else:
            amount = item["amount"]
        if request_id is None:
            request_id = f"inbox-{item['externalId']}"[:64]
        result = self.add_payment(amount, category, item["merchant"], choice, request_id)
        if result["needsConfirm"]:
            return result
        with self._books[self.mode()].session(write=True) as s:
            s.set_inbox_status(item_id, "confirmed", payment_id=result["payment"]["id"], amount=amount)
            s.remember_merchant_fund(item["merchant"], category)
        return {**result, "state": self.get_state()}

    def inbox_dismiss(self, item_id):
        self._pending(item_id)
        with self._books[self.mode()].session(write=True) as s:
            s.set_inbox_status(item_id, "dismissed")
        return self.get_state()

    def undo_payment(self, payment_id):
        """Undo one of this week's payments in the current mode.

        The row is voided, not deleted; balances are always recomputed from the
        payments that still count, so any reallocation it caused is reversed too.
        Returns {"undone": payment, "state"}.
        """
        if type(payment_id) is not int or not 0 < payment_id < 2 ** 63:
            raise ServiceError("Unknown payment.")
        mode = self.mode()
        today = self._today(mode)
        week = monday_of(today)
        with self._books[mode].session(write=True) as s:
            payment = s.get_payment(payment_id)
            if payment is None:
                raise ServiceError("Unknown payment.")
            if payment["voidedAt"] is not None:
                raise ServiceError("This payment was already undone.")
            if payment["date"] not in week_dates(week):
                raise ServiceError("Only this week's payments can be undone. Past weeks are read-only.")
            s.void_payment(payment_id)
            return {"undone": payment, "state": self._build(s, mode, today, week)}

    # backup and restore (iPhone app): the phone keeps the copy, the server can be rebuilt from it
    def backup(self, device):
        """Everything stored in this phone's live book, as one document (backup.py)."""
        with self._books["live"].session() as s:
            tables = s.export_tables(backup.META_KEYS)
        return backup.document(tables, device, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def restore(self, device, doc):
        """Merge a backup document of this phone back into its live book, in one transaction.

        Checks the whole document first; any problem refuses it and writes nothing.
        Returns {"added": rows added per table, "state"}.
        """
        try:
            tables = backup.check(doc, device)
        except backup.Invalid as exc:
            raise ServiceError(str(exc)) from None
        with self._books["live"].session(write=True) as s:
            added = s.merge_tables(tables)
        return {"added": added, "state": self.get_state()}

    # feedback about the app
    def add_feedback(self, rating, text):
        if type(rating) is not int or not 1 <= rating <= 5:
            raise ServiceError("Pick 1 to 5 stars.")
        text = _feedback_text(text)
        with self._books[self.mode()].session(write=True) as s:
            s.add_feedback(rating, text)
        return self.feedback()

    def feedback(self):
        with self._books[self.mode()].session() as s:
            return {"feedback": s.feedback()}

    def add_payment(self, amount, category, note="", choice=None, request_id=None, place=None):
        """Save a payment dated today, or ask which cover to use first.

        Returns {"needsConfirm": True, "level", "options", "state"} when a gap
        needs a choice, else {"needsConfirm": False, "level", "payment", "state"}.
        A choice that is not among the offered options is refused.

        `request_id` (optional) makes the save idempotent: if a payment was already
        saved with it, nothing new is saved and the answer carries that payment,
        the current state and "replayed": True. The id is only stored once a
        payment is saved, so the same id can go through ask-then-confirm.
        """
        if type(amount) is not int or not 0 < amount <= MAX_CENTS:
            raise ServiceError("Enter an amount greater than zero.")
        if category not in money.CATEGORIES:
            raise ServiceError("Unknown category.")
        try:
            note = clean_note(note)
        except ValueError as exc:
            raise ServiceError(str(exc)) from None
        if isinstance(choice, str):
            choice = LEGACY_CHOICES.get(choice, choice)
        if choice is not None and choice not in CHOICES:
            raise ServiceError("Unknown cover.")
        if request_id is not None and not (isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id)):
            raise ServiceError("Bad request id.")
        place = _place(place)
        mode = self.mode()
        today = self._today(mode)
        week = monday_of(today)
        with self._books[mode].session(write=True) as s:
            if request_id is not None:
                saved = s.payment_by_request(request_id)
                if saved is not None:
                    if (saved["amount"], saved["category"]) != (amount, category):
                        raise ServiceError("This request id was already used for another payment.")
                    undone = saved.pop("voidedAt") is not None
                    return {"needsConfirm": False, "level": 0, "replayed": True, "payment": saved, "undone": undone,
                            "state": self._build(s, mode, today, week)}
            state = self._build(s, mode, today, week)
            result = money.plan(state, amount, category)
            if result.get("error"):
                raise ServiceError(result["error"])
            uncovered = 0
            if result["saveNow"]:
                taken, level = result["from"], result["level"]
                uncovered = result.get("uncovered", 0)
            elif choice is None:
                return {"needsConfirm": True, "level": result["level"], "options": result["options"], "state": state}
            else:
                match = next((o for o in result["options"] if o["choice"] == choice), None)
                if match is None:
                    raise ServiceError("That cover is not available for this payment.")
                taken, level = match["from"], match["hole"]
            payment_id = s.add_payment({
                "date": today,
                "amount": amount,
                "category": category,
                "note": note,
                "from": taken,
                "uncovered": uncovered,
            }, request_id=request_id)
            if place is not None:
                # It counts for the campus medal when it fit today's food money (no cover needed).
                left = state["view"]["todayRemaining"]
                within = level == 0 and uncovered == 0 and left is not None and amount <= left
                s.add_visit(payment_id, state["campus"], place["id"], place["name"], within)
            after = self._build(s, mode, today, week)
            saved = next(p for p in after["payments"] if p["id"] == payment_id)
            return {"needsConfirm": False, "level": level, "payment": saved, "state": after}
