"""The app's actions: read the week, switch mode, set funds, add a payment.

Glue between the store, the clock and the money rules. Week dates come from
dates.py; every budget calculation stays in money.py. Amounts are integer cents.

Live mode uses the clock it is given. Demo mode is always on money.SAMPLE_TODAY
and keeps its own database file. Errors the user can fix raise ServiceError.
"""

import json
import re
import uuid
from datetime import datetime, timezone

from . import assistant, cooked, fit, money, places, prices, projection, ranges, receipt, rewards
from .dates import FixedClock, monday_of, week_dates
from .store import INBOX_SOURCES, REQUEST_ID, WALLET_SOURCE
from .validate import MAX_CENTS, clean_note, parse_amount

SCENARIOS = ("sample", "empty", "over", "cooked")
CHOICES = ("snack", money.FLEX, "savings")
# Older clients sent this name for the Experience/Development cover; it is still accepted.
LEGACY_CHOICES = {"borrow": money.FLEX}
CUSTOM = "custom"
PLACE_ID = re.compile(r"(node|way|relation)/[0-9]{1,20}")
FEEDBACK_CHARS = 500


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


def wallet_amount(raw):
    """Integer cents from what an iOS Shortcut sends for a Wallet transaction, or None.

    Text like "HK$38.00", "$38.50", "38.00 HKD" or "HK$ 1,234.50", or a JSON number (38.5).
    A number is read through its shortest decimal text, never as a float sum.
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
        text = raw.replace(" ", " ").upper().replace("HKD", "").replace("HK$", "").replace("$", "")
        text = text.replace(" ", "")
    else:
        return None
    return parse_amount(text)


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
        state["connected"] = _connected(s)
        state["campus"] = _campus(s)
        state["campuses"] = [{"id": c["id"], "name": c["name"]} for c in places.CAMPUSES.values()]
        state["rewards"] = self._rewards(s, today, state["savingsPot"]["total"]) if current else None
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
            entry = assistant.parse_entry(f"{money.hk(item['amount'])} {item['merchant']}", self._chains)
            guess = entry["category"] if entry.get("ok") else "main"
            remembered = s.merchant_fund(item["merchant"])
            if remembered:
                fund, reason = remembered, "used last time at this merchant"
            else:
                fund, reason = guess, entry.get("reason", "")
            # The typo check runs before Confirm too (an extra 0 on a simulated tap).
            typo = entry.get("typo") if fund == guess else assistant.check_typo(item["amount"], fund)
            out.append({**item, "suggestedFund": fund, "suggestedReason": reason, "typo": typo})
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

    def wallet_tap(self, amount, merchant=None, card=None):
        """A real Apple Pay payment from an iOS Shortcuts automation ("When I tap any card in
        Wallet"). It waits in To review like the others; nothing is spent until it is confirmed.
        Every run is a new item (the Shortcut has no id of its own)."""
        cents = wallet_amount(amount)
        if cents is None or cents > MAX_CENTS:
            raise ServiceError("Enter an amount greater than zero.")
        try:
            merchant = clean_note(merchant) or "Apple Pay payment"
            card = clean_note(card) or "Apple Pay"
        except ValueError:
            raise ServiceError("Merchant and card are text.") from None
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._books[self.mode()].session(write=True) as s:
            s.add_inbox({"externalId": f"wallet-{uuid.uuid4().hex}", "source": WALLET_SOURCE, "amount": cents,
                         "merchant": merchant, "card": card, "receivedAt": stamp})
        return {"ok": True, "amount": cents, "merchant": merchant}

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

    def inbox_confirm(self, item_id, category, choice=None, request_id=None):
        """Confirm an incoming payment into a fund, through exactly the same logic as add_payment
        (overspend step included). Until a payment is saved, the item stays pending."""
        item = self._pending(item_id)
        if request_id is None:
            request_id = f"inbox-{item['externalId']}"[:64]
        result = self.add_payment(item["amount"], category, item["merchant"], choice, request_id)
        if result["needsConfirm"]:
            return result
        with self._books[self.mode()].session(write=True) as s:
            s.set_inbox_status(item_id, "confirmed", payment_id=result["payment"]["id"])
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
