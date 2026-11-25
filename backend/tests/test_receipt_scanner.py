"""Receipts in the iPhone app are read on the phone by Apple's text recognition (Vision + VisionKit),
through a local Capacitor plugin, ReceiptScanner. The web app (and an app build without the plugin)
keeps the tesseract.js reader. Swift cannot be built here (no Mac): these checks keep the plugin,
the Xcode project and the web side consistent.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IOS = ROOT / "ios" / "App"
JS = ROOT / "frontend" / "js"


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def block(project, object_id):
    """The text of one pbxproj object, from its definition to its closing brace."""
    start = re.search(rf"^\t\t{object_id} (?:/\*.*?\*/ )?= \{{", project, re.M).start()
    return project[start:project.index("\n\t\t};", start)]


class Plugin(unittest.TestCase):
    def setUp(self):
        self.swift = read("ios", "App", "App", "ReceiptScanner.swift")

    def test_a_capacitor_plugin_named_receipt_scanner(self):
        self.assertIn("class ReceiptScannerPlugin: CAPPlugin, CAPBridgedPlugin, VNDocumentCameraViewControllerDelegate", self.swift)
        self.assertIn('let jsName = "ReceiptScanner"', self.swift)
        for method in ("scan", "recognize"):
            self.assertIn(f'CAPPluginMethod(name: "{method}", returnType: CAPPluginReturnPromise)', self.swift)
            self.assertIn(f"@objc func {method}(_ call: CAPPluginCall)", self.swift)

    def test_accurate_recognition_without_language_correction(self):
        self.assertIn("VNRecognizeTextRequest()", self.swift)
        self.assertIn("request.recognitionLevel = .accurate", self.swift)
        self.assertIn("request.usesLanguageCorrection = false", self.swift)

    def test_languages_are_checked_at_run_time(self):
        self.assertIn('["en-US", "zh-Hant", "zh-Hans"]', self.swift)
        self.assertIn("supportedRecognitionLanguages()", self.swift)

    def test_boxes_from_the_top_left(self):
        # Vision's boxes start at the bottom left; the web side expects the top left.
        self.assertIn('"y": Double(1 - box.maxY)', self.swift)
        for key in ('"text"', '"confidence"', '"x"', '"w"', '"h"', '"pages"'):
            self.assertIn(key, self.swift)

    def test_document_camera_and_permission(self):
        self.assertIn("VNDocumentCameraViewController.isSupported", self.swift)
        self.assertIn("AVCaptureDevice.authorizationStatus(for: .video)", self.swift)
        for code in ('"cancelled"', '"camera_denied"', '"unavailable"', '"bad_image"'):
            self.assertIn(code, self.swift)
        # UIKit work happens on the main thread, the reading on a background queue.
        self.assertIn("DispatchQueue.main.async", self.swift)
        self.assertIn("DispatchQueue.global(qos: .userInitiated).async", self.swift)

    def test_registered_by_the_app_view_controller(self):
        bridge = read("ios", "App", "App", "AppViewController.swift")
        self.assertIn("bridge?.registerPluginInstance(ReceiptScannerPlugin())", bridge)
        self.assertIn("super.capacitorDidLoad()", bridge)
        # the widget channel is still there
        self.assertIn('userContentController.add(widgetMessages, name: "ssustWidget")', bridge)

    def test_permissions_are_declared(self):
        info = read("ios", "App", "App", "Info.plist")
        self.assertIn("<key>NSCameraUsageDescription</key>", info)
        self.assertIn("<key>NSPhotoLibraryUsageDescription</key>", info)


class XcodeProject(unittest.TestCase):
    APP_SOURCES = "504EC3001FED79650016851F"
    WIDGET_SOURCES = "AA5517000000000000000008"
    APP_GROUP = "504EC3061FED79650016851F"
    WIDGET_GROUP = "AA5517000000000000000006"

    def setUp(self):
        self.project = read("ios", "App", "App.xcodeproj", "project.pbxproj")

    def ids(self):
        ref = re.search(r"\t\t([0-9A-F]{24}) /\* ReceiptScanner\.swift \*/ = \{isa = PBXFileReference; "
                        r"lastKnownFileType = sourcecode\.swift; path = ReceiptScanner\.swift; sourceTree = \"<group>\"; \};",
                        self.project)
        self.assertIsNotNone(ref, "file reference")
        build = re.search(r"\t\t([0-9A-F]{24}) /\* ReceiptScanner\.swift in Sources \*/ = \{isa = PBXBuildFile; "
                          rf"fileRef = {ref.group(1)} /\* ReceiptScanner\.swift \*/; \}};", self.project)
        self.assertIsNotNone(build, "build file")
        return ref.group(1), build.group(1)

    def test_file_is_in_the_app_target_only(self):
        ref, build = self.ids()
        self.assertIn(f"{build} /* ReceiptScanner.swift in Sources */,", block(self.project, self.APP_SOURCES))
        self.assertNotIn(build, block(self.project, self.WIDGET_SOURCES))
        self.assertIn(f"{ref} /* ReceiptScanner.swift */,", block(self.project, self.APP_GROUP))
        self.assertNotIn(ref, block(self.project, self.WIDGET_GROUP))
        self.assertEqual(self.project.count("ReceiptScanner.swift in Sources"), 2)  # definition + phase
        self.assertEqual(self.project.count("/* ReceiptScanner.swift */"), 3)  # definition + build file + group

    def test_deployment_targets_unchanged(self):
        # The widget needs iOS 17; the app stays on iOS 15 (Vision and VisionKit need 13).
        self.assertEqual(self.project.count("IPHONEOS_DEPLOYMENT_TARGET = 17.0;"), 2)
        self.assertEqual(self.project.count("IPHONEOS_DEPLOYMENT_TARGET = 15.0;"), 4)

    def test_no_new_framework_or_package(self):
        # Vision, VisionKit and AVFoundation are system frameworks, linked by the Swift imports.
        self.assertIn("files = (\n\t\t\t);", block(self.project, "AA5517000000000000000009"))
        self.assertEqual(self.project.count("isa = XCSwiftPackageProductDependency;"), 1)


if __name__ == "__main__":
    unittest.main()
