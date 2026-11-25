"""Real Apple Pay payments through an iOS Shortcuts automation, and a one-line summary for a
Shortcuts widget. The phone's id comes in the X-SSUST-Device header, like the app."""

import http.client
import json
import plistlib
import re
import unittest
from pathlib import Path

from ssust.service import wallet_amount

from tests.test_api import FUNDS_TEXT, ApiTest

ROOT = Path(__file__).resolve().parent.parent.parent
DEVICE = "c" * 32


class WalletAmount(unittest.TestCase):
    def test_formats_a_shortcut_can_send(self):
        for raw, cents in (("HK$38.00", 3800), ("$38.50", 3850), ("38", 3800), ("HK$ 1,234.50", 123450),
                           ("38.00 HKD", 3800), (" 38.00", 3800), (38, 3800), (38.5, 3850), (12.34, 1234),
                           # An iPhone set to French (or German) writes a decimal comma and spaces in thousands.
                           ("38,00 $HK", 3800), ("HK$38,50", 3850), ("38,5 $HK", 3850),
                           ("1 234,50 $HK", 123450), ("1.234,50 HK$", 123450), ("1,234", 123400),
                           ("HK$1,234.50", 123450)):
            with self.subTest(raw=raw):
                self.assertEqual(wallet_amount(raw), cents)

    def test_refused(self):
        for raw in ("", "abc", "0", "-5", "38,5055", "1,2,3", None, True, [], 0, -1, 1e12, 12.345):
            with self.subTest(raw=raw):
                self.assertIsNone(wallet_amount(raw))


class DeviceClient(ApiTest):
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


class WalletRoute(DeviceClient):
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
        for body in ({"amount": "abc"}, {"amount": "0"}):  # a merchant alone is a real tap without an amount
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)
        self.assertEqual(self.post({"amount": "38"}, device="bad")[0], 400)

    def test_the_last_message_is_kept_to_check_the_setup(self):
        self.assertIsNone(self.device_state()["walletLast"])
        self.assertEqual(self.post({"amount": "abc", "merchant": "Bakery"})[0], 400)
        last = self.device_state()["walletLast"]
        self.assertFalse(last["ok"])
        self.assertEqual(last["amount"], "abc")
        self.assertIn("amount", last["detail"].lower())
        self.post({"amount": "38,00 $HK", "merchant": "Bakery"})
        last = self.device_state()["walletLast"]
        self.assertTrue(last["ok"])
        self.assertEqual(last["detail"], "HK$38 from Bakery")
        self.assertRegex(last["at"], r"^\d{4}-\d\d-\d\dT")

    def test_a_run_by_hand_checks_the_link_without_paying(self):
        # Run from the Shortcuts editor, the automation has no payment, so no amount: the link works.
        for body in ({}, {"amount": ""}, {"amount": "  "}, {"amount": None, "merchant": ""}):
            with self.subTest(body=body):
                self.assertEqual(self.post(body)[0], 400)
                last = self.device_state()["walletLast"]
                self.assertFalse(last["ok"])
                self.assertTrue(last["linkOk"])
                self.assertIn("the link works", last["detail"])
        self.assertEqual(self.device_state()["inbox"], [])

    def test_a_merchant_that_is_not_text_is_ignored(self):
        status, _, payload = self.post({"amount": "12", "merchant": {"name": "x"}, "card": 5})
        self.assertEqual(status, 200, payload)
        item = self.device_state()["inbox"][0]
        self.assertEqual((item["merchant"], item["card"]), ("Apple Pay payment", "Apple Pay"))

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


class WidgetRoute(DeviceClient):
    """GET /api/widget: what the iOS home screen widget shows, as JSON, for the phone in the header."""

    def widget(self, device=DEVICE):
        status, headers, payload = self.get("/api/widget", device)
        self.assertEqual(status, 200, payload)
        self.assertIn("application/json", headers["Content-Type"])
        return json.loads(payload)

    def test_before_a_budget(self):
        data = self.widget()
        self.assertEqual({k: data[k] for k in ("ready", "left", "leftText", "over", "streak", "shape", "toReview")},
                         {"ready": False, "left": 0, "leftText": "HK$0", "over": False,
                          "streak": 0, "shape": "square", "toReview": 0})
        self.assertEqual((data["funds"], data["payments"]), ([], []))

    def test_with_a_budget_and_a_payment_to_review(self):
        self.post({"amount": "12", "merchant": "Bakery"}, path="/api/shortcut/wallet")
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
        data = self.widget()
        self.assertTrue(data["ready"])
        self.assertEqual((data["left"], data["leftText"], data["over"]), (17000, "HK$170", False))
        self.assertEqual(data["toReview"], 1)
        self.assertIsInstance(data["streak"], int)
        self.assertEqual(data["allowanceText"], "HK$170")
        self.assertEqual((data["spentText"], data["spentRatio"]), ("HK$0", 0))
        self.assertEqual(data["daysLeft"], self.device_state()["view"]["daysLeft"])
        self.assertEqual([f["fund"] for f in data["funds"]],
                         ["main", "snack", "fixed", "experience", "development", "savings"])
        main = data["funds"][0]
        self.assertEqual(set(main), {"fund", "name", "left", "leftText", "allocationText", "level"})
        self.assertEqual(main["level"], 1000)

    def test_today_payments_newest_first(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            for path, body in (("/api/settings", FUNDS_TEXT),
                               ("/api/payments", {"amount": "42", "category": "main", "note": "Lunch", "requestId": "a" * 16}),
                               ("/api/payments", {"amount": "8.5", "category": "snack", "note": "", "requestId": "b" * 16})):
                data = json.dumps(body).encode("utf-8")
                conn.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
                conn.putheader("Host", f"127.0.0.1:{self.port}")
                conn.putheader("X-SSUST-Device", DEVICE)
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(data)))
                conn.endheaders(data)
                response = conn.getresponse()
                self.assertEqual(response.status, 200, response.read())
                response.read()
        finally:
            conn.close()
        data = self.widget()
        self.assertEqual(data["payments"], [{"label": "Snacks", "amountText": "HK$8.50", "fund": "snack"},
                                            {"label": "Lunch", "amountText": "HK$42", "fund": "main"}])
        self.assertEqual(data["spentText"], "HK$50.50")
        self.assertEqual(data["spentRatio"], 297)  # 5050 of 17000, per mille

    def test_bad_device_refused(self):
        self.assertEqual(self.get("/api/widget", device="bad")[0], 400)


class NativeWidget(unittest.TestCase):
    """A WidgetKit extension in the Xcode project. It cannot be built here (no Mac): these checks
    keep the project file and the Swift code consistent with the server and with Codemagic."""

    def read(self, *parts):
        return ROOT.joinpath(*parts).read_text(encoding="utf-8")

    def test_extension_target_is_in_the_project_and_embedded(self):
        project = self.read("ios", "App", "App.xcodeproj", "project.pbxproj")
        self.assertIn('productType = "com.apple.product-type.app-extension";', project)
        self.assertIn("PRODUCT_BUNDLE_IDENTIFIER = com.adamattar.ssust.widget;", project)
        self.assertIn("SSUSTWidget.appex in Embed Foundation Extensions", project)
        self.assertIn("dstSubfolderSpec = 13;", project)
        self.assertIn("INFOPLIST_FILE = SSUSTWidget/Info.plist;", project)
        # The Codemagic sed sets every build number at once: app and widget must match for Apple.
        versions = set(re.findall(r"CURRENT_PROJECT_VERSION = (\d+);", project))
        self.assertEqual(len(versions), 1, versions)
        marketing = set(re.findall(r"MARKETING_VERSION = ([\d.]+);", project))
        self.assertEqual(len(marketing), 1, marketing)
        self.assertEqual(project.count("{"), project.count("}"))
        self.assertEqual(project.count("("), project.count(")"))

    def test_object_ids_are_unique(self):
        project = self.read("ios", "App", "App.xcodeproj", "project.pbxproj")
        defined = re.findall(r"^\t\t([0-9A-F]{24}) (?:/\*.*?\*/ )?= \{", project, re.M)
        self.assertEqual(len(defined), len(set(defined)))
        for ref in set(re.findall(r"\b([0-9A-F]{24})\b", project)):
            with self.subTest(ref=ref):
                self.assertIn(ref, defined)

    def test_extension_info_and_code(self):
        with open(ROOT / "ios" / "App" / "SSUSTWidget" / "Info.plist", "rb") as handle:
            info = plistlib.load(handle)
        self.assertEqual(info["NSExtension"]["NSExtensionPointIdentifier"], "com.apple.widgetkit-extension")
        swift = self.read("ios", "App", "SSUSTWidget", "SSUSTWidget.swift")
        for word in ("@main", "WidgetBundle", "AppIntentConfiguration", "X-SSUST-Device", "/api/widget",
                     "https://ssust-api.onrender.com", "leftText", "toReview", "containerBackground"):
            self.assertIn(word, swift)

    def test_the_app_shares_the_phone_code_through_an_app_group(self):
        # No code to paste: the app writes the phone id into the shared App Group, the widget reads it.
        group = "group.com.adamattar.ssust"
        for parts in (("App", "App.entitlements"), ("SSUSTWidget", "SSUSTWidget.entitlements")):
            with self.subTest(file=parts[-1]):
                with open(ROOT.joinpath("ios", "App", *parts), "rb") as handle:
                    self.assertEqual(plistlib.load(handle)["com.apple.security.application-groups"], [group])
        project = self.read("ios", "App", "App.xcodeproj", "project.pbxproj")
        self.assertEqual(project.count("CODE_SIGN_ENTITLEMENTS = App/App.entitlements;"), 2)
        self.assertEqual(project.count("CODE_SIGN_ENTITLEMENTS = SSUSTWidget/SSUSTWidget.entitlements;"), 2)
        self.assertIn("AppViewController.swift in Sources", project)
        bridge = self.read("ios", "App", "App", "AppViewController.swift")
        for word in ("CAPBridgeViewController", "capacitorDidLoad", '"ssustWidget"', group, "reloadAllTimelines"):
            self.assertIn(word, bridge)
        storyboard = self.read("ios", "App", "App", "Base.lproj", "Main.storyboard")
        self.assertIn('customClass="AppViewController" customModule="App" customModuleProvider="target"', storyboard)
        swift = self.read("ios", "App", "SSUSTWidget", "SSUSTWidget.swift")
        self.assertIn(f'UserDefaults(suiteName: "{group}")', swift)
        sync = self.read("frontend", "js", "widgetsync.js")
        self.assertIn("messageHandlers", sync)
        self.assertIn("ssustWidget", sync)
        self.assertIn("syncWidget(", self.read("frontend", "js", "render.js"))

    def test_the_scene_uses_the_view_controller_that_talks_to_the_widget(self):
        # The window is made in SceneDelegate (not from Main.storyboard): it must use our subclass,
        # or the "ssustWidget" channel never exists and the widget never gets the phone id.
        scene = self.read("ios", "App", "App", "SceneDelegate.swift")
        self.assertIn("window?.rootViewController = AppViewController()", scene)
        self.assertNotIn("CAPBridgeViewController()", scene)
        self.assertIn("widgetLinked", self.read("frontend", "js", "widgetsync.js"))
        self.assertIn("widgetLinked()", self.read("frontend", "js", "screens", "shortcuts.js"))

    def test_richer_widget_sizes(self):
        swift = self.read("ios", "App", "SSUSTWidget", "SSUSTWidget.swift")
        for family in (".systemSmall", ".systemMedium", ".systemLarge", ".accessoryCircular", ".accessoryRectangular"):
            self.assertIn(family, swift)
        for field in ("funds", "payments", "spentRatio", "allowanceText"):
            self.assertIn(field, swift)

    def test_codemagic_signs_the_widget_with_the_app(self):
        # Codemagic fetches profiles for every bundle id that starts with the app's id.
        text = self.read("codemagic.yaml")
        self.assertIn("bundle_identifier: com.adamattar.ssust", text)

    def test_settings_explains_the_widget(self):
        guide = self.read("frontend", "js", "screens", "shortcuts.js")
        self.assertIn("SSUST widget", guide)


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
