"""The assistant parts are rule based, and the screens say so where students meet them."""

import unittest

from ssust.server import FRONTEND

JS = FRONTEND / "js"


class SaysOfflineRules(unittest.TestCase):
    def test_this_week_cards(self):
        text = (JS / "screens" / "insights.js").read_text(encoding="utf-8")
        self.assertEqual(text.count("Offline rules, not AI."), 2)

    def test_quick_add(self):
        self.assertIn("offline rules, not AI", (JS / "widget.js").read_text(encoding="utf-8"))

    def test_cooked_score(self):
        self.assertIn("Plain rules, not AI.", (JS / "screens" / "cooked.js").read_text(encoding="utf-8"))
