"""Real Apple Pay payments through an iOS Shortcuts automation, and a one-line summary for a
Shortcuts widget. The phone's id comes in the X-SSUST-Device header, like the app."""

import http.client
import json
import unittest
from pathlib import Path

from ssust.service import wallet_amount

from tests.test_api import FUNDS_TEXT, ApiTest

ROOT = Path(__file__).resolve().parent.parent.parent
DEVICE = "c" * 32


class WalletAmount(unittest.TestCase):
    def test_formats_a_shortcut_can_send(self):
        for raw, cents in (("HK$38.00", 3800), ("$38.50", 3850), ("38", 3800), ("HK$ 1,234.50", 123450),
                           ("38.00 HKD", 3800), (" 38.00", 3800), (38, 3800), (38.5, 3850), (12.34, 1234)):
            with self.subTest(raw=raw):
                self.assertEqual(wallet_amount(raw), cents)

    def test_refused(self):
        for raw in ("", "abc", "0", "-5", "38,50", None, True, [], 0, -1, 1e12, 12.345):
            with self.subTest(raw=raw):
                self.assertIsNone(wallet_amount(raw))


class WalletRoute(ApiTest):
    def post(self, body, device=DEVICE, path="/api/shortcut/wallet"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            data = json.dumps(body).encode("utf-8")
            conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            if device:
                conn.putheader("X-SSUST-Device", device)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data)
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def get(self, path, device=DEVICE):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            if device:
                conn.putheader("X-SSUST-Device", device)
            conn.endheaders()
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def device_state(self):
        status, _, payload = self.get("/api/state")
        self.assertEqual(status, 200)
        return json.loads(payload)

    def test_a_tap_lands_in_to_review_for_that_phone_only(self):
        status, _, payload = self.post({"amount": "HK$38.00", "merchant": "Pacific Coffee", "card": "Visa 1234"})
        self.assertEqual(status, 200, payload)
        self.assertEqual(json.loads(payload)["amount"], 3800)
        items = self.device_state()["inbox"]
        self.assertEqual([(i["source"], i["amount"], i["merchant"], i["card"]) for i in items],
                         [("wallet", 3800, "Pacific Coffee", "Visa 1234")])
        self.assertEqual(items[0]["suggestedFund"], "snack")  # chain + keywords guess, as before
        self.assertEqual(self.state()["inbox"], [])  # the shared web book is untouched

    def test_each_run_is_a_new_payment_and_nothing_is_spent_until_confirmed(self):
        self.post({"amount": "20", "merchant": "7-Eleven"})
        self.post({"amount": "20", "merchant": "7-Eleven"})
        state = self.device_state()
        self.assertEqual(len(state["inbox"]), 2)
        self.assertEqual(state["payments"], [])
        self.assertEqual(state["inbox"][0]["card"], "Apple Pay")  # no card name sent

    def test_bad_taps_are_refused(self):
        for body in ({"merchant": "x"}, {"amount": "abc"}, {"amount": "0"}, {"amount": "38", "merchant": 5}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)
        self.assertEqual(self.post({"amount": "38"}, device="bad")[0], 400)

    def test_the_wallet_source_is_not_a_simulated_switch(self):
        self.assertEqual(set(self.state()["connected"]), {"apple_pay", "octopus", "hsbc"})

    def test_today_summary_is_plain_text(self):
        status, headers, payload = self.get("/api/shortcut/today")
        self.assertEqual(status, 200)
        self.assertIn("text/plain", headers["Content-Type"])
        self.assertEqual(payload.decode("utf-8"), "SSUST: set your weekly budget in the app.")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            body = json.dumps(FUNDS_TEXT).encode("utf-8")
            conn.putrequest("POST", "/api/settings", skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            conn.putheader("X-SSUST-Device", DEVICE)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            self.assertEqual(conn.getresponse().status, 200)
        finally:
            conn.close()
        self.post({"amount": "12", "merchant": "Bakery"})
        text = self.get("/api/shortcut/today")[2].decode("utf-8")
        self.assertTrue(text.startswith("SSUST: HK$170 left today"), text)
        self.assertIn("1 to review", text)


class AppScreens(unittest.TestCase):
    def read(self, *parts):
        return ROOT.joinpath(*parts).read_text(encoding="utf-8")

    def test_camera_and_photo_permissions_are_declared(self):
        info = self.read("ios", "App", "App", "Info.plist")
        self.assertIn("<key>NSCameraUsageDescription</key>", info)
        self.assertIn("<key>NSPhotoLibraryUsageDescription</key>", info)

    def test_scan_a_receipt_from_today(self):
        self.assertIn("data-scan-today", self.read("frontend", "js", "screens", "today.js"))
        self.assertIn("[data-scan-today]", self.read("frontend", "js", "render.js"))

    def test_shortcuts_guide_in_the_app(self):
        guide = self.read("frontend", "js", "screens", "shortcuts.js")
        for word in ("/api/shortcut/wallet", "/api/shortcut/today", "X-SSUST-Device", "deviceId()", "data-copy"):
            self.assertIn(word, guide)
        self.assertIn("shortcutsCard(", self.read("frontend", "js", "screens", "settings.js"))

    def test_wallet_payments_are_not_called_simulated(self):
        inbox = self.read("frontend", "js", "inbox.js")
        self.assertIn('wallet: { name: "Apple Pay"', inbox)
        self.assertIn('item.source === "wallet"', inbox)

    def test_the_app_refreshes_when_it_comes_back(self):
        self.assertIn('"visibilitychange"', self.read("frontend", "js", "main.js"))


if __name__ == "__main__":
    unittest.main()
