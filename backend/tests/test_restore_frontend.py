"""The iPhone app keeps its own copy of its data and rebuilds the server from it.

Files are checked as text (there is no JS test runner). The pure decisions in frontend/js/backup.js
are also run with node when it is installed (tools/check_backup_js.mjs, the same script a person
runs by hand).
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
JS = ROOT / "frontend" / "js"


def read(path):
    return path.read_text(encoding="utf-8")


class DurablePlugin(unittest.TestCase):
    def test_preferences_is_pinned_to_the_capacitor_major(self):
        pkg = json.loads(read(ROOT / "package.json"))
        version = pkg["dependencies"]["@capacitor/preferences"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$", "pinned exactly, like the other Capacitor packages")
        self.assertEqual(version.split(".")[0], pkg["dependencies"]["@capacitor/core"].split(".")[0])
        lock = json.loads(read(ROOT / "package-lock.json"))
        self.assertEqual(lock["packages"]["node_modules/@capacitor/preferences"]["version"], version)

    def test_the_ios_package_includes_the_plugin(self):
        text = read(ROOT / "ios" / "App" / "CapApp-SPM" / "Package.swift")
        self.assertIn('.package(name: "CapacitorPreferences", path: "../../../node_modules/@capacitor/preferences")', text)
        self.assertIn('.product(name: "CapacitorPreferences", package: "CapacitorPreferences")', text)

    def test_durable_storage_uses_preferences_with_a_local_mirror(self):
        text = read(JS / "durable.js")
        self.assertIn("cap.Plugins && cap.Plugins.Preferences", text)
        self.assertIn('isPluginAvailable("Preferences")', text)
        self.assertIn("window.localStorage", text)
        self.assertGreaterEqual(text.count("try {"), 4)

    def test_the_device_id_lives_in_the_durable_store(self):
        config = read(JS / "config.js")
        self.assertIn("export function useDeviceId(id)", config)
        durable = read(JS / "durable.js")
        self.assertIn("export async function loadDeviceId()", durable)
        self.assertIn("writeDurable(DEVICE_KEY, id)", durable)


class Pure(unittest.TestCase):
    def test_backup_decisions_are_pure(self):
        text = read(JS / "backup.js")
        for word in ("import ", "window", "document", "fetch(", "localStorage", "Capacitor", "console."):
            with self.subTest(word=word):
                self.assertNotIn(word, text)
        for name in ("snapshotDecision", "needsRestore", "restoreBanner", "isStale", "offlineLabel", "parseSaved"):
            with self.subTest(name=name):
                self.assertIn(f"export function {name}(", text)
        self.assertIn('export const RESTORED_TEXT = "Your data was restored from this phone.";', text)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_backup_decisions_with_node(self):
        done = subprocess.run(["node", str(ROOT / "tools" / "check_backup_js.mjs")], capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("all backup checks passed", done.stdout)


class Flow(unittest.TestCase):
    def test_no_snapshot_content_is_ever_logged(self):
        for name in ("backup.js", "durable.js", "sync.js"):
            with self.subTest(module=name):
                self.assertNotIn("console.", read(JS / name))

    def test_sync_refreshes_the_copy_and_restores_it(self):
        text = read(JS / "sync.js")
        self.assertIn('api("/api/backup")', text)
        self.assertIn('api("/api/restore", copy.doc)', text)
        self.assertIn("clearTimeout(timer)", text)  # debounced
        self.assertIn("onApiWrite(", text)  # after every successful change

    def test_api_wakes_the_server_and_refuses_writes_while_offline(self):
        text = read(JS / "api.js")
        self.assertIn('fetch(apiUrl("/api/ping")', text)
        self.assertIn("export function setReadOnly(", text)
        self.assertIn("if (body && readOnly && path !== RESTORE_PATH)", text)
        self.assertIn('const RESTORE_PATH = "/api/restore";', text)  # the copy can go back while still offline

    def test_launch_wakes_first_and_falls_back_to_the_saved_state(self):
        text = read(JS / "main.js")
        wake = text.find("wake();")
        self.assertGreater(wake, 0)
        self.assertLess(wake, text.find("loadDeviceId()"))
        self.assertIn("lastSavedState()", text)
        self.assertIn("restoreIfNeeded(", read(JS / "main.js"))
        self.assertIn("WAKE_WAIT_MS", text)

    def test_the_offline_bar(self):
        html = read(ROOT / "frontend" / "index.html")
        self.assertRegex(html, r'<div class="offline-bar" id="offline-bar" role="status" aria-live="polite" hidden></div>')
        self.assertIn(".offline-bar", read(ROOT / "frontend" / "styles.css"))
        self.assertIn("offlineLabel(", read(JS / "render.js"))

    def test_web_keeps_no_backup(self):
        text = read(JS / "sync.js")
        self.assertGreaterEqual(len(re.findall(r"if \(!NATIVE\) return", text)), 3)


class Docs(unittest.TestCase):
    def test_manual_restore_checklist(self):
        text = read(ROOT / "docs" / "RESTORE_TEST.md")
        for words in ("Manual Deploy", "To review", "Your data was restored from this phone.", "Offline, last updated"):
            with self.subTest(words=words):
                self.assertIn(words, text)

    def test_readme_states_where_the_data_lives(self):
        text = read(ROOT / "README.md")
        self.assertIn("docs/RESTORE_TEST.md", text)
        self.assertIn("the copy on the phone is the backup", text)


if __name__ == "__main__":
    unittest.main()
