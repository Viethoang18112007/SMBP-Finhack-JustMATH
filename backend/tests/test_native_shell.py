"""The iOS shell (Capacitor) wraps the same frontend without changing the web version.

The web app keeps working with no build step and no npm: package.json is only for the iOS shell,
API calls go through one config point that is empty on the web, and the phone frame and the
simulated home screen are skipped only when running natively.
"""

import http.client
import json
import plistlib
import re
import unittest
from pathlib import Path

from unittest import mock

from ssust.server import APP_ORIGINS

from tests.test_api import FUNDS_TEXT, ApiTest

ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"
JS = FRONTEND / "js"


def read(path):
    return path.read_text(encoding="utf-8")


class ApiBase(unittest.TestCase):
    def test_config_point_exists(self):
        self.assertTrue((JS / "config.js").is_file())

    def test_web_base_is_empty_and_native_base_is_the_hosted_server(self):
        text = read(JS / "config.js")
        # The Render service from render.yaml (ssust-api), over https, no trailing slash.
        self.assertIn('export const NATIVE_API_BASE = "https://ssust-api.onrender.com";', text)
        self.assertIn('export const API_BASE = NATIVE ? NATIVE_API_BASE : "";', text)

    def test_native_detection_uses_capacitor_and_never_throws(self):
        text = read(JS / "config.js")
        self.assertIn("window.Capacitor", text)
        self.assertIn("isNativePlatform", text)
        self.assertIn("try {", text)
        self.assertIn("return false;", text)

    def test_api_calls_go_through_the_config_point(self):
        text = read(JS / "api.js")
        self.assertIn('import { NATIVE, apiUrl, deviceId } from "./config.js";', text)
        self.assertIn("fetch(apiUrl(path)", text)

    def test_no_module_fetches_the_api_directly(self):
        for path in sorted(JS.rglob("*.js")):
            if path.name == "api.js":
                continue
            with self.subTest(module=path.relative_to(JS).as_posix()):
                for call in re.findall(r"fetch\(([^,)]*)", read(path)):
                    self.assertNotIn("/api", call)


class NativeView(unittest.TestCase):
    def test_no_phone_frame_when_native(self):
        text = read(JS / "device.js")
        self.assertIn('import { NATIVE } from "./config.js";', text)
        self.assertIn("return Boolean(!NATIVE && state.phoneView && wide.matches);", text)

    def test_home_screen_only_inside_the_frame(self):
        text = read(JS / "device.js")
        self.assertIn('const home = framed && state.deviceView === "home";', text)
        self.assertIn('return isFramed() && state.deviceView === "home";', text)


class ShellFiles(unittest.TestCase):
    def test_package_json_is_only_the_ios_shell(self):
        pkg = json.loads(read(ROOT / "package.json"))
        self.assertTrue(pkg.get("private"))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        self.assertEqual(set(deps), {"@capacitor/core", "@capacitor/cli", "@capacitor/ios"})
        # No build step for the web app: nothing to run before serving frontend/.
        self.assertNotIn("build", pkg.get("scripts", {}))

    def test_capacitor_config(self):
        config = json.loads(read(ROOT / "capacitor.config.json"))
        self.assertEqual(config["appName"], "SSUST")
        self.assertEqual(config["webDir"], "frontend")
        self.assertRegex(config["appId"], r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
        self.assertNotIn("server", config, "server.url is for live reload only, never for a release")
        self.assertIn("<head>", read(FRONTEND / "index.html"))

    def test_secrets_and_node_modules_are_ignored(self):
        lines = read(ROOT / ".gitignore").splitlines()
        for pattern in ("node_modules/", "*.p8", "*.p12", "*.mobileprovision"):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, lines)

    def test_run_and_serve_do_not_need_node(self):
        for name in ("run.py", "serve.py"):
            with self.subTest(file=name):
                text = read(ROOT / name)
                self.assertNotIn("npm", text)
                self.assertNotIn("node_modules", text)


class Codemagic(unittest.TestCase):
    def setUp(self):
        self.text = read(ROOT / "codemagic.yaml")

    def test_machine_and_integration(self):
        self.assertIn("instance_type: mac_mini_m2", self.text)
        self.assertIn("app_store_connect: SSUST_ASC_KEY", self.text)

    def test_automatic_signing_for_the_app_store(self):
        self.assertIn("distribution_type: app_store", self.text)
        config = json.loads(read(ROOT / "capacitor.config.json"))
        self.assertIn(f"bundle_identifier: {config['appId']}", self.text)

    def test_steps_in_order(self):
        steps = ["npm ci", "npx cap sync ios", "xcode-project use-profiles", "$BUILD_NUMBER",
                 "xcode-project build-ipa"]
        positions = [self.text.find(step) for step in steps]
        self.assertNotIn(-1, positions, dict(zip(steps, positions)))
        self.assertEqual(positions, sorted(positions))

    def test_build_number_is_above_the_latest_testflight_build(self):
        # Codemagic counts from 1 again for every new application; Apple refuses a used number.
        self.assertIn("APP_STORE_APPLE_ID: 6837791284", self.text)
        self.assertIn('app-store-connect get-latest-testflight-build-number "$APP_STORE_APPLE_ID"', self.text)
        self.assertIn("LATEST + 1", self.text)

    def test_publishes_to_testflight_through_the_integration(self):
        self.assertIn("auth: integration", self.text)
        # Upload without asking for an external beta review (that failed while another build was in review).
        self.assertIn("submit_to_testflight: false", self.text)

    def test_no_secret_in_the_file(self):
        self.assertNotIn("BEGIN PRIVATE KEY", self.text)
        self.assertNotRegex(self.text, r"(?i)(key_id|issuer_id|private_key)\s*:")


class AppOrigin(ApiTest):
    """The iOS app's page comes from capacitor://localhost, so its API calls are cross-origin."""

    APP = "capacitor://localhost"

    def send(self, method, path, origin=None, body=None, extra=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            if origin:
                conn.putheader("Origin", origin)
            for name, value in (extra or {}).items():
                conn.putheader(name, value)
            data = json.dumps(body).encode("utf-8") if body is not None else None
            if data is not None:
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data)
            response = conn.getresponse()
            return response.status, response.headers, response.read()
        finally:
            conn.close()

    def test_only_the_ios_app_origin_is_allowed(self):
        self.assertEqual(APP_ORIGINS, (self.APP,))

    def test_api_answers_the_app_origin(self):
        status, headers, _ = self.send("GET", "/api/state", self.APP)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.APP)
        self.assertEqual(headers["Vary"], "Origin")
        self.assertIsNone(headers["Access-Control-Allow-Credentials"])

    def test_post_from_the_app_goes_through_the_normal_rules(self):
        status, headers, payload = self.send("POST", "/api/payments", self.APP,
                                             {"amount": "-1", "category": "main", "note": "", "requestId": "r1"})
        self.assertEqual(status, 400, payload)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.APP)

    def test_preflight_from_the_app(self):
        status, headers, payload = self.send("OPTIONS", "/api/payments", self.APP, extra={
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(status, 204, payload)
        self.assertEqual(payload, b"")
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.APP)
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, POST")
        self.assertEqual(headers["Access-Control-Allow-Headers"], "Content-Type, X-SSUST-Device")
        self.assertEqual(headers["Access-Control-Max-Age"], "600")
        for name in ("X-Content-Type-Options", "Content-Security-Policy"):
            self.assertIsNotNone(headers[name])

    def test_other_origins_get_no_cors_headers(self):
        for origin in (None, "https://evil.example", "capacitor://localhost.evil.example", "http://localhost"):
            with self.subTest(origin=origin):
                status, headers, _ = self.send("GET", "/api/state", origin)
                self.assertEqual(status, 200)
                self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_preflight_refused_for_other_origins_and_non_api_paths(self):
        for origin, path in (("https://evil.example", "/api/payments"), (None, "/api/payments"),
                             (self.APP, "/index.html"), (self.APP, "/")):
            with self.subTest(origin=origin, path=path):
                status, headers, _ = self.send("OPTIONS", path, origin)
                self.assertEqual(status, 403)
                self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_static_files_get_no_cors_headers(self):
        status, headers, _ = self.send("GET", "/index.html", self.APP)
        self.assertEqual(status, 200)
        self.assertIsNone(headers["Access-Control-Allow-Origin"])

    def test_preflight_still_checks_the_host(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest("OPTIONS", "/api/state", skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", "evil.example")
            conn.putheader("Origin", self.APP)
            conn.endheaders()
            response = conn.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIsNone(response.headers["Access-Control-Allow-Origin"])
        finally:
            conn.close()


class RenderService(unittest.TestCase):
    def test_hosted_api_service(self):
        # A new name: the workspace already has an older "ssust" service tied to the old repository.
        text = read(ROOT / "render.yaml")
        lines = text.splitlines()
        self.assertIn("    name: ssust-api", lines)
        self.assertIn("    startCommand: python serve.py", lines)
        self.assertIn("    plan: free", lines)


class AppDevices(ApiTest):
    """Each iPhone sends its own id and gets its own live data. The app has no demo mode."""

    APP = AppOrigin.APP
    send = AppOrigin.send
    ONE = "a" * 32
    TWO = "b" * 32

    def device_call(self, method, path, device, body=None):
        status, headers, payload = self.send(method, path, self.APP, body, extra={"X-SSUST-Device": device})
        return status, json.loads(payload)

    def test_each_device_has_its_own_live_book(self):
        status, data = self.device_call("POST", "/api/settings", self.ONE, FUNDS_TEXT)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["mode"], "live")
        self.assertFalse(data["needsFunds"])
        self.assertTrue(self.device_call("GET", "/api/state", self.TWO)[1]["needsFunds"])
        self.assertTrue(self.state()["needsFunds"])  # the web book is untouched
        self.assertTrue((self.dir / "devices" / self.ONE / "ssust.db").is_file())

    def test_live_even_when_the_web_is_in_demo(self):
        self.call("POST", "/api/mode", {"mode": "demo"})
        self.assertEqual(self.device_call("GET", "/api/state", self.ONE)[1]["mode"], "live")

    def test_no_demo_in_the_app(self):
        status, data = self.device_call("POST", "/api/mode", self.ONE, {"mode": "demo"})
        self.assertEqual(status, 400)
        self.assertIn("demo", data["error"].lower())

    def test_bad_device_ids_are_refused(self):
        for device in ("short", "A" * 32, "g" * 32, "a" * 33, "../" + "a" * 29):
            with self.subTest(device=device):
                self.assertEqual(self.device_call("GET", "/api/state", device)[0], 400)

    def test_number_of_devices_is_capped(self):
        with mock.patch("ssust.server.MAX_DEVICES", 1):
            self.assertEqual(self.device_call("GET", "/api/state", self.ONE)[0], 200)
            status, data = self.device_call("GET", "/api/state", self.TWO)
            self.assertEqual(status, 503)
            self.assertEqual(self.device_call("GET", "/api/state", self.ONE)[0], 200)


class IosProject(unittest.TestCase):
    def test_export_compliance_is_declared(self):
        with open(ROOT / "ios" / "App" / "App" / "Info.plist", "rb") as handle:
            info = plistlib.load(handle)
        self.assertIs(info["ITSAppUsesNonExemptEncryption"], False)

    def test_app_icon_and_splash_are_ssust_without_alpha(self):
        # Apple refuses an app icon with an alpha channel. Colour type 2 is 8-bit RGB.
        assets = ROOT / "ios" / "App" / "App" / "Assets.xcassets"
        files = {assets / "AppIcon.appiconset" / "AppIcon-512@2x.png": 1024}
        for name in ("splash-2732x2732.png", "splash-2732x2732-1.png", "splash-2732x2732-2.png"):
            files[assets / "Splash.imageset" / name] = 2732
        for path, size in files.items():
            with self.subTest(file=path.name):
                head = path.read_bytes()[:26]
                self.assertEqual(head[:8], bytes([137, 80, 78, 71, 13, 10, 26, 10]))
                self.assertEqual((int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")), (size, size))
                self.assertEqual((head[24], head[25]), (8, 2))

    def test_native_error_message_does_not_mention_run_py(self):
        text = read(JS / "main.js")
        self.assertIn('import { NATIVE } from "./config.js";', text)
        self.assertIn("NATIVE_UNREACHABLE", text)


if __name__ == "__main__":
    unittest.main()
