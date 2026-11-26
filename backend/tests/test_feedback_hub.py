"""Feedback goes to the central server; everything else stays on this computer.

A local SSUST (run.py) keeps the budget, payments and every other data in its own data folder.
Only feedback leaves: the local server sends it to the central feedback server (serve.py on Render
by default), and keeps it in a local outbox until that server has it. The central server stores
it in its private feedback box, readable by the team only. urlopen is patched: no test uses the
network.
"""

import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ssust import feedback
from ssust.dates import FixedClock
from ssust.server import make_server
from tests.test_api import FUNDS_TEXT, ApiTest

ROOT = Path(__file__).resolve().parent.parent.parent
HUB = "https://hub.example.org/api/feedback"


def load(name):
    spec = importlib.util.spec_from_file_location(f"ssust_{name}_hub", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeHub:
    """Stands in for urlopen: records each request; answers 200, or fails as told."""

    def __init__(self):
        self.requests = []
        self.fail = None  # None, "down" (URLError) or an HTTP status

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.fail == "down":
            raise urllib.error.URLError("offline")
        if self.fail:
            raise urllib.error.HTTPError(request.full_url, self.fail, "refused", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps({"ok": True, "id": len(self.requests), "thanks": "x"}).encode())

    def bodies(self):
        return [json.loads(r.data.decode("utf-8")) for r in self.requests]


class RelayServer(ApiTest):
    """A local server whose feedback goes to the central server."""

    def start(self):
        self.hub = FakeHub()
        patcher = mock.patch("urllib.request.urlopen", self.hub)
        patcher.start()
        self.addCleanup(patcher.stop)
        server = make_server(self.dir, FixedClock("2027-03-03"), port=0, places_fetcher=self.fetcher, quiet=True,
                             feedback_url=HUB)
        server.feedback_relay.flush()  # the start-up flush, run here so the tests are deterministic
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.server, self.thread = server, thread
        self.port = server.server_address[1]
        self.addCleanup(self.stop, server, thread)

    def send(self, message, **extra):
        return self.call("POST", "/api/feedback", {"rating": 4, "message": message, "screen": "today", **extra})

    def outbox(self):
        return self.server.feedback_relay.pending()

    def test_feedback_goes_to_the_hub_and_nothing_stays_here(self):
        answer = self.send("Nice sliders", deviceId="a" * 32)
        self.assertEqual(set(answer), {"ok", "id", "thanks"})
        self.assertEqual(len(self.hub.requests), 1)
        request = self.hub.requests[0]
        self.assertEqual(request.full_url, HUB)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        body = self.hub.bodies()[0]
        self.assertEqual(body, {"rating": 4, "message": "Nice sliders", "screen": "today", "deviceId": "a" * 32,
                                "appVersion": feedback.APP_VERSION})
        self.assertEqual(self.outbox(), 0)
        self.assertEqual(self.server.feedback.count(), 0)  # not kept in this computer's box

    def test_offline_feedback_waits_then_goes(self):
        self.hub.fail = "down"
        answer = self.send("first")
        self.assertIn("online", answer["thanks"])
        self.assertEqual(self.outbox(), 1)
        self.hub.fail = None
        self.send("second")
        self.assertEqual([b["message"] for b in self.hub.bodies()[1:]], ["first", "second"])  # oldest first
        self.assertEqual(self.outbox(), 0)

    def test_a_refused_entry_is_dropped_not_retried_forever(self):
        self.hub.fail = 400
        self.send("odd")
        self.assertEqual(self.outbox(), 0)
        self.hub.fail = 503
        self.send("later")
        self.assertEqual(self.outbox(), 1)  # a server error is kept for later

    def test_budget_and_payments_never_leave_this_computer(self):
        self.call("POST", "/api/settings", FUNDS_TEXT)
        self.call("POST", "/api/payments", {"amount": "48", "category": "main", "note": "lunch"})
        self.call("GET", "/api/state")
        self.assertEqual(self.hub.requests, [])

    def test_bad_feedback_is_refused_here(self):
        self.call("POST", "/api/feedback", {"rating": 9, "screen": "today"}, status=400)
        self.assertEqual(self.hub.requests, [])

    def test_the_outbox_survives_a_restart(self):
        self.hub.fail = "down"
        self.send("kept")
        con = sqlite3.connect(self.dir / feedback.FEEDBACK_FILE)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 1)
        con.close()


class HubServer(ApiTest):
    """The central server (no feedback_url): it keeps what local servers send it."""

    def test_accepts_relayed_entries_with_their_app_version(self):
        self.call("POST", "/api/feedback", {"rating": 5, "message": "from a laptop", "screen": "map",
                                            "appVersion": "2.0.9"})
        rows = self.server.feedback.all()
        self.assertEqual((rows[0]["message"], rows[0]["appVersion"]), ("from a laptop", "2.0.9"))
        self.call("POST", "/api/feedback", {"rating": 5, "screen": "map", "appVersion": "<script>"}, status=400)


class Launchers(unittest.TestCase):
    def test_run_py_sends_to_the_hosted_server_by_default(self):
        run = load("run")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSUST_FEEDBACK_URL", None)
            self.assertEqual(run.parse_args([]).feedback_url, feedback.DEFAULT_HUB)
            self.assertIsNone(run.parse_args(["--feedback-url", "local"]).feedback_url)
            self.assertEqual(run.parse_args(["--feedback-url", HUB]).feedback_url, HUB)
        with mock.patch.dict(os.environ, {"SSUST_FEEDBACK_URL": "local"}):
            self.assertIsNone(run.parse_args([]).feedback_url)

    def test_run_py_refuses_a_non_https_hub(self):
        run = load("run")
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            run.parse_args(["--feedback-url", "http://hub.example.org/api/feedback"])

    def test_serve_py_is_the_hub_unless_told(self):
        serve = load("serve")
        self.assertIsNone(serve.config({})["feedbackUrl"])
        self.assertEqual(serve.config({"SSUST_FEEDBACK_URL": HUB})["feedbackUrl"], HUB)

    def test_default_hub_is_the_hosted_api(self):
        self.assertEqual(feedback.DEFAULT_HUB, "https://ssust-api.onrender.com/api/feedback")


class FeedbackTab(unittest.TestCase):
    """The Feedback tab sends only; it never lists anyone's feedback."""

    def test_no_list(self):
        js = ROOT / "frontend" / "js"
        screen = (js / "screens" / "feedback.js").read_text(encoding="utf-8")
        actions = (js / "actions.js").read_text(encoding="utf-8")
        self.assertNotIn("Recent feedback", screen)
        self.assertIn("Only the SSUST team can read it", screen)
        self.assertNotIn('api("/api/feedback")', actions)
        self.assertNotIn("loadFeedback", (js / "main.js").read_text(encoding="utf-8"))
