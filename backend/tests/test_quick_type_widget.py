"""The Quick type bar: a second iOS widget shaped like a search bar. iOS widgets cannot take typed
text, so a tap opens the app (ssust://quick) on a sheet with the same typing field as the web
quick-add widget (read by offline rules, then added through the app's own Add flow).

It cannot be built here (no Mac): these checks keep the widget, the URL scheme, the native
hand-off and the web sheet consistent with each other."""

import plistlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IOS = ROOT / "ios" / "App"
JS = ROOT / "frontend" / "js"


def read(path):
    return path.read_text(encoding="utf-8")


class QuickTypeWidget(unittest.TestCase):
    def test_second_widget_in_the_bundle(self):
        swift = read(IOS / "SSUSTWidget" / "SSUSTWidget.swift")
        self.assertIn("struct QuickTypeWidget: Widget", swift)
        self.assertIn('kind: "SSUSTQuickType"', swift)
        bundle = swift[swift.index("struct SSUSTWidgets: WidgetBundle"):]
        self.assertIn("SSUSTWidget()", bundle)
        self.assertIn("QuickTypeWidget()", bundle)

    def test_bar_shape_and_tap_target(self):
        swift = read(IOS / "SSUSTWidget" / "SSUSTWidget.swift")
        widget = swift[swift.index("struct QuickTypeWidget: Widget"):swift.index("@main")]
        self.assertIn(".supportedFamilies([.systemMedium, .accessoryRectangular])", widget)
        self.assertIn('URL(string: "ssust://quick")', swift)
        self.assertIn(".widgetURL(quickURL)", swift)
        self.assertIn("$50 KFC dinner", swift)  # the same example as the web widget's field

    def test_the_app_declares_the_url_scheme(self):
        with open(IOS / "App" / "Info.plist", "rb") as handle:
            info = plistlib.load(handle)
        schemes = [s for t in info.get("CFBundleURLTypes", []) for s in t.get("CFBundleURLSchemes", [])]
        self.assertIn("ssust", schemes)


class NativeHandOff(unittest.TestCase):
    def test_scene_opens_the_quick_sheet_on_launch_and_while_running(self):
        scene = read(IOS / "App" / "SceneDelegate.swift")
        self.assertIn("connectionOptions.urlContexts", scene)  # cold start from the widget
        self.assertGreaterEqual(scene.count("handleQuick("), 3)  # defined, at launch, while running
        self.assertIn('url.scheme == "ssust" && url.host == "quick"', scene)
        self.assertIn("openQuickType()", scene)
        # Other URLs still reach Capacitor.
        self.assertIn("SceneDelegateProxy.shared.scene(scene, openURLContexts: URLContexts)", scene)

    def test_view_controller_waits_for_the_page(self):
        bridge = read(IOS / "App" / "AppViewController.swift")
        self.assertIn("func openQuickType()", bridge)
        self.assertIn("window.ssustOpenQuick", bridge)
        self.assertIn("evaluateJavaScript", bridge)
        self.assertIn("DispatchQueue.main.asyncAfter", bridge)  # retries until the module has loaded


class WebSheet(unittest.TestCase):
    def test_page_has_the_sheet(self):
        html = read(ROOT / "frontend" / "index.html")
        self.assertIn('id="quick-sheet"', html)
        self.assertIn('id="app-quick"', html)
        self.assertIn('data-backdrop="quicksheet"', html)
        self.assertIn('data-close="quicksheet"', html)
        # Inside the app, not on the simulated home screen.
        self.assertLess(html.index('id="phone"'), html.index('id="quick-sheet"'))

    def test_widget_module_renders_into_the_sheet_when_native(self):
        text = read(JS / "widget.js")
        self.assertIn('import { NATIVE } from "./config.js";', text)
        self.assertIn('NATIVE ? el("app-quick") : el("home-quick")', text)
        self.assertIn("window.ssustOpenQuick = openQuickSheet;", text)
        self.assertIn('registerOverlay({ name: "quicksheet"', text)
        self.assertIn("state.quickOpen", text)

    def test_only_the_type_tab_in_the_sheet(self):
        # The app has its own receipt scanner: the sheet is only for typing.
        text = read(JS / "widget.js")
        self.assertIn('NATIVE ? "" : `<div class="qa-tabs"', text)

    def test_settings_mentions_the_bar(self):
        guide = read(JS / "screens" / "shortcuts.js")
        self.assertIn("Quick type", guide)


if __name__ == "__main__":
    unittest.main()
