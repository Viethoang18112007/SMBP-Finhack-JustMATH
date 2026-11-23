import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ssust import fit, money, places
from ssust.dates import FixedClock
from ssust.service import Service, ServiceError
from ssust.store import open_books
from ssust.validate import MAX_CENTS

LIVE_TODAY = "2027-03-03"  # a Wednesday, far from the demo week
LIVE_MONDAY = "2027-03-01"
FUNDS = dict(money.SAMPLE_OPENING)
NO_FUNDS = {fund: None for fund in money.FUNDS}
PAYMENT_FIELDS = ("date", "amount", "category", "note", "from")


def comparable(payments):
    return [{key: p[key] for key in PAYMENT_FIELDS} for p in payments]


class ServiceTest(unittest.TestCase):
    """Every test gets its own temporary data folder; the real data/ folder is never used."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "data"
        self.svc = self.service(LIVE_TODAY)

    def service(self, today):
        return Service(open_books(self.dir), FixedClock(today))


class FreshLive(ServiceTest):
    def test_mode_is_live_until_switched(self):
        self.assertEqual(self.svc.mode(), "live")
        self.svc.set_mode("demo")
        self.assertEqual(self.svc.mode(), "demo")
        self.svc.set_mode("live")
        self.assertEqual(self.svc.mode(), "live")

    def test_fresh_live_db_needs_funds_with_no_prefill(self):
        state = self.svc.get_state()
        self.assertEqual(state["mode"], "live")
        self.assertIsNone(state["scenario"])
        self.assertEqual(state["today"], LIVE_TODAY)
        self.assertEqual(state["weekStart"], LIVE_MONDAY)
        self.assertTrue(state["needsFunds"])
        self.assertIsNone(state["prefill"])
        self.assertEqual(state["weeks"], [])
        self.assertEqual(state["opening"], NO_FUNDS)
        self.assertEqual(state["payments"], [])
        self.assertFalse(state["view"]["ready"])

    def test_set_funds_starts_the_week(self):
        state = self.svc.set_funds(FUNDS)
        self.assertFalse(state["needsFunds"])
        self.assertIsNone(state["prefill"])
        self.assertEqual(state["opening"], FUNDS)
        self.assertEqual(state["weeks"], [LIVE_MONDAY])
        self.assertTrue(state["view"]["ready"])
        # Wednesday: 5 days left, HK$850 of food.
        self.assertEqual(state["view"]["allowance"], 17000)

    def test_state_is_json_ready(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(4800, "main", "lunch")
        json.dumps(self.svc.get_state())

    def test_data_survives_a_new_service_on_the_same_folder(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(4800, "main", "lunch")
        state = self.service(LIVE_TODAY).get_state()
        self.assertEqual(state["opening"], FUNDS)
        self.assertEqual([p["amount"] for p in state["payments"]], [4800])


class NewWeek(ServiceTest):
    def test_next_monday_needs_funds_prefilled_from_last_week(self):
        self.svc.set_funds(FUNDS)
        state = self.service("2027-03-08").get_state()
        self.assertEqual(state["weekStart"], "2027-03-08")
        self.assertTrue(state["needsFunds"])
        self.assertEqual(state["prefill"], FUNDS)
        self.assertEqual(state["opening"], NO_FUNDS)
        self.assertEqual(state["payments"], [])
        self.assertEqual(state["weeks"], [LIVE_MONDAY])

    def test_prefill_skips_weeks_without_funds(self):
        self.svc.set_funds(FUNDS)
        state = self.service("2027-03-24").get_state()
        self.assertEqual(state["weekStart"], "2027-03-22")
        self.assertEqual(state["prefill"], FUNDS)

    def test_last_weeks_payments_do_not_count_this_week(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(4800, "main", "lunch")
        nxt = self.service("2027-03-08")
        state = nxt.set_funds(FUNDS)
        self.assertEqual(state["payments"], [])
        self.assertEqual(state["weeks"], [LIVE_MONDAY, "2027-03-08"])
        self.assertIsNone(state["prefill"])

    def test_past_week_stays_readable(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(4800, "main", "lunch")
        nxt = self.service("2027-03-08")
        nxt.set_funds({**FUNDS, "main": 50000})
        past = nxt.get_state(week=LIVE_MONDAY)
        self.assertEqual(past["weekStart"], LIVE_MONDAY)
        self.assertEqual(past["opening"], FUNDS)
        self.assertEqual([p["amount"] for p in past["payments"]], [4800])
        self.assertFalse(past["needsFunds"])

    def test_bad_week_is_rejected(self):
        for bad in ["2027-03-03", "2027-03-15", "next", "", 20270301]:
            with self.subTest(week=bad):
                with self.assertRaises(ServiceError):
                    self.svc.get_state(week=bad)


class LiveFunds(ServiceTest):
    def test_live_funds_edit_keeps_payments(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(4800, "main", "lunch")
        self.svc.add_payment(1500, "snack", "tea")
        state = self.svc.set_funds({**FUNDS, "main": 90000})
        self.assertEqual(state["opening"]["main"], 90000)
        self.assertEqual([p["amount"] for p in state["payments"]], [4800, 1500])
        self.assertEqual(state["view"]["fundsNow"]["main"], 90000 - 4800)

    def test_bad_funds_are_rejected(self):
        bad_inputs = [
            None,
            [],
            {k: v for k, v in FUNDS.items() if k != "savings"},
            {**FUNDS, "extra": 100},
            {**FUNDS, "main": -100},
            {**FUNDS, "main": 480.0},
            {**FUNDS, "main": "48"},
            {**FUNDS, "main": True},
            {**FUNDS, "main": MAX_CENTS + 1},
        ]
        for bad in bad_inputs:
            with self.subTest(funds=bad):
                with self.assertRaises(ServiceError):
                    self.svc.set_funds(bad)
        self.assertTrue(self.svc.get_state()["needsFunds"])


class Demo(ServiceTest):
    def test_demo_scenarios_match_v1_numbers_exactly(self):
        for scenario in ("sample", "empty", "over"):
            with self.subTest(scenario=scenario):
                v1 = money.make_state(scenario)
                state = self.svc.set_mode("demo", scenario)
                self.assertEqual(state["mode"], "demo")
                self.assertEqual(state["scenario"], scenario)
                self.assertEqual(state["today"], money.SAMPLE_TODAY)
                self.assertEqual(state["weekStart"], money.SAMPLE_WEEK_START)
                self.assertEqual(state["opening"], v1["opening"])
                self.assertEqual(comparable(state["payments"]), comparable(v1["payments"]))
                self.assertEqual(state["view"], money.snapshot(v1))
                self.assertEqual(state["needsFunds"], scenario == "empty")

    def test_demo_sample_gives_hk140_today(self):
        state = self.svc.set_mode("demo", "sample")
        self.assertEqual(state["view"]["allowance"], 14000)
        self.assertEqual(state["view"]["todayRemaining"], 14000)

    def test_demo_scenario_defaults_to_sample(self):
        self.assertEqual(self.svc.set_mode("demo")["scenario"], "sample")

    def test_switching_scenario_replaces_the_demo_week(self):
        self.svc.set_mode("demo", "sample")
        self.svc.add_payment(4800, "main", "lunch")
        state = self.svc.set_mode("demo", "sample")
        self.assertEqual(len(state["payments"]), 4)

    def test_mode_is_remembered(self):
        self.svc.set_mode("demo", "over")
        state = self.service(LIVE_TODAY).get_state()
        self.assertEqual(state["mode"], "demo")
        self.assertEqual(state["scenario"], "over")

    def test_demo_and_live_data_stay_apart(self):
        self.svc.set_funds({**FUNDS, "main": 90000})
        self.svc.add_payment(1234, "main", "live lunch")
        self.svc.set_mode("demo", "sample")
        self.svc.add_payment(4800, "main", "demo lunch")
        live = self.svc.set_mode("live")
        self.assertEqual(live["mode"], "live")
        self.assertEqual(live["today"], LIVE_TODAY)
        self.assertEqual(live["opening"]["main"], 90000)
        self.assertEqual([p["note"] for p in live["payments"]], ["live lunch"])
        demo = self.svc.set_mode("demo", "sample")
        self.assertNotIn("live lunch", [p["note"] for p in demo["payments"]])

    def test_demo_funds_edit_resets_the_payments(self):
        self.svc.set_mode("demo", "sample")
        state = self.svc.set_funds(FUNDS)
        self.assertEqual(state["payments"], [])
        self.assertEqual(state["opening"], FUNDS)
        self.assertEqual(state["scenario"], "custom")

    def test_bad_mode_or_scenario_is_rejected(self):
        for mode, scenario in [("test", None), (None, None), ("demo", "custom"), ("demo", "nope"), ("live", "sample")]:
            with self.subTest(mode=mode, scenario=scenario):
                with self.assertRaises(ServiceError):
                    self.svc.set_mode(mode, scenario)
        self.assertEqual(self.svc.get_state()["mode"], "live")


class Payments(ServiceTest):
    def setUp(self):
        super().setUp()
        self.svc.set_mode("demo", "sample")

    def count(self):
        return len(self.svc.get_state()["payments"])

    def test_a_payment_that_fits_is_saved_at_once(self):
        result = self.svc.add_payment(4800, "main", "lunch")
        self.assertFalse(result["needsConfirm"])
        self.assertEqual(result["level"], 0)
        saved = result["state"]["payments"][-1]
        self.assertEqual(saved["date"], money.SAMPLE_TODAY)
        self.assertEqual(saved["note"], "lunch")
        self.assertEqual(saved["from"], {**money.empty_from(), "main": 4800})
        self.assertEqual(result["state"]["view"]["todayRemaining"], 9200)

    def lunch_first(self):
        # The v1 walkthrough: after the HK$48 lunch, HK$92 is left, so HK$100 leaves a gap.
        self.svc.add_payment(4800, "main", "lunch")

    def test_a_gap_asks_first_and_saves_nothing(self):
        self.lunch_first()
        result = self.svc.add_payment(10000, "main", "dinner")
        self.assertTrue(result["needsConfirm"])
        self.assertEqual({o["choice"] for o in result["options"]}, {"snack", "flex"})
        self.assertEqual(len(result["state"]["payments"]), 5)
        self.assertEqual(self.count(), 5)

    def test_an_offered_choice_saves_that_option(self):
        self.lunch_first()
        offered = self.svc.add_payment(10000, "main", "dinner")["options"]
        flex = next(o for o in offered if o["choice"] == "flex")
        result = self.svc.add_payment(10000, "main", "dinner", choice="flex")
        self.assertFalse(result["needsConfirm"])
        self.assertEqual(result["level"], flex["hole"])
        self.assertEqual(result["state"]["payments"][-1]["from"], flex["from"])
        self.assertEqual(self.count(), 6)

    def test_a_choice_that_is_not_offered_is_rejected(self):
        self.lunch_first()
        for choice in ["savings", "free", "", 1]:
            with self.subTest(choice=choice):
                with self.assertRaises(ServiceError):
                    self.svc.add_payment(10000, "main", "dinner", choice=choice)
        self.assertEqual(self.count(), 5)

    def test_fixed_bill_records_the_uncovered_part(self):
        result = self.svc.add_payment(25000, "fixed", "rent")
        saved = result["state"]["payments"][-1]
        self.assertEqual(saved["from"]["fixed"], 20000)
        self.assertEqual(saved["uncovered"], 5000)

    def test_cannot_cover_is_an_error(self):
        with self.assertRaises(ServiceError):
            self.svc.add_payment(MAX_CENTS, "development", "laptop")
        self.assertEqual(self.count(), 4)

    def test_note_is_cleaned(self):
        result = self.svc.add_payment(500, "snack", "  <b>tea</b>  ")
        self.assertEqual(result["state"]["payments"][-1]["note"], "btea/b")

    def test_bad_payment_input_is_rejected(self):
        bad_inputs = [
            (0, "main", ""),
            (-100, "main", ""),
            (48.0, "main", ""),
            ("4800", "main", ""),
            (True, "main", ""),
            (MAX_CENTS + 1, "main", ""),
            (4800, "savings", ""),
            (4800, None, ""),
            (4800, "main", 42),
        ]
        for amount, category, note in bad_inputs:
            with self.subTest(amount=amount, category=category, note=note):
                with self.assertRaises(ServiceError):
                    self.svc.add_payment(amount, category, note)
        self.assertEqual(self.count(), 4)

    def test_no_payment_before_funds_are_set(self):
        self.svc.set_mode("demo", "empty")
        with self.assertRaises(ServiceError):
            self.svc.add_payment(4800, "main", "lunch")


class Campus(ServiceTest):
    def test_default_campus_and_the_list(self):
        state = self.svc.get_state()
        self.assertEqual(state["campus"], "hkust")
        self.assertEqual(state["campuses"], [
            {"id": "hkbu", "name": "HKBU"}, {"id": "hkust", "name": "HKUST"}, {"id": "cuhk", "name": "CUHK"},
            {"id": "hku", "name": "HKU"}, {"id": "cityu", "name": "CityU"},
        ])

    def test_choice_is_saved_per_mode(self):
        self.assertEqual(self.svc.set_campus("hkbu")["campus"], "hkbu")
        self.svc.set_mode("demo")
        self.assertEqual(self.svc.get_state()["campus"], "hkust")
        self.svc.set_campus("cuhk")
        self.svc.set_mode("live")
        self.assertEqual(self.svc.get_state()["campus"], "hkbu")
        self.svc.set_mode("demo", "over")  # a re-seed keeps the demo choice
        self.assertEqual(self.svc.get_state()["campus"], "cuhk")

    def test_choice_survives_a_restart(self):
        self.svc.set_campus("hku")
        self.assertEqual(self.service(LIVE_TODAY).get_state()["campus"], "hku")

    def test_past_weeks_carry_the_campus(self):
        self.svc.set_campus("cityu")
        with open_books(self.dir)["live"].session(write=True) as s:
            s.set_week("2027-02-22", FUNDS)
        self.assertEqual(self.svc.get_state("2027-02-22")["campus"], "cityu")

    def test_unknown_campus_is_refused(self):
        for bad in ("", "HKBU", "polyu", None, 3, ["hku"]):
            with self.subTest(campus=bad):
                with self.assertRaises(ServiceError):
                    self.svc.set_campus(bad)
        self.assertEqual(self.svc.get_state()["campus"], "hkust")


def no_fetch(*args):
    raise AssertionError("the places fetcher must not be called")


class PlacesFit(ServiceTest):
    def setUp(self):
        super().setUp()
        self.svc.set_mode("demo")

    def expected_fits(self, campus, remaining):
        data = places.snapshot_places("food", 3.0, campus)
        return sorted(fit.fit_for(p["price"], remaining) or "none" for p in data["places"])

    def test_demo_sample_has_hk140_left_and_every_food_place_gets_a_fit(self):
        data = self.svc.places("food", 3.0, no_fetch)
        self.assertEqual(data["source"], "snapshot")
        self.assertEqual(data["center"], places.CAMPUSES["hkust"])
        self.assertEqual(data["budget"]["remaining"], 14000)
        # One meal is compared with one meal's share: demo noon, lunch and dinner to go.
        self.assertEqual((data["budget"]["mealsLeft"], data["budget"]["perMeal"]), (2, 7000))
        self.assertEqual(data["budget"]["bands"], {
            "cheap": {"min": 1, "max": 5000},
            "normal": {"min": 5001, "max": 12000},
            "expensive": {"min": 12001, "max": None},
        })
        fits = [p["fit"] for p in data["places"]]
        self.assertEqual(sorted(f or "none" for f in fits), self.expected_fits("hkust", 7000))
        self.assertNotIn(None, fits)
        # Sorted by the honest status (menu, chain, estimate...), not by the estimate band.
        ranks = [fit._ORDER[p["status"]] for p in data["places"]]
        self.assertEqual(ranks, sorted(ranks))

    def test_chosen_campus_is_used(self):
        self.svc.set_campus("hku")
        data = self.svc.places("food", 3.0, no_fetch)
        self.assertEqual(data["center"], places.CAMPUSES["hku"])
        fits = sorted(p["fit"] or "none" for p in data["places"])
        self.assertEqual(fits, self.expected_fits("hku", 7000))

    def test_a_payment_changes_the_fit(self):
        self.svc.add_payment(4800, "main", "lunch")  # HK$92 left today, HK$46 a meal
        data = self.svc.places("food", 3.0, no_fetch)
        self.assertEqual(data["budget"]["remaining"], 9200)
        self.assertEqual(data["budget"]["perMeal"], 4600)
        by_price = {}
        for place in data["places"]:
            by_price.setdefault(place["price"], set()).add(place["fit"])
        self.assertEqual(by_price.get("cheap", {"tight"}), {"tight"})
        self.assertEqual(by_price.get("normal", {"over"}), {"over"})
        self.assertEqual(by_price.get("expensive", {"over"}), {"over"})
        self.assertIn("normal", by_price)

    def test_week_over_means_nothing_fits(self):
        self.svc.set_mode("demo", "over")
        data = self.svc.places("food", 3.0, no_fetch)
        remaining = data["budget"]["remaining"]
        self.assertLessEqual(remaining, 0)
        self.assertTrue(all(p["fit"] == "over" for p in data["places"]))

    def test_no_fit_before_funds_are_set(self):
        self.svc.set_mode("demo", "empty")
        data = self.svc.places("food", 3.0, no_fetch)
        self.assertIsNone(data["budget"]["remaining"])
        self.assertTrue(data["places"])
        self.assertTrue(all(p["fit"] is None for p in data["places"]))

    def test_shops_get_no_fit(self):
        data = self.svc.places("shop", 3.0, no_fetch)
        self.assertNotIn("budget", data)
        self.assertTrue(data["places"])
        self.assertTrue(all("fit" not in p for p in data["places"]))

    def test_live_passes_the_campus_to_the_fetcher(self):
        self.svc.set_mode("live")
        self.svc.set_campus("cityu")
        self.svc.set_funds(FUNDS)
        live = {"center": places.CAMPUSES["cityu"], "kind": "food", "radiusKm": 1.0, "source": "OpenStreetMap",
                "shown": 1, "total": 1,
                "places": [{"id": "node/1", "name": "X", "price": "cheap", "priceSource": "type", "distanceKm": 0.1}]}
        fetcher = mock.Mock(return_value=live)
        data = self.svc.places("food", 1.0, fetcher)
        fetcher.assert_called_once_with("food", 1.0, "cityu")
        self.assertEqual(data["places"][0]["fit"], "fits")
        self.assertNotIn("fit", live["places"][0])  # the fetcher's (cached) answer is not changed


if __name__ == "__main__":
    unittest.main()


class FundEditsBelowSpent(ServiceTest):
    """P0.1: a live fund edit can never go below what is already spent from that fund this week."""

    SUNDAY = "2027-03-07"  # one day left, so a HK$300 main meal fits today

    def setUp(self):
        super().setUp()
        self.svc = self.service(self.SUNDAY)
        self.svc.set_funds({**FUNDS, "main": 50000})
        self.svc.add_payment(30000, "main", "groceries")

    def test_reduce_below_spent_is_rejected_with_the_minimum(self):
        with self.assertRaises(ServiceError) as caught:
            self.svc.set_funds({**FUNDS, "main": 20000})
        self.assertEqual(caught.exception.details, {"field": "main", "minimum": 30000})
        self.assertIn("HK$300", str(caught.exception))
        state = self.svc.get_state()
        self.assertEqual(state["opening"]["main"], 50000)
        self.assertEqual(state["view"]["fundsNow"]["main"], 20000)

    def test_reduce_to_exactly_spent_is_accepted(self):
        state = self.svc.set_funds({**FUNDS, "main": 30000})
        self.assertEqual(state["opening"]["main"], 30000)
        self.assertEqual(state["view"]["fundsNow"]["main"], 0)

    def test_increase_is_accepted(self):
        state = self.svc.set_funds({**FUNDS, "main": 60000})
        self.assertEqual(state["view"]["fundsNow"]["main"], 30000)
        self.assertEqual([p["amount"] for p in state["payments"]], [30000])

    def test_reallocated_spending_counts_for_the_source_fund(self):
        # A main meal that spilled into Snacks: Snacks cannot go below what it gave.
        self.svc.set_funds({**FUNDS, "main": 30000, "snack": 8000})
        self.svc.add_payment(5000, "main", "dinner")  # main is empty, so all of it comes from Snacks
        self.assertEqual(self.svc.get_state()["view"]["fundsNow"]["snack"], 3000)
        with self.assertRaises(ServiceError) as caught:
            self.svc.set_funds({**FUNDS, "main": 30000, "snack": 4999})
        self.assertEqual(caught.exception.details, {"field": "snack", "minimum": 5000})

    def test_live_edit_does_not_touch_demo(self):
        self.svc.set_mode("demo", "sample")
        self.svc.add_payment(4800, "main", "demo lunch")
        demo_book = open_books(self.dir)["demo"]
        with demo_book.session() as s:
            before = (s.get_week(money.SAMPLE_WEEK_START), s.payments(money.SAMPLE_WEEK_START))
        self.svc.set_mode("live")
        with self.assertRaises(ServiceError):
            self.svc.set_funds({**FUNDS, "main": 100})
        self.svc.set_funds({**FUNDS, "main": 90000})
        with demo_book.session() as s:
            after = (s.get_week(money.SAMPLE_WEEK_START), s.payments(money.SAMPLE_WEEK_START))
        self.assertEqual(after, before)


class ZeroAllocation(ServiceTest):
    def test_a_fund_may_be_zero(self):
        state = self.svc.set_funds({**FUNDS, "snack": 0, "development": 0})
        self.assertEqual(state["opening"]["snack"], 0)
        self.assertEqual(state["view"]["allowance"], 15400)  # (77000 + 0) / 5 days
        result = self.svc.add_payment(15400, "main", "lunch")
        self.assertFalse(result["needsConfirm"])
        self.assertEqual(result["state"]["view"]["todayRemaining"], 0)


class Idempotency(ServiceTest):
    """P0.4: the same request id never records a second payment."""

    KEY = "0b8a3c1e-5d2f-4e6a-9c7b-1a2b3c4d5e6f"

    def setUp(self):
        super().setUp()
        self.svc.set_mode("demo", "sample")
        self.before = len(self.svc.get_state()["payments"])

    def test_same_key_twice_saves_once(self):
        first = self.svc.add_payment(4800, "main", "lunch", request_id=self.KEY)
        again = self.svc.add_payment(4800, "main", "lunch", request_id=self.KEY)
        self.assertFalse(again["needsConfirm"])
        self.assertTrue(again["replayed"])
        self.assertEqual(again["payment"], first["payment"])
        self.assertEqual(len(again["state"]["payments"]), self.before + 1)
        self.assertEqual(again["state"]["view"], first["state"]["view"])

    def test_confirmed_cover_with_same_key_saves_once(self):
        asked = self.svc.add_payment(15000, "main", "dinner", request_id=self.KEY)
        self.assertTrue(asked["needsConfirm"])  # nothing saved, the key is still free
        self.svc.add_payment(15000, "main", "dinner", choice="snack", request_id=self.KEY)
        again = self.svc.add_payment(15000, "main", "dinner", choice="snack", request_id=self.KEY)
        self.assertTrue(again["replayed"])
        self.assertEqual(len(self.svc.get_state()["payments"]), self.before + 1)

    def test_key_reused_for_another_payment_is_refused(self):
        self.svc.add_payment(4800, "main", "lunch", request_id=self.KEY)
        with self.assertRaises(ServiceError):
            self.svc.add_payment(5000, "main", "lunch", request_id=self.KEY)
        self.assertEqual(len(self.svc.get_state()["payments"]), self.before + 1)

    def test_bad_keys_are_refused(self):
        for bad in ("short", "x" * 65, "a b c d e f g h", 12345678, ["k"]):
            with self.subTest(bad=bad):
                with self.assertRaises(ServiceError):
                    self.svc.add_payment(4800, "main", "lunch", request_id=bad)
        self.assertEqual(len(self.svc.get_state()["payments"]), self.before)


class HongKongWeekRollover(ServiceTest):
    """P0.6: the live week turns over at Monday 00:00 in Hong Kong, whatever the computer's time zone."""

    def test_sunday_night_then_monday_morning(self):
        from datetime import datetime, timezone
        from ssust.dates import LiveClock
        moment = {"now": datetime(2027, 3, 7, 15, 59, tzinfo=timezone.utc)}  # Sun 23:59 HK
        svc = Service(open_books(self.dir), LiveClock(now=lambda: moment["now"]))
        svc.set_funds(FUNDS)
        state = svc.get_state()
        self.assertEqual((state["today"], state["weekStart"], state["view"]["daysLeft"]), ("2027-03-07", LIVE_MONDAY, 1))
        moment["now"] = datetime(2027, 3, 7, 16, 1, tzinfo=timezone.utc)  # Mon 00:01 HK
        state = svc.get_state()
        self.assertEqual((state["today"], state["weekStart"]), ("2027-03-08", "2027-03-08"))
        self.assertTrue(state["needsFunds"])
        self.assertEqual(state["prefill"], FUNDS)


def without_stamps(state):
    clean = json.loads(json.dumps(state))
    for p in clean["payments"]:
        p.pop("createdAt")
    return clean


class DemoReliability(ServiceTest):
    """P0.7: the demo is deterministic, and switching to it again restores the exact initial state."""

    def test_reset_restores_the_exact_initial_state(self):
        for scenario in ("sample", "empty", "over"):
            with self.subTest(scenario=scenario):
                initial = without_stamps(self.svc.set_mode("demo", scenario))
                if scenario == "sample":
                    self.svc.add_payment(4800, "main", "lunch")
                    self.svc.add_payment(10000, "main", "dinner", choice="snack")
                elif scenario == "over":
                    self.svc.add_payment(3000, "main", "late", choice="savings")
                self.svc.set_funds(FUNDS)
                again = without_stamps(self.svc.set_mode("demo", scenario))
                self.assertEqual(again, initial)

    def test_two_folders_give_the_same_demo(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        a = without_stamps(self.svc.set_mode("demo"))
        b = without_stamps(Service(open_books(Path(other.name)), FixedClock("2030-01-01")).set_mode("demo"))
        self.assertEqual(a, b)

    def test_walkthrough_numbers(self):
        """Every number in the demo walkthrough panel (index.html), step by step."""
        view = self.svc.set_mode("demo")["view"]
        self.assertEqual((view["allowance"], view["tomorrow"], view["lifeAtStart"]), (14000, 14000, 70000))
        self.assertEqual(view["fundsNow"], {"main": 66000, "snack": 4000, "fixed": 20000,
                                            "experience": 12000, "development": 8000, "savings": 50000})
        # Step 2: a HK$48 main meal.
        view = self.svc.add_payment(4800, "main", "lunch")["state"]["view"]
        self.assertEqual((view["todayRemaining"], view["fundsNow"]["main"], view["fundsNow"]["snack"]), (9200, 61200, 4000))
        # Step 3: HK$100 more leaves an HK$8 gap: Snacks (tomorrow HK$138) or Experience (tomorrow stays HK$140).
        asked = self.svc.add_payment(10000, "main", "dinner")
        by_choice = {o["choice"]: o for o in asked["options"]}
        self.assertEqual((by_choice["snack"]["from"]["snack"], by_choice["snack"]["tomorrowAfter"]), (800, 13800))
        self.assertEqual((by_choice[money.FLEX]["from"]["experience"], by_choice[money.FLEX]["tomorrowAfter"]), (800, 14000))
        # Step 4: HK$70 instead: HK$118 of HK$140, the notice, tomorrow stays HK$140.
        result = self.svc.add_payment(7000, "main", "dinner")
        view = result["state"]["view"]
        self.assertEqual((result["level"], view["spentToday"], view["notice"], view["tomorrow"]), (1, 11800, True, 14000))
        # Step 5: Experience HK$150: HK$30 from Development, HK$80 to HK$50.
        asked = self.svc.add_payment(15000, "experience", "concert")
        [option] = asked["options"]
        self.assertEqual((option["from"]["experience"], option["from"]["development"]), (12000, 3000))
        self.assertEqual(option["fundsAfter"]["development"], 5000)
        # Step 6: "Week already over", a HK$30 main meal comes out of Savings, HK$500 to HK$470.
        self.svc.set_mode("demo", "over")
        [option] = self.svc.add_payment(3000, "main", "late")["options"]
        self.assertEqual((option["choice"], option["fundsAfter"]["savings"]), ("savings", 47000))


class LegacyBorrowChoice(ServiceTest):
    """P1.1: the cover choice is now "flex"; the old API value is still accepted, as an alias."""

    def test_old_choice_value_saves_the_flex_option(self):
        self.svc.set_mode("demo", "sample")
        self.svc.add_payment(4800, "main", "lunch")
        flex = next(o for o in self.svc.add_payment(10000, "main", "dinner")["options"] if o["choice"] == "flex")
        result = self.svc.add_payment(10000, "main", "dinner", choice="bor" + "row")
        self.assertEqual(result["payment"]["from"], flex["from"])


class Undo(ServiceTest):
    """P1.3: undo restores the exact balances and allowances from before the payment."""

    def setUp(self):
        super().setUp()
        self.svc.set_mode("demo", "sample")

    def test_undo_a_normal_payment(self):
        before = self.svc.get_state()
        paid = self.svc.add_payment(4800, "main", "lunch")
        result = self.svc.undo_payment(paid["payment"]["id"])
        self.assertEqual(result["undone"]["id"], paid["payment"]["id"])
        self.assertEqual(result["state"]["view"], before["view"])
        self.assertEqual(comparable(result["state"]["payments"]), comparable(before["payments"]))

    def test_undo_a_payment_that_reallocated(self):
        self.svc.add_payment(4800, "main", "lunch")
        before = self.svc.get_state()
        paid = self.svc.add_payment(10000, "main", "dinner", choice="flex")
        self.assertEqual(paid["payment"]["from"]["experience"], 800)
        after_undo = self.svc.undo_payment(paid["payment"]["id"])["state"]
        self.assertEqual(after_undo["view"], before["view"])
        self.assertEqual(after_undo["view"]["fundsNow"]["experience"], 12000)
        self.assertEqual(after_undo["view"]["tomorrow"], 14000)

    def test_undo_savings_cover(self):
        self.svc.set_mode("demo", "over")
        before = self.svc.get_state()["view"]
        paid = self.svc.add_payment(3000, "main", "late", choice="savings")
        self.assertEqual(paid["state"]["view"]["fundsNow"]["savings"], 47000)
        self.assertEqual(self.svc.undo_payment(paid["payment"]["id"])["state"]["view"], before)

    def test_undo_an_earlier_payment_keeps_the_later_ones(self):
        first = self.svc.add_payment(4800, "main", "lunch")["payment"]["id"]
        self.svc.add_payment(1000, "snack", "tea")
        state = self.svc.undo_payment(first)["state"]
        self.assertEqual([p["note"] for p in state["payments"]][-1], "tea")
        self.assertEqual(state["view"]["spentToday"], 1000)

    def test_undo_twice_is_a_clear_error(self):
        pid = self.svc.add_payment(4800, "main", "lunch")["payment"]["id"]
        self.svc.undo_payment(pid)
        with self.assertRaises(ServiceError) as caught:
            self.svc.undo_payment(pid)
        self.assertIn("already undone", str(caught.exception))

    def test_replaying_an_undone_request_does_not_bring_it_back(self):
        key = "undo-replay-0001"
        pid = self.svc.add_payment(4800, "main", "lunch", request_id=key)["payment"]["id"]
        self.svc.undo_payment(pid)
        again = self.svc.add_payment(4800, "main", "lunch", request_id=key)
        self.assertTrue(again["replayed"])
        self.assertNotIn(pid, [p["id"] for p in again["state"]["payments"]])

    def test_bad_or_unknown_ids(self):
        for bad in (None, "1", 1.0, True, 0, -1, 10 ** 12):
            with self.subTest(bad=bad):
                with self.assertRaises(ServiceError):
                    self.svc.undo_payment(bad)

    def test_past_week_payments_cannot_be_undone(self):
        svc = self.service(LIVE_TODAY)
        svc.set_mode("live")
        svc.set_funds(FUNDS)
        pid = svc.add_payment(4800, "main", "lunch")["payment"]["id"]
        next_week = self.service("2027-03-08")
        with self.assertRaises(ServiceError):
            next_week.undo_payment(pid)
        self.assertEqual(len(svc.get_state()["payments"]), 1)

    def test_undo_in_demo_does_not_touch_live(self):
        self.svc.set_mode("live")
        self.svc.set_funds(FUNDS)
        live_id = self.svc.add_payment(4800, "main", "live lunch")["payment"]["id"]
        self.svc.set_mode("demo", "sample")
        demo_ids = [p["id"] for p in self.svc.get_state()["payments"]]
        self.assertIn(live_id, demo_ids)  # the same number exists in both books
        self.svc.undo_payment(live_id)
        live = self.svc.set_mode("live")
        self.assertEqual([p["note"] for p in live["payments"]], ["live lunch"])


class VerifiedPlaces(ServiceTest):
    """P1.5: a verified price (a test fixture here) puts its place first as "Fits"; estimates never fit."""

    def test_verified_fit_comes_first_and_estimates_never_fit(self):
        from ssust import prices
        nearest = places.snapshot_places("food", 3.0, "hkust")["places"]
        target = nearest[-1]
        records, problems = prices.validate_all([{
            "place": "Fixture", "osm_id": target["id"], "dish": "Fixture dish", "price_cents": 3000,
            "currency": "HKD", "source": "https://example.test/fixture", "verified_on": "2026-11-10", "campus": "hkust"}])
        self.assertEqual(problems, [])
        svc = Service(open_books(self.dir), FixedClock(LIVE_TODAY), verified=records, price_ranges=[], chains=[])
        svc.set_mode("demo")
        data = svc.places("food", 3.0, no_fetch)
        self.assertEqual(data["places"][0]["id"], target["id"])
        self.assertEqual(data["places"][0]["status"], "fits")
        self.assertEqual(data["budget"]["verifiedRecords"], 1)
        self.assertTrue(all(p["status"] in ("estimate", "unlikely", "unknown") for p in data["places"][1:]))

    def test_default_service_has_no_verified_prices(self):
        self.svc.set_mode("demo")
        data = self.svc.places("food", 3.0, no_fetch)
        self.assertEqual(data["budget"]["verifiedRecords"], 0)
        self.assertNotIn("fits", {p["status"] for p in data["places"]})


class Tanks(ServiceTest):
    """The state carries one tank per fund, recomputed after every payment and undo."""

    def test_state_has_tanks_matching_the_balances(self):
        state = self.svc.set_mode("demo", "sample")
        self.assertEqual(state["tanks"], money.fund_tanks(state))
        for tank in state["tanks"]:
            self.assertEqual(tank["allocation"], state["opening"][tank["fund"]])
            self.assertEqual(tank["remaining"], state["view"]["fundsNow"][tank["fund"]])

    def test_payment_and_undo_move_the_level(self):
        self.svc.set_mode("demo", "sample")
        before = self.svc.get_state()["tanks"]
        paid = self.svc.add_payment(4800, "main", "lunch")
        self.assertEqual(paid["state"]["tanks"][0]["remaining"], 61200)
        self.assertLess(paid["state"]["tanks"][0]["level"], before[0]["level"])
        undone = self.svc.undo_payment(paid["payment"]["id"])["state"]
        self.assertEqual(undone["tanks"], before)

    def test_demo_reset_restores_the_tanks_exactly(self):
        fresh = self.svc.set_mode("demo", "sample")["tanks"]
        self.svc.add_payment(4800, "main", "lunch")
        self.svc.add_payment(10000, "main", "dinner", choice="flex")
        self.assertEqual(self.svc.set_mode("demo", "sample")["tanks"], fresh)

    def test_empty_week_has_no_tanks(self):
        self.assertEqual(self.svc.get_state()["tanks"], [])


class FlexibleRollover(ServiceTest):
    """What is left in the flexible funds when a week ends moves to Long-term Savings."""

    def test_flex_left_counts_experience_and_development(self):
        state = self.svc.set_funds(FUNDS)
        self.assertEqual(state["view"]["flexLeft"], FUNDS["experience"] + FUNDS["development"])
        self.svc.add_payment(3000, "experience", "cinema")
        state = self.svc.get_state()
        self.assertEqual(state["view"]["flexLeft"], FUNDS["experience"] + FUNDS["development"] - 3000)

    def test_an_ended_week_hands_its_flex_and_savings_to_the_pot(self):
        self.svc.set_funds(FUNDS)
        self.svc.add_payment(3000, "experience", "cinema")
        self.assertIsNone(self.svc.get_state()["closed"])
        self.assertEqual(self.svc.get_state()["savingsPot"]["total"], 0)
        next_week = self.service("2027-03-08")  # the Monday after LIVE_MONDAY
        state = next_week.get_state()
        flex = FUNDS["experience"] + FUNDS["development"] - 3000
        self.assertEqual(state["savingsPot"], {"total": flex + FUNDS["savings"], "lastFlexMoved": flex,
                                               "lastWeek": LIVE_MONDAY})
        past = next_week.get_state(LIVE_MONDAY)
        self.assertEqual(past["closed"], {"flexMoved": flex, "savingsKept": FUNDS["savings"],
                                          "total": flex + FUNDS["savings"]})

    def test_state_carries_the_suggested_split_and_minimums(self):
        split = self.svc.get_state()["split"]
        self.assertEqual(sum(split["suggested"].values()), 100)
        self.assertEqual(split["minimum"]["savings"], 10)
        for fund in money.FUNDS:
            self.assertGreaterEqual(split["suggested"][fund], split["minimum"][fund])


class WeekCloseRule(unittest.TestCase):
    def test_overspent_funds_add_nothing(self):
        opening = {"main": 100, "snack": 0, "fixed": 0, "experience": 50, "development": 20, "savings": 30}
        payments = [{"from": {**money.empty_from(), "experience": 80}}]
        self.assertEqual(money.week_close(opening, payments), {"flexMoved": 20, "savingsKept": 30, "total": 50})

    def test_a_week_without_a_budget_closes_at_zero(self):
        self.assertEqual(money.week_close(None, [])["total"], 0)


class ZeroStart(ServiceTest):
    """A first Live launch starts at zero: no suggested amounts, no NaN, no negative days."""

    def test_fresh_live_has_no_amounts_and_no_prefill(self):
        state = self.svc.get_state()
        self.assertTrue(state["needsFunds"])
        self.assertIsNone(state["prefill"])
        self.assertEqual(state["opening"], NO_FUNDS)
        self.assertEqual(state["tanks"], [])
        self.assertGreaterEqual(state["view"]["daysLeft"], 1)

    def test_zero_budget_saved_every_day_of_the_week(self):
        for day in ("2027-03-01", "2027-03-03", "2027-03-07"):  # Monday, Wednesday, Sunday
            with self.subTest(day=day):
                svc = Service(open_books(Path(self._tmp.name) / day), FixedClock(day))
                state = svc.set_funds({fund: 0 for fund in money.FUNDS})
                view = state["view"]
                self.assertTrue(view["ready"])
                self.assertGreaterEqual(view["daysLeft"], 1)
                self.assertGreaterEqual(view["daysAfter"], 0)
                for key in ("allowance", "todayRemaining", "tomorrow", "lifeNow", "spentToday", "flexLeft"):
                    self.assertEqual(view[key], 0, key)
                    self.assertIs(type(view[key]), int)
                self.assertEqual({t["fund"]: (t["level"], t["percent"], t["tone"]) for t in state["tanks"]},
                                 {fund: (0, 0, "none") for fund in money.FUNDS})

    def test_a_payment_on_a_zero_budget_is_refused_not_saved(self):
        self.svc.set_funds({fund: 0 for fund in money.FUNDS})
        with self.assertRaises(ServiceError):
            self.svc.add_payment(1000, "main")
        self.assertEqual(self.svc.get_state()["payments"], [])


class ProjectionInState(ServiceTest):
    def test_demo_sample_week_has_a_projection(self):
        state = self.svc.set_mode("demo")
        proj = state["projection"]
        self.assertTrue(proj["ready"])
        self.assertEqual(proj["days"], 3)
        self.assertEqual(proj["real"][-1]["cents"], 15000)
        self.assertEqual(proj["avgDaily"], 5000)
        self.assertEqual(proj["pace"], 17857)  # (77000 + 8000 + 20000 + 12000 + 8000) / 7
        self.assertEqual(proj["status"], "comfortable")

    def test_fresh_live_has_none(self):
        proj = self.svc.get_state()["projection"]
        self.assertFalse(proj["ready"])

    def test_payments_from_earlier_weeks_count(self):
        Service(open_books(self.dir), FixedClock("2027-02-26")).set_funds(FUNDS)
        Service(open_books(self.dir), FixedClock("2027-02-26")).add_payment(3000, "main")
        self.svc.set_funds(FUNDS)
        proj = self.svc.get_state()["projection"]
        self.assertTrue(proj["ready"])
        self.assertEqual(proj["days"], 6)  # Friday 26 Feb to Wednesday 3 Mar
        self.assertEqual(proj["real"][0], {"date": "2027-02-26", "cents": 3000})

    def test_undone_payment_leaves_the_projection(self):
        self.svc.set_funds(FUNDS)
        saved = self.svc.add_payment(3000, "main")["payment"]
        state = self.svc.undo_payment(saved["id"])["state"]
        self.assertEqual(state["projection"]["days"], 0)


class Inbox(ServiceTest):
    """Connected payments (simulated): an inbox confirmed through the normal payment logic."""

    def tap(self, amount=3800, merchant="Sample Coffee Kiosk", external="tap-0001-abcd", source="apple_pay"):
        return self.svc.inbox_add(source, amount, merchant, "Sample card 0000", external)

    def setUp(self):
        super().setUp()
        self.svc.set_funds(FUNDS)

    def test_add_is_idempotent_and_shows_in_the_state(self):
        first = self.tap()
        again = self.tap(amount=1)
        self.assertTrue(first["created"])
        self.assertFalse(again["created"])
        [item] = again["state"]["inbox"]
        self.assertEqual((item["amount"], item["merchant"]), (3800, "Sample Coffee Kiosk"))

    def test_no_memory_uses_the_assistant_guess_with_its_reason(self):
        item = self.tap()["state"]["inbox"][0]
        self.assertEqual((item["suggestedFund"], item["suggestedReason"]), ("snack", '"coffee"'))
        item = self.tap(merchant="Sample Shop", external="tap-0009-abcd")["state"]["inbox"][1]
        self.assertEqual(item["suggestedFund"], "main")
        self.assertEqual(item["suggestedReason"], "no clear clue, so Main meals")

    def test_typo_check_runs_on_inbox_items(self):
        state = self.tap(amount=48000, merchant="Sample Noodle Bar")["state"]
        [item] = state["inbox"]
        self.assertEqual(item["suggestedFund"], "main")
        self.assertEqual(item["typo"]["suggestion"], 4800)
        normal = self.tap(amount=4800, merchant="Sample Noodle Bar", external="tap-0010-abcd")["state"]["inbox"][1]
        self.assertIsNone(normal["typo"])

    def test_remembered_fund_wins_over_the_guess(self):
        item = self.tap()["state"]["inbox"][0]
        self.svc.inbox_confirm(item["id"], "experience")
        nxt = self.tap(external="tap-0002-abcd")["state"]["inbox"][0]
        self.assertEqual((nxt["suggestedFund"], nxt["suggestedReason"]), ("experience", "used last time at this merchant"))

    def test_confirm_saves_a_payment_and_remembers_the_fund(self):
        item = self.tap()["state"]["inbox"][0]
        result = self.svc.inbox_confirm(item["id"], "snack")
        self.assertFalse(result["needsConfirm"])
        self.assertEqual((result["payment"]["amount"], result["payment"]["category"]), (3800, "snack"))
        self.assertEqual(result["payment"]["note"], "Sample Coffee Kiosk")
        self.assertEqual(result["state"]["inbox"], [])
        nxt = self.tap(external="tap-0002-abcd")["state"]["inbox"][0]
        self.assertEqual(nxt["suggestedFund"], "snack")
        with self.assertRaises(ServiceError):
            self.svc.inbox_confirm(item["id"], "snack")  # already handled

    def test_confirm_uses_the_overspend_step(self):
        item = self.tap(amount=30000)["state"]["inbox"][0]  # more than today's HK$170
        ask = self.svc.inbox_confirm(item["id"], "main")
        self.assertTrue(ask["needsConfirm"])
        self.assertEqual(len(ask["state"]["inbox"]), 1)  # still pending until a cover is chosen
        self.assertEqual(ask["state"]["payments"], [])
        done = self.svc.inbox_confirm(item["id"], "main", choice=ask["options"][0]["choice"])
        self.assertFalse(done["needsConfirm"])
        self.assertEqual(done["state"]["inbox"], [])
        self.assertEqual(len(done["state"]["payments"]), 1)

    def test_confirm_is_the_same_as_add_payment(self):
        item = self.tap(amount=5000)["state"]["inbox"][0]
        via_inbox = self.svc.inbox_confirm(item["id"], "main")["state"]["view"]
        other = Service(open_books(Path(self._tmp.name) / "other"), FixedClock(LIVE_TODAY))
        other.set_funds(FUNDS)
        direct = other.add_payment(5000, "main", "Sample Coffee Kiosk")["state"]["view"]
        self.assertEqual(via_inbox, direct)

    def test_confirmed_payment_can_be_undone(self):
        item = self.tap()["state"]["inbox"][0]
        payment = self.svc.inbox_confirm(item["id"], "main")["payment"]
        state = self.svc.undo_payment(payment["id"])["state"]
        self.assertEqual(state["payments"], [])

    def test_dismiss(self):
        item = self.tap()["state"]["inbox"][0]
        state = self.svc.inbox_dismiss(item["id"])
        self.assertEqual(state["inbox"], [])
        self.assertEqual(state["payments"], [])
        with self.assertRaises(ServiceError):
            self.svc.inbox_dismiss(item["id"])

    def test_bad_input(self):
        for args in (("bank", 100, "Shop", "card", "tap-0003-abcd"), ("apple_pay", 0, "Shop", "card", "tap-0003-abcd"),
                     ("apple_pay", 100, "", "card", "tap-0003-abcd"), ("apple_pay", 100, "Shop", "card", "x")):
            with self.subTest(args=args), self.assertRaises(ServiceError):
                self.svc.inbox_add(*args)
        with self.assertRaises(ServiceError):
            self.svc.inbox_confirm(999, "main")
        item = self.tap()["state"]["inbox"][0]
        with self.assertRaises(ServiceError):
            self.svc.inbox_confirm(item["id"], "savings")

    def test_live_and_demo_inboxes_are_separate_and_demo_resets(self):
        self.tap()
        demo = self.svc.set_mode("demo")
        self.assertEqual(demo["inbox"], [])
        self.svc.inbox_add("octopus", 2450, "Sample Convenience Store", "Sample Octopus", "tap-0009-abcd")
        self.assertEqual(len(self.svc.set_mode("demo")["inbox"]), 0)  # a demo restart empties it
        self.assertEqual(len(self.svc.set_mode("live")["inbox"]), 1)

    def test_connected_sources(self):
        state = self.svc.get_state()
        self.assertEqual(state["connected"], {"apple_pay": False, "octopus": False, "hsbc": False})
        state = self.svc.set_connected("octopus", True)
        self.assertTrue(state["connected"]["octopus"])
        with self.assertRaises(ServiceError):
            self.svc.set_connected("bank", True)


class RangePlaces(ServiceTest):
    def test_shipped_ranges_reach_the_map(self):
        self.svc.set_mode("demo")
        self.svc.set_campus("hkust")
        data = self.svc.places("food", 3.0, lambda *a: None)
        with_range = [p for p in data["places"] if p.get("priceRange")]
        self.assertGreater(len(with_range), 0)
        self.assertGreater(data["budget"]["rangeRecords"], 0)
        for place in with_range:
            self.assertTrue(place["priceRange"]["sourceUrl"].startswith("https://"))
            self.assertIn(place["status"], ("range_fits", "range_may", "range_over"))
class ChainPrices(ServiceTest):
    """A chain's published meal range applies to every branch the name matches, shown apart from verified."""

    def chain(self, **over):
        from ssust import prices
        raw = {"chain": "Test Chain", "names": ["McDonald's", "麥當勞"], "what": "Sets", "low_cents": 2900,
               "high_cents": 4600, "sources": ["https://example.test/menu"], "checked_on": "2026-11-15",
               "needs_check": True, **over}
        chain, problem = prices.validate_chain(raw)
        self.assertIsNone(problem)
        return chain

    def test_matches_english_and_chinese_names_and_ignores_others(self):
        from ssust import prices
        chain = self.chain()
        self.assertIs(prices.match_chain({"name": "McDonald's"}, [chain]), chain)
        self.assertIs(prices.match_chain({"name": "麥當勞 McDonald's (HKUST)"}, [chain]), chain)
        self.assertIsNone(prices.match_chain({"name": "Lucky Dragon Restaurant"}, [chain]))

    def test_states_follow_the_range(self):
        chain = self.chain()
        place = {"id": "node/1", "name": "McDonald's", "price": "cheap", "distanceKm": 0.1}
        for remaining, status in ((5000, "chain_fits"), (3000, "chain_tight"), (2000, "chain_over"), (None, "chain")):
            [item] = fit.rank_places([place], remaining, [], chains=[chain])
            self.assertEqual(item["status"], status)
            self.assertEqual(item["chain"]["lowCents"], 2900)

    def test_verified_price_wins_over_a_chain_price(self):
        from ssust import prices
        records, _ = prices.validate_all([{
            "place": "McDonald's", "osm_id": "node/1", "dish": "Big Mac set", "price_cents": 4450, "currency": "HKD",
            "source": "visited in person", "verified_on": "2026-11-15", "campus": "hkust"}])
        place = {"id": "node/1", "name": "McDonald's", "price": "cheap", "distanceKm": 0.1}
        [item] = fit.rank_places([place], 5000, records, chains=[self.chain()])
        self.assertEqual(item["status"], "fits")
        self.assertIsNone(item["chain"])

    def test_bad_chain_records_are_rejected(self):
        from ssust import prices
        base = {"chain": "X", "names": ["Xy"], "what": "Sets", "low_cents": 100, "high_cents": 200,
                "sources": ["visited in person"], "checked_on": "2026-11-15", "needs_check": False}
        for bad in ({"low_cents": 300}, {"names": ["X"]}, {"sources": []}, {"checked_on": "soon"},
                    {"needs_check": "yes"}, {"extra": 1}):
            self.assertIsNotNone(prices.validate_chain({**base, **bad})[1], bad)

    def test_shipped_chain_file_is_valid(self):
        from ssust import prices
        chains, problems = prices.load_chains()
        self.assertEqual(problems, [])
        self.assertGreater(len(chains), 0)
