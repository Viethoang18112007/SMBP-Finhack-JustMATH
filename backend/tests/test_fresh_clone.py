"""A fresh clone must work like the author's copy: every file the page loads is in git, the
widgets have something useful to show on an empty database, narrow screens can still reach them,
and the smoke script (scripts/smoke_fresh_clone.py) passes against a real server."""

import contextlib
import importlib.util
import io
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from ssust.dates import FixedClock
from ssust.server import FRONTEND, make_server

ROOT = Path(__file__).resolve().parent.parent.parent
JS = FRONTEND / "js"
SMOKE = ROOT / "scripts" / "smoke_fresh_clone.py"


def load_smoke():
    spec = importlib.util.spec_from_file_location("ssust_smoke", SMOKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_files():
    """Paths tracked by git (posix, relative to the repo root), or None outside a git checkout."""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {name for name in out.decode("utf-8").split("\0") if name}


class EverythingThePageLoadsIsInGit(unittest.TestCase):
    """A file that exists only on one computer (untracked or git-ignored) breaks every other clone."""

    def test_every_referenced_file_is_tracked(self):
        tracked = tracked_files()
        if tracked is None:
            self.skipTest("not a git checkout")
        smoke = load_smoke()
        needed = smoke.referenced_files(FRONTEND)
        self.assertGreater(len(needed), 20)
        for path in sorted(needed):
            rel = path.relative_to(ROOT).as_posix()
            with self.subTest(file=rel):
                self.assertTrue(path.is_file(), f"{rel} is referenced but missing")
                self.assertIn(rel, tracked, f"{rel} is referenced by the page but not in git")

    def test_referenced_files_cover_vendor_samples_and_modules(self):
        smoke = load_smoke()
        names = {p.relative_to(FRONTEND).as_posix() for p in smoke.referenced_files(FRONTEND)}
        for needle in ("vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/tesseract/tesseract.min.js",
                       "vendor/tesseract/worker.min.js", "vendor/tesseract/lang/eng.traineddata.gz",
                       "img/samples/receipt-mcd.png", "img/icon-64.png", "js/main.js", "js/widgets.js", "styles.css"):
            self.assertIn(needle, names)


class SmokeScript(unittest.TestCase):
    """The same checks a new teammate runs, against a real server on a temporary data folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name) / "data"

    def serve(self):
        server = make_server(self.data, FixedClock("2027-03-03"), port=0, places_fetcher=_no_fetch, quiet=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_checks_pass_on_an_empty_database(self):
        smoke = load_smoke()
        port = self.serve()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            problems = smoke.check_server(f"http://127.0.0.1:{port}", FRONTEND)
        self.assertEqual(problems, [], out.getvalue())
        self.assertIn("widgets", out.getvalue())

    def test_a_broken_endpoint_is_reported(self):
        smoke = load_smoke()
        problems = smoke.check_widget_state({"view": {"ready": True}, "mode": "live"})
        self.assertTrue(problems)

    def test_script_has_a_main_and_clone_option(self):
        text = SMOKE.read_text(encoding="utf-8")
        self.assertIn("def main(", text)
        self.assertIn("--clone", text)
        self.assertIn('if __name__ == "__main__":', text)


def _no_fetch(kind, radius_km, campus):
    raise AssertionError("the smoke checks must not fetch places")


class WidgetsWithoutABudget(unittest.TestCase):
    """First launch in live mode: HK$0 everywhere. The widgets say what to do instead of failing."""

    def setUp(self):
        self.widgets = (JS / "widgets.js").read_text(encoding="utf-8")
        self.quick = (JS / "widget.js").read_text(encoding="utf-8")

    def test_small_and_medium_widgets_have_a_setup_state(self):
        self.assertIn("function setupWidgetsHtml", self.widgets)
        setup = self.widgets[self.widgets.index("function setupWidgetsHtml"):]
        setup = setup[:setup.index("\n}\n")]
        self.assertIn("No budget yet", setup)
        self.assertIn('data-open-app="today"', setup)
        self.assertIn('data-switch="demo"', setup)
        self.assertIn("!data.view.ready", self.widgets)

    def test_quick_add_does_not_send_a_payment_without_a_budget(self):
        self.assertIn("function setupPane", self.quick)
        self.assertIn("data-w-setup", self.quick)
        add = self.quick[self.quick.index("async function addEntry"):]
        add = add[:add.index("\n}\n")]
        self.assertIn("!ready()", add)


class NarrowScreensReachTheWidgets(unittest.TestCase):
    """No phone frame (narrow window, or Phone view off): a header button opens the home screen."""

    def setUp(self):
        self.index = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.device = (JS / "device.js").read_text(encoding="utf-8")
        self.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_header_button(self):
        self.assertIn('id="home-btn"', self.index)
        self.assertIn('aria-label="Show the home screen widgets"', self.index)
        self.assertRegex(self.css, r"body\.phone-view #home-btn\s*\{\s*display:\s*none")

    def test_overlay_state_and_styles(self):
        self.assertIn("state.homeOpen", self.device)
        self.assertIn('classList.toggle("home-open"', self.device)
        self.assertIn("body.home-open .home", self.css)
        self.assertIn('name: "home"', self.device)  # Escape closes it

    def test_framed_behaviour_is_unchanged(self):
        self.assertIn("export function isFramed()", self.device)
        self.assertIn("(min-width: 901px)", self.device)


class NewerDatabase(unittest.TestCase):
    """A data folder written by a newer branch: a clear message and exit code 1, not a traceback."""

    def test_run_py_explains_a_newer_schema(self):
        spec = importlib.util.spec_from_file_location("ssust_run_newer", ROOT / "run.py")
        run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run)
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            con = sqlite3.connect(data / "ssust.db")
            con.execute("PRAGMA user_version = 99")
            con.close()
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = run.main(["--port", "0", "--data", str(data), "--no-browser"])
        self.assertEqual(code, 1)
        self.assertIn("newer", err.getvalue())
        self.assertIn("--data", err.getvalue())


class ReadmeTroubleshooting(unittest.TestCase):
    def test_section_with_the_commands(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("## Troubleshooting", text)
        section = text[text.index("## Troubleshooting"):]
        for needle in ("python scripts/smoke_fresh_clone.py", "python3 run.py", "--port 0", "--demo", "Widgets"):
            self.assertIn(needle, section)
        self.assertTrue(re.search(r"901", section), "explain when the phone frame shows")
