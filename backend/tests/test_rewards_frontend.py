"""The new screens and the iPhone app: Feedback as the last tab, rewards, the map's meal budget,
no demo in the app, room for the status bar and no double-tap zoom."""

import re
import unittest
from pathlib import Path

from ssust import rewards

ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"
JS = FRONTEND / "js"


def read(path):
    return path.read_text(encoding="utf-8")


class Navigation(unittest.TestCase):
    def test_feedback_is_the_last_tab(self):
        html = read(FRONTEND / "index.html")
        nav = html[html.index('<nav class="nav"'):html.index("</nav>")]
        self.assertEqual(re.findall(r'data-screen="(\w+)"', nav), ["today", "map", "week", "settings", "feedback"])
        self.assertIn("grid-template-columns: repeat(5, 1fr);", read(FRONTEND / "styles.css"))

    def test_feedback_screen(self):
        self.assertIn("feedback: feedbackScreen", read(JS / "render.js"))
        screen = read(JS / "screens" / "feedback.js")
        for word in ('data-rating="', 'id="feedback-text"', 'maxlength="500"', 'id="send-feedback"'):
            self.assertIn(word, screen)
        actions = read(JS / "actions.js")
        self.assertIn('api("/api/feedback", { rating', actions)
        # Private feedback: the app never asks for a list (only the team reads it).
        self.assertNotIn('api("/api/feedback")', actions)


class Rewards(unittest.TestCase):
    def test_a_shape_for_every_streak_level(self):
        text = read(JS / "rewards.js")
        for shape, _, _ in rewards.STREAK_SHAPES:
            with self.subTest(shape=shape):
                self.assertIn(f"{shape}:", text)

    def test_where_they_show(self):
        self.assertIn("rewardsStrip(", read(JS / "screens" / "today.js"))
        self.assertIn("progressCard(", read(JS / "screens" / "week.js"))
        self.assertIn("medalLine(", read(JS / "screens" / "map.js"))
        self.assertIn("streakChip(", read(JS / "widget.js"))

    def test_stars_and_badges(self):
        text = read(JS / "rewards.js")
        self.assertIn("lastWeek", text)
        self.assertIn("badge.earned", text)
        self.assertIn('role="img"', text)


class MapMeals(unittest.TestCase):
    def test_compares_with_one_meals_share(self):
        screen = read(JS / "screens" / "map.js")
        self.assertIn("data.budget.perMeal", screen)
        self.assertIn("mealsLeft", screen)

    def test_log_a_meal_here_sends_the_place(self):
        self.assertIn("data-log-place", read(JS / "screens" / "map.js"))
        actions = read(JS / "actions.js")
        self.assertIn("export function logMealAt(", actions)
        self.assertIn("if (place) body.place = place;", actions)
        self.assertIn("place: pending.place || null", actions)


class NativeApp(unittest.TestCase):
    def test_each_phone_sends_its_own_id(self):
        config = read(JS / "config.js")
        self.assertIn("export function deviceId()", config)
        self.assertIn("crypto.getRandomValues", config)
        api = read(JS / "api.js")
        self.assertIn('"X-SSUST-Device"', api)
        self.assertIn("NATIVE", api)

    def test_no_demo_in_the_app(self):
        settings = read(JS / "screens" / "settings.js")
        self.assertIn("if (NATIVE)", settings)
        main = read(JS / "main.js")
        self.assertIn('document.documentElement.classList.add("native")', main)
        self.assertIn("if (!NATIVE) maybeOfferTour();", main)
        self.assertIn("if (NATIVE || !auto", read(JS / "notifications.js"))
        css = read(FRONTEND / "styles.css")
        self.assertIn("html.native #tour-btn", css)
        self.assertIn("html.native .mode-badge", css)

    def test_room_for_the_status_bar(self):
        css = read(FRONTEND / "styles.css")
        self.assertIn("html.native .top", css)
        self.assertIn("env(safe-area-inset-top", css)

    def test_no_double_tap_zoom(self):
        css = read(FRONTEND / "styles.css")
        self.assertIn("touch-action: manipulation;", css)
        self.assertIn("user-scalable=no", read(JS / "main.js"))
        # The web page keeps zoom: the viewport in index.html is unchanged.
        self.assertIn('content="width=device-width, initial-scale=1, viewport-fit=cover"', read(FRONTEND / "index.html"))


if __name__ == "__main__":
    unittest.main()
