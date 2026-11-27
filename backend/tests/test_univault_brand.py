"""The UniVault logo and name where people see the app: the header, the page icon, the home
screen icon and widgets, the iOS app name and the iOS widgets. Code names (ssust package, X-SSUST-Device
header, bundle id, App Group) stay as they are."""

import plistlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"
JS = FRONTEND / "js"
IOS = ROOT / "ios" / "App"


def read(path):
    return path.read_text(encoding="utf-8")


def png_size(path):
    head = path.read_bytes()[:24]
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


class WebBrand(unittest.TestCase):
    def test_page_title_header_and_home_icon(self):
        html = read(FRONTEND / "index.html")
        self.assertIn("<title>UniVault</title>", html)
        self.assertIn('alt="UniVault"', html)
        self.assertIn('<span class="app-name">UniVault</span>', html)
        self.assertIn('aria-label="UniVault app"', html)

    def test_header_logo_size_matches_the_image(self):
        html = read(FRONTEND / "index.html")
        tag = re.search(r'<img class="brand-logo" src="img/logo.png"[^>]*>', html).group(0)
        width = int(re.search(r'width="(\d+)"', tag).group(1))
        height = int(re.search(r'height="(\d+)"', tag).group(1))
        real_w, real_h = png_size(FRONTEND / "img" / "logo.png")
        self.assertEqual(real_h, 96)  # 3x the 32 px header
        self.assertAlmostEqual(width / height, real_w / real_h, delta=0.05)

    def test_icons_keep_their_sizes(self):
        self.assertEqual(png_size(FRONTEND / "img" / "icon-64.png"), (64, 64))
        self.assertEqual(png_size(FRONTEND / "img" / "icon-180.png"), (180, 180))

    def test_widgets_say_univault(self):
        for name in ("widgets.js", "widget.js"):
            with self.subTest(file=name):
                text = read(JS / name)
                self.assertIn("UniVault", text)
                self.assertNotRegex(text, r">SSUST[ <]")
                self.assertNotIn('aria-label="SSUST', text)

    def test_camera_hint_names_the_ios_app(self):
        self.assertIn("Settings > UniVault > Camera", read(JS / "format.js"))


class IosBrand(unittest.TestCase):
    def test_home_screen_name(self):
        with open(IOS / "App" / "Info.plist", "rb") as handle:
            info = plistlib.load(handle)
        self.assertEqual(info["CFBundleDisplayName"], "UniVault")
        self.assertIn("UniVault", info["NSCameraUsageDescription"])
        self.assertIn("UniVault", info["NSPhotoLibraryUsageDescription"])

    def test_widgets_say_univault(self):
        swift = read(IOS / "SSUSTWidget" / "SSUSTWidget.swift")
        self.assertNotIn('Text("SSUST")', swift)
        self.assertNotIn('configurationDisplayName("SSUST")', swift)
        self.assertIn('configurationDisplayName("UniVault")', swift)


if __name__ == "__main__":
    unittest.main()
