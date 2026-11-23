"""The README describes the real repository: clone URL, folder, CI badge, test count, screenshots."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
README = ROOT / "README.md"
REPO = "Viethoang18112007/HKBU-Hackathon-2.0-SSUST"


def text():
    return README.read_text(encoding="utf-8")


class Readme(unittest.TestCase):
    def test_clone_url_and_folder(self):
        self.assertIn(f"git clone https://github.com/{REPO}.git", text())
        self.assertIn("cd HKBU-Hackathon-2.0-SSUST\n", text())

    def test_ci_badge_uses_the_real_repo_and_workflow(self):
        workflow = ROOT / ".github" / "workflows" / "tests.yml"
        self.assertTrue(workflow.is_file())
        self.assertIn(f"https://github.com/{REPO}/actions/workflows/tests.yml/badge.svg", text())
        for url in re.findall(r"https://github\.com/[^)\s\"]+", text()):
            with self.subTest(url=url):
                self.assertTrue(url.startswith(f"https://github.com/{REPO}"), url)

    def test_test_count_is_the_real_one(self):
        backend = ROOT / "backend"
        suite = unittest.TestLoader().discover(str(backend / "tests"), top_level_dir=str(backend))
        found = re.search(r"The suite \((\d+) tests\)", text())
        self.assertIsNotNone(found, "README must state the suite size as 'The suite (N tests)'")
        self.assertEqual(int(found.group(1)), suite.countTestCases())

    def test_referenced_images_exist(self):
        for path in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text()):
            if path.startswith("http"):
                continue
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)

    def test_demo_video_link(self):
        line = next((l for l in text().splitlines() if l.startswith("Demo video:")), "")
        self.assertEqual(line, "Demo video: https://youtu.be/dwNjo46av5E")

    def test_no_long_dashes(self):
        self.assertNotIn("—", text())
        self.assertNotIn("–", text())


class NoBorrowWording(unittest.TestCase):
    """P1.1: SSUST moves no real money and lends nothing, so "borrow" appears nowhere a user can read it.

    The only allowed occurrence is the backward-compatible API alias in service.py.
    """

    def test_no_borrow_in_user_facing_files(self):
        files = [README, *(ROOT / "frontend").glob("*.html"), *(ROOT / "frontend" / "js").rglob("*.js"),
                 *(ROOT / "backend" / "ssust").glob("*.py")]
        for path in files:
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                if "LEGACY_CHOICES" in line:
                    continue
                with self.subTest(file=path.name, line=number):
                    self.assertNotRegex(line.lower(), r"borrow")
