"""Rewards, meals logged at a place and feedback, through the store, the service and the API."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ssust import money
from ssust.dates import FixedClock
from ssust.service import Service, ServiceError
from ssust.store import open_books

from tests.test_api import FUNDS_TEXT, LIVE_MONDAY, ApiTest

PLACE = {"id": "node/123456", "name": "Nan Yuan"}


class TempBooks(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.books = open_books(self.dir)

    def payment(self, s, date, amount=5000):
        return s.add_payment({"date": date, "amount": amount, "category": "main", "note": "",
                              "from": {**money.empty_from(), "main": amount}})


class StoreV5(TempBooks):
    def test_tables(self):
        con = sqlite3.connect(self.dir / "ssust.db")
        try:
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            con.close()
        self.assertTrue({"visits", "feedback"} <= tables)

    def test_visit_counts_distinct_places_within_budget_and_skip_undone(self):
        with self.books["live"].session(write=True) as s:
            a = self.payment(s, "2026-11-23")
            b = self.payment(s, "2026-11-23")
            c = self.payment(s, "2026-11-23")
            d = self.payment(s, "2026-11-23")
            s.add_visit(a, "hkbu", "node/1", "A", True)
            s.add_visit(b, "hkbu", "node/1", "A", True)  # the same place again
            s.add_visit(c, "hkbu", "node/2", "B", False)  # over that day's money
            s.add_visit(d, "hkust", "node/3", "C", True)
            s.add_visit(d, "hkust", "node/3", "C", True)  # one visit per payment
            self.assertEqual(s.visit_counts(), {"hkbu": 1, "hkust": 1})
            s.void_payment(d)
            self.assertEqual(s.visit_counts(), {"hkbu": 1})

    def test_payment_dates(self):
        with self.books["live"].session(write=True) as s:
            self.payment(s, "2026-11-22")
            self.payment(s, "2026-11-22")
            gone = self.payment(s, "2026-11-23")
            s.void_payment(gone)
            self.assertEqual(s.payment_dates(), ["2026-11-22"])
            self.assertEqual(s.payment_count(), 2)

    def test_feedback_newest_first(self):
        with self.books["live"].session(write=True) as s:
            s.add_feedback(4, "Nice", "2026-11-23T10:00:00+00:00")
            s.add_feedback(2, "Map is slow", "2026-11-23T11:00:00+00:00")
            rows = s.feedback()
        self.assertEqual([(r["rating"], r["text"]) for r in rows], [(2, "Map is slow"), (4, "Nice")])
        self.assertEqual(rows[0]["createdAt"], "2026-11-23T11:00:00+00:00")

    def test_demo_reset_clears_them(self):
        with self.books["demo"].session(write=True) as s:
            p = self.payment(s, "2026-11-11")
            s.add_visit(p, "hkbu", "node/1", "A", True)
            s.add_feedback(5, "x")
            s.reset()
            self.assertEqual((s.visit_counts(), s.feedback()), ({}, []))


class ServiceRewards(TempBooks):
    def service(self, today):
        return Service(self.books, FixedClock(today))

    def set_week(self, service, opening=None):
        return service.set_funds(opening or dict(money.SAMPLE_OPENING))

    def test_state_has_rewards(self):
        svc = self.service("2026-11-25")
        state = self.set_week(svc)
        rewards = state["rewards"]
        self.assertEqual(rewards["streak"]["days"], 0)
        self.assertIsNone(rewards["lastWeek"])
        self.assertEqual({row["campus"] for row in rewards["medals"]}, {c["id"] for c in state["campuses"]})
        self.assertEqual(rewards["badges"][1]["id"], "planner")
        self.assertTrue(rewards["badges"][1]["earned"])

    def test_streak_follows_payments(self):
        svc = self.service("2026-11-25")
        self.set_week(svc)
        state = svc.add_payment(3000, "main", "lunch")["state"]
        self.assertEqual((state["rewards"]["streak"]["days"], state["rewards"]["streak"]["shape"]), (1, "square"))

    def test_last_week_stars(self):
        svc = self.service("2026-11-18")
        self.set_week(svc)
        svc.add_payment(3000, "main", "lunch")
        later = self.service("2026-11-25")
        state = self.set_week(later)
        last = state["rewards"]["lastWeek"]
        self.assertEqual(last["weekStart"], "2026-11-16")
        self.assertEqual(last["stars"], 5)

    def test_a_meal_at_a_place_within_budget_counts_for_the_medal(self):
        svc = self.service("2026-11-25")
        state = self.set_week(svc)
        result = svc.add_payment(3000, "main", "Nan Yuan", place=PLACE)
        row = next(r for r in result["state"]["rewards"]["medals"] if r["campus"] == state["campus"])
        self.assertEqual(row["count"], 1)

    def test_a_meal_over_todays_money_does_not_count(self):
        svc = self.service("2026-11-25")
        state = self.set_week(svc)
        too_much = state["view"]["todayRemaining"] + 100
        result = svc.add_payment(too_much, "main", "Nan Yuan", place=PLACE)
        row = next(r for r in result["state"]["rewards"]["medals"] if r["campus"] == state["campus"])
        self.assertEqual(row["count"], 0)

    def test_bad_places_are_refused(self):
        svc = self.service("2026-11-25")
        self.set_week(svc)
        for place in ("node/1", {"id": "x", "name": "A"}, {"id": "node/1"}, {"id": "node/1", "name": 3},
                      {"id": "node/" + "1" * 30, "name": "A"}):
            with self.subTest(place=place):
                with self.assertRaises(ServiceError):
                    svc.add_payment(3000, "main", "", place=place)

    def test_a_replayed_request_records_one_visit(self):
        svc = self.service("2026-11-25")
        self.set_week(svc)
        svc.add_payment(3000, "main", "", request_id="req-12345678", place=PLACE)
        svc.add_payment(3000, "main", "", request_id="req-12345678", place=PLACE)
        with self.books["live"].session() as s:
            self.assertEqual(sum(s.visit_counts().values()), 1)

    def test_feedback(self):
        svc = self.service("2026-11-25")
        got = svc.add_feedback(5, "  Love the tanks  ")
        self.assertEqual(got["feedback"][0]["text"], "Love the tanks")
        self.assertEqual(svc.feedback()["feedback"][0]["rating"], 5)

    def test_feedback_is_checked(self):
        svc = self.service("2026-11-25")
        for rating, text in ((0, "a"), (6, "a"), (True, "a"), ("5", "a"), (3, 7), (3, "x" * 501)):
            with self.subTest(rating=rating, text=str(text)[:10]):
                with self.assertRaises(ServiceError):
                    svc.add_feedback(rating, text)
        self.assertEqual(svc.add_feedback(3, "")["feedback"][0]["text"], "")
        cleaned = svc.add_feedback(3, "line one\nline two <b>")["feedback"][0]["text"]
        self.assertEqual(cleaned, "line one\nline two b")


class RewardsApi(ApiTest):
    def test_payment_with_a_place(self):
        self.set_funds()
        data = self.call("POST", "/api/payments", {"amount": "30", "category": "main", "note": "Nan Yuan",
                                                   "requestId": "req-abcdefgh", "place": PLACE})
        self.assertIn("rewards", data["state"])
        self.call("POST", "/api/payments", {"amount": "30", "category": "main", "place": "node/1"}, status=400)

    def test_feedback_routes(self):
        self.assertEqual(self.call("GET", "/api/feedback"), {"feedback": []})
        data = self.call("POST", "/api/feedback", {"rating": 4, "text": "Good"})
        self.assertEqual(data["feedback"][0]["rating"], 4)
        self.call("POST", "/api/feedback", {"rating": 9, "text": "Good"}, status=400)
        self.call("POST", "/api/feedback", {"text": "Good"}, status=400)


if __name__ == "__main__":
    unittest.main()
