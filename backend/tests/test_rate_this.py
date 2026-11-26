"""The small "Rate this" control: three levels, one tap sends, an optional comment after.

It goes through the private feedback pipeline (POST /api/feedback) with a context id, so only
the team can read it (GET /api/admin/feedback).
"""

import json
import unittest

from ssust.server import FRONTEND
from tests.test_api import ApiTest

JS = FRONTEND / "js"
TOKEN = "rate-this-token-0123456789"


class RateThisUi(unittest.TestCase):
    def setUp(self):
        self.fb = (JS / "feedback.js").read_text(encoding="utf-8")

    def test_component(self):
        self.assertIn("export function rateHtml", self.fb)
        for level in ('data-rate="5"', 'data-rate="3"', 'data-rate="1"'):
            self.assertIn(level, self.fb)
        self.assertIn("data-rate-comment", self.fb)  # the optional comment box, shown after a tap
        self.assertIn("MutationObserver", self.fb)  # slots fill themselves after any render
        self.assertNotIn("location.reload", self.fb)

    def test_used_on_receipts_insights_and_groceries(self):
        for path, screen in ((JS / "widget.js", "receipt"), (JS / "screens" / "insights.js", "insight"),
                             (JS / "screens" / "groceries.js", "groceries")):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(f'data-rate-slot="{screen}"', text)
                self.assertIn("data-context=", text)
                self.assertIn("data-question=", text)


class RateThisApi(ApiTest):
    def start(self):
        from ssust.dates import FixedClock
        from ssust.server import make_server
        import threading
        server = make_server(self.dir, FixedClock("2027-03-03"), port=0, places_fetcher=self.fetcher, quiet=True,
                             admin_token=TOKEN)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.server, self.thread = server, thread
        self.port = server.server_address[1]
        self.addCleanup(self.stop, server, thread)

    def test_ratings_with_context_reach_only_the_team(self):
        for body in ({"rating": 5, "screen": "receipt", "contextId": "receipt:sample:5060"},
                     {"rating": 1, "screen": "groceries", "contextId": "recipe:tomato_egg_rice"},
                     {"rating": 3, "screen": "insight", "contextId": "insight:2027-03-01",
                      "message": "the pace warning was wrong"}):
            answer = self.call("POST", "/api/feedback", body)
            self.assertEqual(set(answer), {"ok", "id", "thanks"})
        status, _headers, raw = self.request("GET", "/api/admin/feedback")
        self.assertEqual(status, 401)
        conn_status, _h, raw = self._admin()
        self.assertEqual(conn_status, 200)
        rows = json.loads(raw)["feedback"]
        self.assertEqual([r["contextId"] for r in rows],
                         ["insight:2027-03-01", "recipe:tomato_egg_rice", "receipt:sample:5060"])

    def _admin(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/api/admin/feedback", headers={"Authorization": f"Bearer {TOKEN}"})
            res = conn.getresponse()
            return res.status, res.headers, res.read()
        finally:
            conn.close()
