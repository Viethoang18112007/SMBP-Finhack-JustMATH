"""Private feedback: anyone can send it, nobody but the team can read it.

Students only ever get a "Thanks" back. The team reads everything through
GET /api/admin/feedback (or the /admin/feedback page) with the token from SSUST_ADMIN_TOKEN, or
exports a CSV with `python run.py --export-feedback FILE`. Without the variable, the admin routes
do not exist (404).
"""

import contextlib
import csv
import http.client
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from ssust import feedback
from ssust.dates import FixedClock
from ssust.server import make_server

ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN = "team-secret-token-1234567890abcdef"
DEVICE_A = "a" * 32
DEVICE_B = "b" * 32


class Box(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "feedback.db"
        self.box = feedback.FeedbackBox(self.path)

    def test_add_and_read_back(self):
        first = self.box.add(rating=4, message="Nice sliders", screen="settings")
        second = self.box.add(rating=None, message="Map is slow\non my phone", screen="map", device_id=DEVICE_A,
                              context_id="place:node/123")
        self.assertIsInstance(first, int)
        rows = self.box.all()
        self.assertEqual([r["id"] for r in rows], [second, first])  # newest first
        row = rows[0]
        self.assertEqual(set(row), {"id", "createdAt", "rating", "message", "screen", "contextId", "appVersion",
                                    "deviceId"})
        self.assertEqual(row["message"], "Map is slow\non my phone")
        self.assertEqual(row["deviceId"], DEVICE_A)
        self.assertEqual(row["contextId"], "place:node/123")
        self.assertEqual(row["appVersion"], feedback.APP_VERSION)
        self.assertRegex(row["createdAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(self.box.count(), 2)

    def test_rating_only_or_message_only(self):
        self.box.add(rating=5, message="", screen="today")
        self.box.add(rating=None, message="ok", screen="today")
        with self.assertRaises(feedback.FeedbackError):
            self.box.add(rating=None, message="   ", screen="today")

    def test_bad_ratings(self):
        for bad in (0, 6, True, 2.5, "3", -1):
            with self.subTest(rating=bad), self.assertRaises(feedback.FeedbackError):
                self.box.add(rating=bad, message="", screen="today")

    def test_message_rules(self):
        with self.assertRaises(feedback.FeedbackError):
            self.box.add(rating=3, message="x" * (feedback.MAX_MESSAGE + 1), screen="today")
        with self.assertRaises(feedback.FeedbackError):
            self.box.add(rating=3, message=42, screen="today")
        self.box.add(rating=3, message="tab\there\x00\x07 bell\r\nnew line", screen="today")
        self.assertEqual(self.box.all()[0]["message"], "tab here bell\nnew line")

    def test_screen_context_and_device_are_checked(self):
        with self.assertRaises(feedback.FeedbackError):
            self.box.add(rating=3, message="", screen="admin")
        for bad in ("<script>", "a" * 65, "two words", 7):
            with self.subTest(context=bad), self.assertRaises(feedback.FeedbackError):
                self.box.add(rating=3, message="", screen="today", context_id=bad)
        for bad in ("A" * 32, "a" * 31, "z" * 32, 5):
            with self.subTest(device=bad), self.assertRaises(feedback.FeedbackError):
                self.box.add(rating=3, message="", screen="today", device_id=bad)

    def test_no_personal_data_columns(self):
        con = sqlite3.connect(self.path)
        cols = {row[1] for row in con.execute("PRAGMA table_info(feedback)")}
        con.close()
        self.assertEqual(cols, {"id", "created_at", "rating", "message", "screen", "context_id", "app_version",
                                "device_id"})

    def test_full_box_refuses_more(self):
        with mock.patch.object(feedback, "MAX_ROWS", 2):
            self.box.add(rating=1, message="", screen="today")
            self.box.add(rating=2, message="", screen="today")
            with self.assertRaises(feedback.FeedbackError):
                self.box.add(rating=3, message="", screen="today")

    def test_csv_export_guards_formulas(self):
        self.box.add(rating=2, message="=HYPERLINK(\"x\")", screen="week")
        self.box.add(rating=5, message="fine, thanks", screen="today")
        out = Path(self.path).with_suffix(".csv")
        count = feedback.export_csv(self.path, out)
        self.assertEqual(count, 2)
        with open(out, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([r["message"] for r in rows], ["fine, thanks", "'=HYPERLINK(\"x\")"])
        self.assertEqual(set(rows[0]), {"id", "created_at", "rating", "message", "screen", "context_id",
                                        "app_version", "device_id"})

    def test_parse_request(self):
        entry = feedback.parse_request({"rating": 4, "message": "hi", "screen": "map", "contextId": "recipe:congee",
                                        "deviceId": DEVICE_A})
        self.assertEqual(entry, {"rating": 4, "message": "hi", "screen": "map", "context_id": "recipe:congee",
                                 "device_id": DEVICE_A})
        with self.assertRaises(feedback.FeedbackError):
            feedback.parse_request({"rating": 4, "screen": "map", "extra": 1})
        # The first iPhone builds send {"rating", "text"} with no screen.
        self.assertEqual(feedback.parse_request({"rating": 5, "text": "Nice"})["message"], "Nice")
        self.assertEqual(feedback.parse_request({"rating": 5, "text": "Nice"})["screen"], "feedback")
        with self.assertRaises(feedback.FeedbackError):
            feedback.parse_request({"rating": 5, "text": "a", "message": "b"})

    def test_token_check(self):
        self.assertTrue(feedback.token_ok(TOKEN, f"Bearer {TOKEN}"))
        for header in (None, "", TOKEN, f"Bearer {TOKEN}x", "Bearer ", f"Basic {TOKEN}"):
            with self.subTest(header=header):
                self.assertFalse(feedback.token_ok(TOKEN, header))
        self.assertFalse(feedback.token_ok("", "Bearer "))
        self.assertFalse(feedback.token_ok(None, f"Bearer {TOKEN}"))
        self.assertIn("hmac.compare_digest", Path(feedback.__file__).read_text(encoding="utf-8"))


class FeedbackApi(unittest.TestCase):
    """A real server on port 0 with a temporary data folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "data"

    def serve(self, admin_token=None, quiet=True):
        server = make_server(self.dir, FixedClock("2027-03-03"), port=0, places_fetcher=_no_fetch, quiet=quiet,
                             admin_token=admin_token)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]
        return server

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            data = None if body is None else json.dumps(body).encode("utf-8")
            hdrs = {"Content-Type": "application/json"} if body is not None else {}
            hdrs.update(headers or {})
            conn.request(method, path, body=data, headers=hdrs)
            res = conn.getresponse()
            raw = res.read()
            return res.status, res.getheader("Content-Type", ""), raw
        finally:
            conn.close()

    def send(self, message, device=None, rating=4):
        body = {"rating": rating, "message": message, "screen": "today"}
        if device:
            body["deviceId"] = device
        return self.call("POST", "/api/feedback", body)

    def test_sending_answers_only_thanks(self):
        self.serve()
        status, _, raw = self.send("first from A", DEVICE_A)
        self.assertEqual(status, 200)
        answer = json.loads(raw)
        self.assertEqual(set(answer), {"ok", "id", "thanks"})
        self.assertTrue(answer["ok"])
        status, _, raw = self.send("second from B", DEVICE_B)
        self.assertNotIn(b"first from A", raw)

    def test_bad_feedback_is_refused(self):
        self.serve()
        for body in ({"rating": 9, "screen": "today"}, {"message": "", "screen": "today"},
                     {"rating": 3, "screen": "nowhere"}, {"rating": 3, "screen": "today", "deviceId": "../.."},
                     {"rating": 3, "screen": "today", "message": "x" * 600}):
            with self.subTest(body=body):
                status, _, raw = self.call("POST", "/api/feedback", body)
                self.assertEqual(status, 400, raw)

    def test_no_user_route_returns_anyones_feedback(self):
        self.serve()
        self.send("secret note from A", DEVICE_A)
        for path in ("/api/feedback", "/api/feedback?device=" + DEVICE_A, "/api/feedback/mine", "/api/state",
                     "/api/insights", "/api/admin/feedback", "/admin/feedback"):
            with self.subTest(path=path):
                status, _, raw = self.call("GET", path)
                self.assertNotIn(b"secret note", raw)
                if "feedback" in path:
                    self.assertEqual(status, 404)

    def test_admin_disabled_without_the_variable(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SSUST_ADMIN_TOKEN", None)
            self.serve()
        self.send("hello")
        for path in ("/api/admin/feedback", "/admin/feedback", "/admin/feedback.js"):
            with self.subTest(path=path):
                status, _, _ = self.call("GET", path, headers={"Authorization": f"Bearer {TOKEN}"})
                self.assertEqual(status, 404)

    def test_admin_token_from_the_environment(self):
        with mock.patch.dict(os.environ, {"SSUST_ADMIN_TOKEN": TOKEN}):
            self.serve()
        self.send("from env")
        status, _, raw = self.call("GET", "/api/admin/feedback", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(status, 200)
        self.assertIn(b"from env", raw)

    def test_wrong_or_missing_token(self):
        self.serve(admin_token=TOKEN)
        self.send("private")
        for headers in ({}, {"Authorization": "Bearer nope"}, {"Authorization": TOKEN},
                        {"X-Admin-Token": TOKEN}):
            with self.subTest(headers=headers):
                status, _, raw = self.call("GET", "/api/admin/feedback", headers=headers)
                self.assertEqual(status, 401)
                self.assertNotIn(b"private", raw)
        status, _, raw = self.call("GET", f"/api/admin/feedback?token={TOKEN}")
        self.assertEqual(status, 401)

    def test_admin_reads_everyone(self):
        self.serve(admin_token=TOKEN)
        self.send("from A", DEVICE_A, rating=5)
        self.send("from B", DEVICE_B, rating=1)
        status, ctype, raw = self.call("GET", "/api/admin/feedback", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("application/json"))
        data = json.loads(raw)
        self.assertEqual(data["count"], 2)
        self.assertEqual([e["message"] for e in data["feedback"]], ["from B", "from A"])
        self.assertEqual(data["feedback"][0]["deviceId"], DEVICE_B)

    def test_admin_page_when_enabled(self):
        self.serve(admin_token=TOKEN)
        status, ctype, raw = self.call("GET", "/admin/feedback")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn(b'src="/admin/feedback.js"', raw)
        self.assertNotIn(TOKEN.encode(), raw)
        status, ctype, raw = self.call("GET", "/admin/feedback.js")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/javascript"))
        self.assertIn(b"Authorization", raw)

    def test_token_is_never_logged(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.serve(admin_token=TOKEN, quiet=False)
            self.call("GET", "/api/admin/feedback", headers={"Authorization": f"Bearer {TOKEN}"})
            self.call("GET", "/api/admin/feedback", headers={"Authorization": "Bearer wrong-token"})
            self.call("GET", f"/api/admin/feedback?token={TOKEN}")
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())
        self.assertNotIn("wrong-token", out.getvalue() + err.getvalue())


def _no_fetch(kind, radius_km, campus):
    raise AssertionError("no places in these tests")


class ExportCommand(unittest.TestCase):
    def test_run_py_export_feedback(self):
        spec = importlib.util.spec_from_file_location("ssust_run_export", ROOT / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            box = feedback.FeedbackBox(data / feedback.FEEDBACK_FILE)
            box.add(rating=4, message="exported", screen="today")
            out = Path(tmp) / "out.csv"
            printed = io.StringIO()
            with contextlib.redirect_stdout(printed):
                code = run.main(["--data", str(data), "--export-feedback", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("1 feedback", printed.getvalue())
            self.assertIn("exported", out.read_text(encoding="utf-8"))

    def test_export_with_no_feedback_yet(self):
        spec = importlib.util.spec_from_file_location("ssust_run_export2", ROOT / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            with contextlib.redirect_stdout(io.StringIO()):
                code = run.main(["--data", str(Path(tmp) / "empty"), "--export-feedback", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.read_text(encoding="utf-8").startswith("id,"))


class FeedbackUi(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / "frontend" / "js" / "feedback.js").read_text(encoding="utf-8")
        self.settings = (ROOT / "frontend" / "js" / "screens" / "settings.js").read_text(encoding="utf-8")

    def test_feedback_tab_sends_and_only_thanks(self):
        # The Feedback tab is the place to send it (no second card in Settings).
        self.assertNotIn("feedbackCard", self.settings)
        self.assertIn('"/api/feedback"', self.js)
        tab = (ROOT / "frontend" / "js" / "screens" / "feedback.js").read_text(encoding="utf-8")
        self.assertIn("Thanks", tab)
        # The app never asks for a list of feedback.
        self.assertNotIn("/api/admin", self.js)
        self.assertNotIn('api("/api/feedback")', self.js)

    def test_anonymous_device_id_is_optional_and_safe(self):
        self.assertIn("ssust.deviceId", self.js)
        self.assertIn("crypto.getRandomValues", self.js)
        self.assertIn("try {", self.js)

    def test_readme_explains_how_the_team_reads_it(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Feedback (private)", text)
        section = text[text.index("## Feedback (private)"):]
        for needle in ("SSUST_ADMIN_TOKEN", "/api/admin/feedback", "/admin/feedback", "--export-feedback",
                       "Authorization: Bearer"):
            self.assertIn(needle, section)
