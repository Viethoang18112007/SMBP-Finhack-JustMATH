"""Feedback in a small online database (Supabase, Postgres over HTTPS), so every computer's
feedback lands in one place that is not wiped like Render's free disk.

The public key can only add rows (row level security, docs/FEEDBACK_DATABASE.md): the app writes,
nobody reads through the API, the team reads in the database dashboard. A delivery only counts
when the receiver really says so; anything unclear stays in the local outbox. urlopen is patched:
no test uses the network.
"""

import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from ssust import feedback

ROOT = Path(__file__).resolve().parent.parent.parent
SUPA = "https://abcdefgh.supabase.co"
KEY = "eyJhbGciOiJIUzI1NiJ9.anon-key-for-tests.sig"  # an older anon key (a JWT)
PUBLISHABLE = "sb_publishable_testkey"
ENTRY = {"rating": 4, "message": "Nice", "screen": "today", "context_id": None, "device_id": "a" * 32}


class Answer:
    """urlopen stand-in: one status (and body) for every request; records the requests."""

    def __init__(self, status=201, body=b""):
        self.status, self.body, self.requests = status, body, []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        if self.status == "down":
            raise urllib.error.URLError("offline")
        if self.status >= 400:
            raise urllib.error.HTTPError(request.full_url, self.status, "no", {}, io.BytesIO(self.body))
        response = io.BytesIO(self.body)
        response.status = self.status
        return response


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / feedback.FEEDBACK_FILE

    def relay(self, answer, url=SUPA, key=KEY):
        patcher = mock.patch("urllib.request.urlopen", answer)
        patcher.start()
        self.addCleanup(patcher.stop)
        return feedback.Relay(self.path, url, key=key)


class Supabase(Base):
    def test_rows_go_to_the_feedback_table_with_the_public_key(self):
        answer = Answer(201)
        relay = self.relay(answer)
        _, sent = relay.deliver(ENTRY)
        self.assertTrue(sent)
        request = answer.requests[0]
        self.assertEqual(request.full_url, f"{SUPA}/rest/v1/feedback")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Apikey"), KEY)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {KEY}")
        self.assertEqual(request.get_header("Prefer"), "return=minimal")
        self.assertEqual(json.loads(request.data), {"rating": 4, "message": "Nice", "screen": "today",
                                                    "device_id": "a" * 32, "app_version": feedback.APP_VERSION})
        self.assertEqual(relay.pending(), 0)

    def test_a_publishable_key_goes_in_apikey_only(self):
        answer = Answer(201)
        self.relay(answer, key=PUBLISHABLE).deliver(ENTRY)
        self.assertEqual(answer.requests[0].get_header("Apikey"), PUBLISHABLE)
        self.assertIsNone(answer.requests[0].get_header("Authorization"))

    def test_a_wrong_key_or_table_keeps_the_feedback(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                relay = self.relay(Answer(status))
                relay.deliver(ENTRY)
                self.assertGreaterEqual(relay.pending(), 1)  # a setup problem never loses feedback

    def test_a_row_the_database_refuses_is_dropped(self):
        relay = self.relay(Answer(400, b'{"code":"23514"}'))  # a CHECK constraint said no
        relay.deliver(ENTRY)
        self.assertEqual(relay.pending(), 0)

    def test_offline_keeps_it(self):
        relay = self.relay(Answer("down"))
        relay.deliver(ENTRY)
        self.assertEqual(relay.pending(), 1)


class SsustServer(Base):
    def test_only_a_real_thank_you_counts(self):
        # The old hosted server answers 200 with the list of feedback and ignores the message:
        # that is not a delivery, so the entry waits until the server is updated.
        relay = self.relay(Answer(200, json.dumps({"feedback": []}).encode()), url=feedback.DEFAULT_HUB, key=None)
        _, sent = relay.deliver(ENTRY)
        self.assertFalse(sent)
        self.assertEqual(relay.pending(), 1)

    def test_new_server_answer(self):
        relay = self.relay(Answer(200, json.dumps({"ok": True, "id": 3, "thanks": "x"}).encode()),
                           url=feedback.DEFAULT_HUB, key=None)
        self.assertTrue(relay.deliver(ENTRY)[1])


class Settings(unittest.TestCase):
    def test_kind_of_receiver(self):
        self.assertTrue(feedback.is_database(SUPA))
        self.assertFalse(feedback.is_database(feedback.DEFAULT_HUB))

    def test_hub_config_file_is_the_default_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "feedback_hub.json"
            config.write_text(json.dumps({"url": SUPA, "key": KEY}), encoding="utf-8")
            with mock.patch.object(feedback, "HUB_CONFIG", config), mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(feedback.URL_ENV, None)
                os.environ.pop(feedback.KEY_ENV, None)
                self.assertEqual(feedback.default_target(), (SUPA, KEY))
            with mock.patch.object(feedback, "HUB_CONFIG", Path(tmp) / "missing.json"):
                self.assertEqual(feedback.default_target()[0], feedback.DEFAULT_HUB)

    def test_environment_wins(self):
        with mock.patch.dict(os.environ, {feedback.URL_ENV: SUPA, feedback.KEY_ENV: "k2"}):
            self.assertEqual(feedback.default_target(), (SUPA, "k2"))

    def test_setup_guide_with_insert_only_policy(self):
        guide = (ROOT / "docs" / "FEEDBACK_DATABASE.md").read_text(encoding="utf-8")
        for needle in ("create table", "enable row level security", "for insert", "to anon",
                       "check (rating between 1 and 5)", "feedback_hub.json"):
            self.assertIn(needle, guide.lower())
        self.assertNotIn("for select", guide.lower())  # the public key can never read
