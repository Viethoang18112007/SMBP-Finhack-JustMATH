"""HTTP API tests on a real server bound to port 0.

Each test gets its own temporary data folder (never the real data/ folder) and
a stub places fetcher. urllib's urlopen is patched to fail, so no test can
reach the network. Requests go through http.client to 127.0.0.1.
"""

import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ssust import fit, money, places
from ssust.dates import FixedClock
from ssust.server import make_server
from ssust.service import CHOICES, SCENARIOS, Service
from ssust.store import open_books

LIVE_TODAY = "2027-03-03"  # a Wednesday, far from the demo week
LIVE_MONDAY = "2027-03-01"
FUNDS_TEXT = {fund: f"{cents // 100}.{cents % 100:02d}" for fund, cents in money.SAMPLE_OPENING.items()}
SECURITY_HEADERS = ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
                    "Content-Security-Policy", "Cache-Control")

_no_network = mock.patch("urllib.request.urlopen", side_effect=AssertionError("tests must not use the network"))


def setUpModule():
    _no_network.start()


def tearDownModule():
    _no_network.stop()


def no_fetch(kind, radius_km, campus):
    raise AssertionError("the places fetcher must not be called")


class ApiTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "data"
        self.fetcher = mock.Mock(side_effect=no_fetch)
        self.start()

    def start(self):
        server = make_server(self.dir, FixedClock(LIVE_TODAY), port=0,
                             places_fetcher=self.fetcher, quiet=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.server, self.thread = server, thread
        self.port = server.server_address[1]
        self.addCleanup(self.stop, server, thread)

    @staticmethod
    def stop(server, thread):
        if thread.is_alive():
            server.shutdown()
            thread.join(5)
        server.server_close()

    def request(self, method, path, body=None, content_type="application/json", host=None, length=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        elif body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}" if host is None else host)
            if body is not None:
                conn.putheader("Content-Type", content_type)
                conn.putheader("Content-Length", str(len(body)) if length is None else length)
            conn.endheaders(body)
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def call(self, method, path, body=None, status=200, **kw):
        got, headers, payload = self.request(method, path, body, **kw)
        self.assertEqual(got, status, payload)
        self.assertIn("application/json", headers["Content-Type"])
        data = json.loads(payload)
        if status >= 400:
            self.assertIsInstance(data.get("error"), str)
        return data

    def state(self, query=""):
        return self.call("GET", "/api/state" + query)

    def set_funds(self):
        return self.call("POST", "/api/settings", FUNDS_TEXT)

    def demo(self, scenario=None):
        body = {"mode": "demo"} if scenario is None else {"mode": "demo", "scenario": scenario}
        return self.call("POST", "/api/mode", body)


class Routes(ApiTest):
    def test_state_on_a_fresh_live_db(self):
        state = self.state()
        self.assertEqual(state["mode"], "live")
        self.assertEqual(state["today"], LIVE_TODAY)
        self.assertEqual(state["weekStart"], LIVE_MONDAY)
        self.assertTrue(state["needsFunds"])
        self.assertEqual(state["payments"], [])

    def test_settings_store_whole_cents(self):
        state = self.set_funds()
        self.assertEqual(state["opening"], money.SAMPLE_OPENING)
        self.assertFalse(state["needsFunds"])
        self.assertEqual(self.state()["opening"], money.SAMPLE_OPENING)

    def test_payment_is_saved_in_cents(self):
        self.set_funds()
        result = self.call("POST", "/api/payments", {"amount": "HK$48.50", "category": "main", "note": "lunch"})
        self.assertFalse(result["needsConfirm"])
        [payment] = result["state"]["payments"]
        self.assertEqual((payment["amount"], payment["category"], payment["note"], payment["date"]),
                         (4850, "main", "lunch", LIVE_TODAY))
        self.assertEqual(self.state()["payments"], result["state"]["payments"])

    def test_mode_switches_between_demo_and_live(self):
        state = self.demo()
        self.assertEqual((state["mode"], state["scenario"], state["today"]),
                         ("demo", "sample", money.SAMPLE_TODAY))
        self.assertEqual(len(state["payments"]), len(money.make_state("sample")["payments"]))
        self.assertEqual(self.demo("over")["scenario"], "over")
        state = self.call("POST", "/api/mode", {"mode": "live"})
        self.assertEqual((state["mode"], state["today"], state["payments"]), ("live", LIVE_TODAY, []))

    def test_week_query(self):
        self.set_funds()
        self.assertEqual(self.state(f"?week={LIVE_MONDAY}")["opening"], money.SAMPLE_OPENING)
        past = self.state("?week=2027-02-22")
        self.assertTrue(past["needsFunds"])
        self.assertIsNone(past["prefill"])
        for week in ("2027-03-03", "2027-03-08", "abc", ""):
            with self.subTest(week=week):
                self.call("GET", "/api/state?week=" + week, status=400)

    def test_static_files(self):
        for path, kind in (("/", "text/html"), ("/index.html", "text/html"), ("/styles.css", "text/css"),
                           ("/js/main.js", "text/javascript"), ("/vendor/leaflet/leaflet.js", "text/javascript"),
                           ("/vendor/leaflet/leaflet.css", "text/css")):
            with self.subTest(path=path):
                status, headers, payload = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertIn(kind, headers["Content-Type"])
                self.assertEqual(int(headers["Content-Length"]), len(payload))
                self.assertGreater(len(payload), 0)


class ConfirmFlow(ApiTest):
    def setUp(self):
        super().setUp()
        self.demo()
        self.count = len(self.state()["payments"])

    def test_gap_asks_first_and_saves_nothing(self):
        result = self.call("POST", "/api/payments", {"amount": "150", "category": "main"})
        self.assertTrue(result["needsConfirm"])
        self.assertEqual([o["choice"] for o in result["options"]], ["snack", "flex"])
        self.assertEqual(len(self.state()["payments"]), self.count)

    def test_chosen_cover_is_saved(self):
        result = self.call("POST", "/api/payments", {"amount": "150", "category": "main", "choice": "snack"})
        self.assertFalse(result["needsConfirm"])
        self.assertEqual(len(result["state"]["payments"]), self.count + 1)
        self.assertEqual(result["state"]["payments"][-1]["amount"], 15000)

    def test_cover_not_offered_is_refused(self):
        result = self.call("POST", "/api/payments", {"amount": "200", "category": "main"})
        offered = {o["choice"] for o in result["options"]}
        missing = [choice for choice in CHOICES if choice not in offered]
        self.assertTrue(missing)
        for choice in missing:
            with self.subTest(choice=choice):
                self.call("POST", "/api/payments", {"amount": "200", "category": "main", "choice": choice}, status=400)
        self.assertEqual(len(self.state()["payments"]), self.count)


class BadInputGets400(ApiTest):
    """Every case from the former test_server_errors.py, now on a real server."""

    def setUp(self):
        super().setUp()
        self.demo()
        self.before = self.state()["payments"]

    def test_payment_with_bad_amounts(self):
        for amount in ("²", "1.²", "١٢", "４８", "", "-5", 48, None, ["48"], {"a": 1}):
            with self.subTest(amount=amount):
                self.call("POST", "/api/payments", {"amount": amount, "category": "main"}, status=400)
        self.assertEqual(self.state()["payments"], self.before)

    def test_payment_with_bad_fields(self):
        for extra in ({"category": ["main"]}, {"category": {"a": 1}}, {"category": "savings"},
                      {"note": 5}, {"note": ["a"]}, {"choice": ["snack"]}, {"choice": "nope"}):
            with self.subTest(extra=extra):
                self.call("POST", "/api/payments", {"amount": "10", "category": "main", **extra}, status=400)
        self.assertEqual(self.state()["payments"], self.before)

    def test_payment_before_funds_are_set(self):
        self.call("POST", "/api/mode", {"mode": "live"})
        self.call("POST", "/api/payments", {"amount": "10", "category": "main"}, status=400)

    def test_settings_with_bad_amounts(self):
        good = dict(FUNDS_TEXT)
        for bad in ("²", "١٢", "-1", "12,50", 100, None, ["1"]):
            with self.subTest(bad=bad):
                self.call("POST", "/api/settings", {**good, "main": bad}, status=400)
        missing = dict(good)
        del missing["savings"]
        self.call("POST", "/api/settings", missing, status=400)
        self.assertEqual(self.state()["scenario"], "sample")

    def test_mode_with_bad_values(self):
        for body in ({"mode": "nope"}, {"mode": ["sample"]}, {"mode": {"a": 1}}, {"mode": None},
                     {"mode": "sample"}, {"mode": "live", "scenario": "sample"},
                     {"mode": "demo", "scenario": "nope"}, {"mode": "demo", "scenario": ["over"]}):
            with self.subTest(body=body):
                self.call("POST", "/api/mode", body, status=400)

    def test_unreadable_bodies(self):
        cases = [
            ("not json", {}),
            ("[1, 2]", {}),
            (b"\xff", {}),
            ("[" * 3000, {}),  # nested deeper than the JSON parser allows
            ("{}", {"content_type": "text/plain"}),
            ("{}", {"length": "abc"}),
            ("{}", {"length": "0"}),
            ("{}", {"length": "-1"}),
            ("{}", {"length": "99999"}),
            ('{"note": "' + "a" * 5000 + '"}', {}),  # a real body over the size limit
        ]
        for body, kw in cases:
            with self.subTest(body=body[:10], **kw):
                self.call("POST", "/api/payments", body, status=400, **kw)

    def test_unread_body_still_gets_its_400(self):
        """The server answers before reading these bodies; the client must still get the 400, not a reset."""
        big = '{"note": "' + "a" * 50000 + '"}'
        for body, kw in ((big, {}), (big, {"content_type": "text/plain"}), (big, {"length": "abc"})):
            with self.subTest(**kw):
                self.call("POST", "/api/payments", body, status=400, **kw)

    def test_bad_map_filters(self):
        for query in ("kind=nope", "radius=abc", "radius=1e9", "kind=food&radius=-1"):
            with self.subTest(query=query):
                self.call("GET", "/api/places?" + query, status=400)


class HostAndPaths(ApiTest):
    def test_bad_host_is_refused(self):
        for host in ("evil.example", f"evil.example:{self.port}", "127.0.0.1:1", "127.0.0.1", ""):
            with self.subTest(host=host):
                self.call("GET", "/api/state", host=host, status=400)
                self.call("POST", "/api/mode", {"mode": "demo"}, host=host, status=400)
        self.assertEqual(self.state()["mode"], "live")

    def test_localhost_with_the_bound_port_is_accepted(self):
        self.call("GET", "/api/state", host=f"localhost:{self.port}")

    def test_unknown_paths_get_404(self):
        for path in ("/nope.html", "/api/nope", "/vendor/", "/../run.bat", "/%2e%2e/run.bat",
                     "/vendor/../../backend/server.py", "/..%2f..%2fbackend/server.py",
                     "/%5c..%5cbackend%5cserver.py", "/index.html%00.js", "/../README.md",
                     "/../.gitignore", "//etc/passwd"):
            with self.subTest(path=path):
                self.call("GET", path, status=404)
        self.call("POST", "/api/nope", {"a": 1}, status=404)
        self.call("POST", "/index.html", {"a": 1}, status=404)


class SecurityHeaders(ApiTest):
    def test_headers_on_every_kind_of_response(self):
        responses = {
            "json": self.request("GET", "/api/state"),
            "static": self.request("GET", "/"),
            "400": self.request("POST", "/api/mode", {"mode": "nope"}),
            "404": self.request("GET", "/nope"),
            "bad host": self.request("GET", "/", host="evil.example"),
        }
        for name, (_status, headers, _payload) in responses.items():
            for header in SECURITY_HEADERS:
                with self.subTest(response=name, header=header):
                    self.assertTrue(headers[header])
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])


class UnexpectedErrors(ApiTest):
    """A bug inside an action answers 500 JSON without details, never a dropped connection."""

    def assert_clean_500(self, method, path, body=None):
        status, headers, payload = self.request(method, path, body)
        self.assertEqual(status, 500)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertIsInstance(json.loads(payload)["error"], str)
        self.assertNotIn(b"Traceback", payload)
        self.assertNotIn(b"secret", payload)
        for header in SECURITY_HEADERS:
            self.assertTrue(headers[header])

    def test_get_and_post(self):
        boom = RuntimeError("secret internal detail")
        with mock.patch.object(Service, "get_state", side_effect=boom):
            self.assert_clean_500("GET", "/api/state")
        with mock.patch.object(Service, "set_mode", side_effect=KeyError("secret")):
            self.assert_clean_500("POST", "/api/mode", {"mode": "demo"})

    def test_plain_value_error_is_not_shown(self):
        with mock.patch.object(Service, "add_payment", side_effect=ValueError("secret column")):
            self.assert_clean_500("POST", "/api/payments", {"amount": "10", "category": "main"})

    def test_server_keeps_working_afterwards(self):
        with mock.patch.object(Service, "get_state", side_effect=RuntimeError("secret")):
            self.assert_clean_500("GET", "/api/state")
        self.assertEqual(self.state()["mode"], "live")


class Places(ApiTest):
    LIVE_PAYLOAD = {"center": {"name": "HKUST", "lat": 22.338, "lng": 114.263}, "kind": "food",
                    "radiusKm": 3.0, "sample": False, "source": "OpenStreetMap", "shown": 0,
                    "total": 0, "places": []}

    def test_demo_reads_the_snapshot_and_never_fetches(self):
        self.demo()
        for kind in ("food", "shop"):
            with self.subTest(kind=kind):
                data = self.call("GET", f"/api/places?kind={kind}&radius=10")
                self.assertEqual((data["source"], data["kind"]), ("snapshot", kind))
                self.assertTrue(data["fetchedAt"])
                self.assertGreater(data["total"], 0)
        self.fetcher.assert_not_called()

    def test_live_uses_the_fetcher(self):
        self.fetcher.side_effect = None
        self.fetcher.return_value = self.LIVE_PAYLOAD
        data = self.call("GET", "/api/places?kind=food&radius=3")
        budget = data.pop("budget")
        self.assertEqual(data, self.LIVE_PAYLOAD)
        self.assertIsNone(budget["remaining"])  # funds not set yet
        self.fetcher.assert_called_once_with("food", 3.0, "hkust")

    def test_default_filters(self):
        self.fetcher.side_effect = None
        self.fetcher.return_value = self.LIVE_PAYLOAD
        self.call("GET", "/api/places")
        self.fetcher.assert_called_once_with("food", 3.0, "hkust")

    def test_live_falls_back_to_the_snapshot(self):
        for error in (urllib.error.URLError("offline"), TimeoutError(), ValueError("bad json"), RuntimeError("bug")):
            with self.subTest(error=type(error).__name__):
                self.fetcher.side_effect = error
                data = self.call("GET", "/api/places?kind=shop&radius=5")
                self.assertEqual((data["source"], data["kind"], data["radiusKm"]), ("snapshot", "shop", 5.0))
                self.assertTrue(data["fetchedAt"])

    def test_demo_food_fits_today_left(self):
        self.demo()
        data = self.call("GET", "/api/places?kind=food&radius=3")
        self.assertEqual(data["budget"]["remaining"], 14000)
        self.assertEqual(data["budget"]["perMeal"], 7000)
        expected = sorted(fit.fit_for(p["price"], 7000) for p in places.snapshot_places("food", 3.0)["places"])
        self.assertEqual(sorted(p["fit"] for p in data["places"]), expected)
        self.assertTrue(all(p["priceSource"] in ("tag", "type") for p in data["places"]))
        self.call("POST", "/api/payments", {"amount": "48", "category": "main"})
        after = self.call("GET", "/api/places?kind=food&radius=3")
        self.assertEqual(after["budget"]["remaining"], 9200)
        self.assertEqual(after["budget"]["perMeal"], 4600)
        self.assertNotEqual([p["fit"] for p in after["places"]], [p["fit"] for p in data["places"]])

    def test_shops_have_no_fit(self):
        self.demo()
        data = self.call("GET", "/api/places?kind=shop&radius=3")
        self.assertNotIn("budget", data)
        self.assertTrue(all("fit" not in p for p in data["places"]))


class Campus(ApiTest):
    def test_choice_moves_the_map_and_survives_a_restart(self):
        self.assertEqual(self.state()["campus"], "hkust")
        state = self.call("POST", "/api/campus", {"campus": "hkbu"})
        self.assertEqual(state["campus"], "hkbu")
        self.demo()
        self.assertEqual(self.call("GET", "/api/places?kind=food&radius=1")["center"]["name"], "HKUST")
        self.call("POST", "/api/campus", {"campus": "cuhk"})
        self.assertEqual(self.call("GET", "/api/places?kind=food&radius=1")["center"]["name"], "CUHK")
        self.stop(self.server, self.thread)
        self.start()
        self.assertEqual(self.state()["campus"], "cuhk")
        self.call("POST", "/api/mode", {"mode": "live"})
        self.assertEqual(self.state()["campus"], "hkbu")
        self.fetcher.assert_not_called()

    def test_bad_campus_gets_400(self):
        for body in ({"campus": "polyu"}, {"campus": ""}, {"campus": 1}, {"campus": None}, {}):
            with self.subTest(body=body):
                self.call("POST", "/api/campus", body, status=400)
        self.assertEqual(self.state()["campus"], "hkust")


class WeekNavigation(ApiTest):
    PAST = "2027-02-22"

    def add_past_week(self):
        """A live week before this one, written straight to the live file."""
        with open_books(self.dir)["live"].session(write=True) as s:
            s.set_week(self.PAST, money.SAMPLE_OPENING)
            s.add_payment({"date": "2027-02-24", "amount": 3300, "category": "snack", "note": "past",
                           "from": {fund: (3300 if fund == "snack" else 0) for fund in money.FUNDS}})

    def test_weeks_lists_every_stored_week(self):
        self.set_funds()
        self.add_past_week()
        self.assertEqual(self.state()["weeks"], [self.PAST, LIVE_MONDAY])

    def test_past_week_is_readable(self):
        self.set_funds()
        self.add_past_week()
        self.call("POST", "/api/payments", {"amount": "48", "category": "main"})
        past = self.state("?week=" + self.PAST)
        self.assertEqual((past["weekStart"], past["today"], past["mode"]), (self.PAST, LIVE_TODAY, "live"))
        self.assertEqual(past["opening"], money.SAMPLE_OPENING)
        self.assertEqual([p["note"] for p in past["payments"]], ["past"])
        self.assertIsNone(past["prefill"])

    def test_writes_always_go_to_the_current_week(self):
        self.set_funds()
        self.add_past_week()
        result = self.call("POST", "/api/payments",
                           {"amount": "10", "category": "main", "week": self.PAST, "date": "2027-02-24"})
        self.assertEqual(result["state"]["weekStart"], LIVE_MONDAY)
        self.assertEqual([p["date"] for p in result["state"]["payments"]], [LIVE_TODAY])
        self.assertEqual(len(self.state("?week=" + self.PAST)["payments"]), 1)

    def test_no_future_week(self):
        self.set_funds()
        for week in ("2027-03-08", "2027-03-15", "2030-01-07"):
            with self.subTest(week=week):
                self.call("GET", "/api/state?week=" + week, status=400)

    def test_demo_weeks_follow_the_demo_date(self):
        self.demo()
        self.assertEqual(self.state()["weeks"], [money.SAMPLE_WEEK_START])
        self.assertEqual(self.state("?week=" + money.SAMPLE_WEEK_START)["today"], money.SAMPLE_TODAY)
        self.assertTrue(self.state("?week=2026-11-02")["needsFunds"])
        # Later than the demo date, even though the live date is in 2027.
        for week in ("2026-11-16", LIVE_MONDAY):
            with self.subTest(week=week):
                self.call("GET", "/api/state?week=" + week, status=400)


class ModeSwitch(ApiTest):
    def test_every_demo_week_button(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                state = self.call("POST", "/api/mode", {"mode": "demo", "scenario": scenario})
                self.assertEqual((state["mode"], state["scenario"], state["today"]),
                                 ("demo", scenario, money.SAMPLE_TODAY))
                self.assertEqual(self.state()["scenario"], scenario)

    def test_v1_mode_names_are_refused(self):
        for mode in SCENARIOS:
            with self.subTest(mode=mode):
                self.call("POST", "/api/mode", {"mode": mode}, status=400)

    def test_switching_modes_never_mixes_data(self):
        self.set_funds()
        self.call("POST", "/api/payments", {"amount": "12", "category": "snack", "note": "live"})
        demo = self.demo()
        self.assertNotIn("live", [p["note"] for p in demo["payments"]])
        self.assertEqual(demo["weeks"], [money.SAMPLE_WEEK_START])
        self.call("POST", "/api/payments", {"amount": "5", "category": "snack", "note": "demo"})
        live = self.call("POST", "/api/mode", {"mode": "live"})
        self.assertEqual(live["today"], LIVE_TODAY)
        self.assertEqual([p["note"] for p in live["payments"]], ["live"])
        self.assertEqual(live["weeks"], [LIVE_MONDAY])
        self.assertEqual(live["opening"], money.SAMPLE_OPENING)
        # The demo week does not exist in the live file.
        past = self.state("?week=" + money.SAMPLE_WEEK_START)
        self.assertEqual((past["payments"], past["needsFunds"]), ([], True))

    def test_live_after_demo_starts_with_its_own_funds_prompt(self):
        self.demo()
        live = self.call("POST", "/api/mode", {"mode": "live"})
        self.assertTrue(live["needsFunds"])
        self.assertIsNone(live["prefill"])
        self.assertIsNone(live["scenario"])


class Restart(ApiTest):
    def test_data_survives_a_restart_on_the_same_folder(self):
        self.set_funds()
        saved = self.call("POST", "/api/payments", {"amount": "48", "category": "main"})["state"]
        self.stop(self.server, self.thread)
        self.start()
        self.assertEqual(self.state()["payments"], saved["payments"])
        self.assertEqual(self.state()["opening"], money.SAMPLE_OPENING)

    def test_demo_mode_survives_a_restart(self):
        self.demo("over")
        self.stop(self.server, self.thread)
        self.start()
        state = self.state()
        self.assertEqual((state["mode"], state["scenario"]), ("demo", "over"))


if __name__ == "__main__":
    unittest.main()


class FundEditBelowSpent(ApiTest):
    def test_settings_below_spent_answers_400_with_field_and_minimum(self):
        self.set_funds()
        self.call("POST", "/api/payments", {"amount": "100", "category": "main"})
        error = self.call("POST", "/api/settings", {**FUNDS_TEXT, "main": "50"}, status=400)
        self.assertEqual(error["field"], "main")
        self.assertEqual(error["minimum"], 10000)
        self.assertIn("HK$100", error["error"])
        self.assertEqual(self.state()["opening"], money.SAMPLE_OPENING)
        state = self.call("POST", "/api/settings", {**FUNDS_TEXT, "main": "100"})
        self.assertEqual(state["view"]["fundsNow"]["main"], 0)


class ZeroFundsAndPositivePayments(ApiTest):
    def test_settings_accept_zero(self):
        state = self.call("POST", "/api/settings", {**FUNDS_TEXT, "snack": "0", "experience": "0.00"})
        self.assertEqual((state["opening"]["snack"], state["opening"]["experience"]), (0, 0))

    def test_payment_amounts_must_be_positive(self):
        self.set_funds()
        for amount in ("0", "0.00", "-5", "12,50", "1.234", "99999999999", "abc"):
            with self.subTest(amount=amount):
                self.call("POST", "/api/payments", {"amount": amount, "category": "main"}, status=400)
        self.assertEqual(self.state()["payments"], [])


class IdempotentPayments(ApiTest):
    def test_same_request_id_twice_creates_one_payment(self):
        self.set_funds()
        body = {"amount": "48", "category": "main", "note": "lunch", "requestId": "c0ffee00-1234-4abc-8def-001122334455"}
        first = self.call("POST", "/api/payments", body)
        again = self.call("POST", "/api/payments", body)
        self.assertTrue(again["replayed"])
        self.assertEqual(again["payment"]["id"], first["payment"]["id"])
        self.assertEqual(len(self.state()["payments"]), 1)

    def test_bad_request_id_is_400(self):
        self.set_funds()
        for bad in (["x"], 12345678, "bad id!"):
            with self.subTest(bad=bad):
                self.call("POST", "/api/payments", {"amount": "48", "category": "main", "requestId": bad}, status=400)
        self.assertEqual(self.state()["payments"], [])


class CentsEndToEnd(ApiTest):
    """P0.5: "12.34" is stored as the integer 1234, and Today's figures equal what SQLite holds."""

    def db(self):
        import sqlite3
        return sqlite3.connect(self.dir / "ssust.db")

    def test_12_34_is_stored_as_integer_1234(self):
        self.set_funds()
        result = self.call("POST", "/api/payments", {"amount": "12.34", "category": "snack"})
        self.assertEqual(result["payment"]["amount"], 1234)
        con = self.db()
        try:
            row = con.execute("SELECT amount, typeof(amount), from_snack, typeof(from_snack) FROM payments").fetchone()
        finally:
            con.close()
        self.assertEqual(row, (1234, "integer", 1234, "integer"))
        self.assertEqual(money.hk(row[0]), "HK$12.34")

    def test_today_figures_equal_sqlite_totals(self):
        self.set_funds()
        for amount, category in (("48.50", "main"), ("12.34", "snack"), ("30", "experience"), ("99.99", "fixed")):
            self.call("POST", "/api/payments", {"amount": amount, "category": category})
        view = self.state()["view"]
        con = self.db()
        try:
            opening = dict(zip(money.FUNDS, con.execute(
                f"SELECT {', '.join(money.FUNDS)} FROM weeks WHERE week_start = ?", (LIVE_MONDAY,)).fetchone()))
            used = dict(zip(money.FUNDS, con.execute(
                "SELECT " + ", ".join(f"COALESCE(SUM(from_{f}), 0)" for f in money.FUNDS) + " FROM payments").fetchone()))
            food_today = con.execute(
                "SELECT COALESCE(SUM(from_main + from_snack), 0) FROM payments WHERE date = ?", (LIVE_TODAY,)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(view["fundsNow"], {f: opening[f] - used[f] for f in money.FUNDS})
        self.assertEqual(view["spentToday"], food_today)
        self.assertEqual(view["spentToday"], 4850 + 1234)
        self.assertEqual(view["allowance"], money.round_div(opening["main"] + opening["snack"], 5))
        self.assertEqual(view["todayRemaining"], view["allowance"] - food_today)


class UndoRoute(ApiTest):
    def test_undo_then_undo_again(self):
        self.set_funds()
        before = self.state()["view"]
        paid = self.call("POST", "/api/payments", {"amount": "48", "category": "main"})
        result = self.call("POST", "/api/payments/undo", {"id": paid["payment"]["id"]})
        self.assertEqual(result["state"]["view"], before)
        self.assertEqual(result["state"]["payments"], [])
        error = self.call("POST", "/api/payments/undo", {"id": paid["payment"]["id"]}, status=400)
        self.assertIn("already undone", error["error"])

    def test_bad_ids_are_400(self):
        self.set_funds()
        for body in ({}, {"id": "1"}, {"id": 1.5}, {"id": True}, {"id": None}, {"id": [1]}, {"id": 404}):
            with self.subTest(body=body):
                self.call("POST", "/api/payments/undo", body, status=400)


class ReceiptRoute(ApiTest):
    def test_parse_returns_cents_line_and_merchant(self):
        data = self.call("POST", "/api/receipt/parse", {"text": "Sample Noodle Bar\nTOTAL HK$48.50"})
        entry = data.pop("entry")
        self.assertEqual(data, {"found": True, "amount": 4850, "line": "TOTAL HK$48.50",
                                "merchant": "Sample Noodle Bar", "guess": False})
        self.assertEqual((entry["amount"], entry["category"], entry["note"]), (4850, "main", "Sample Noodle Bar"))

    def test_text_only_sample_reader_is_gone(self):
        self.call("POST", "/api/assistant/receipt", {"sample": "mcd"}, status=404)

    def test_nothing_found(self):
        data = self.call("POST", "/api/receipt/parse", {"text": "Sample Shop\nThank you"})
        self.assertFalse(data["found"])
        self.assertEqual(data["reason"], "no_amounts")  # the app asks for a better photo
        # Prices but no TOTAL line: a best guess (here the largest price).
        data = self.call("POST", "/api/receipt/parse", {"text": "Sample Shop\nItem 12.00\nItem 8.00"})
        self.assertEqual((data["found"], data["guess"], data["amount"]), (True, True, 1200))

    def test_parse_never_saves_a_payment(self):
        self.set_funds()
        self.call("POST", "/api/receipt/parse", {"text": "Shop\nTotal 30.00"})
        self.assertEqual(self.state()["payments"], [])

    def test_bad_input_gets_400(self):
        for body in ({}, {"text": 12}, {"text": None}):
            with self.subTest(body=body):
                self.call("POST", "/api/receipt/parse", body, status=400)

    def test_ocr_files_are_served(self):
        for path, kind in (("/vendor/tesseract/tesseract.min.js", "text/javascript"),
                           ("/vendor/tesseract/worker.min.js", "text/javascript"),
                           ("/vendor/tesseract/core/tesseract-core-simd-lstm.wasm.js", "text/javascript"),
                           ("/vendor/tesseract/lang/eng.traineddata.gz", "application/octet-stream"),
                           ("/vendor/tesseract/lang/chi_tra.traineddata.gz", "application/octet-stream")):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertTrue(headers["Content-Type"].startswith(kind))
                self.assertNotIn("Content-Encoding", headers)


class InboxRoutes(ApiTest):
    TAP = {"source": "apple_pay", "amount": "38", "merchant": "Sample Coffee Kiosk", "card": "Sample card 0000",
           "externalId": "tap-0001-abcd"}

    def test_add_confirm_and_dismiss(self):
        self.set_funds()
        data = self.call("POST", "/api/inbox", self.TAP)
        self.assertTrue(data["created"])
        [item] = data["state"]["inbox"]
        self.assertEqual(item["amount"], 3800)
        again = self.call("POST", "/api/inbox", self.TAP)
        self.assertFalse(again["created"])
        done = self.call("POST", "/api/inbox/confirm", {"id": item["id"], "category": "main"})
        self.assertEqual(done["payment"]["amount"], 3800)
        self.assertEqual(done["state"]["inbox"], [])
        second = self.call("POST", "/api/inbox", {**self.TAP, "externalId": "tap-0002-abcd"})["state"]["inbox"][0]
        self.assertEqual(self.call("POST", "/api/inbox/dismiss", {"id": second["id"]})["inbox"], [])

    def test_bad_input_gets_400(self):
        self.set_funds()
        for body in ({**self.TAP, "amount": "0"}, {**self.TAP, "source": "bank"}, {**self.TAP, "merchant": 5}):
            with self.subTest(body=body):
                self.call("POST", "/api/inbox", body, status=400)
        self.call("POST", "/api/inbox/confirm", {"id": "1", "category": "main"}, status=400)
        self.call("POST", "/api/inbox/dismiss", {"id": 99}, status=400)

    def test_connected_switches(self):
        state = self.call("POST", "/api/connected", {"source": "hsbc", "on": True})
        self.assertTrue(state["connected"]["hsbc"])
        self.call("POST", "/api/connected", {"source": "hsbc", "on": "yes"}, status=400)
