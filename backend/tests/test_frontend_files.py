"""The frontend as ES modules: the entry point, every import, and the served Content-Type."""

import mimetypes
import re
import unittest
from pathlib import Path
from unittest import mock

from ssust.server import FRONTEND, SECURITY_HEADERS

from tests.test_api import ApiTest

JS_ROOT = FRONTEND / "js"
IMPORT = re.compile(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s*['"]([^'"]+)['"]|^\s*import\s*['"]([^'"]+)['"]""",
                    re.MULTILINE)


def modules():
    return sorted(JS_ROOT.rglob("*.js"))


def imports_of(path):
    text = path.read_text(encoding="utf-8")
    return [a or b for a, b in IMPORT.findall(text)]


class ModuleFiles(unittest.TestCase):
    def test_index_loads_main_as_a_module(self):
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module" src="js/main.js"></script>', html)
        self.assertIn('<script src="vendor/leaflet/leaflet.js"></script>', html)
        self.assertNotIn('src="app.js"', html)

    def test_there_are_modules(self):
        self.assertTrue((JS_ROOT / "main.js").is_file())
        self.assertGreater(len(modules()), 1)

    def test_every_import_resolves_to_a_file_under_js(self):
        root = JS_ROOT.resolve()
        for path in modules():
            for spec in imports_of(path):
                with self.subTest(module=path.relative_to(JS_ROOT).as_posix(), spec=spec):
                    self.assertTrue(spec.startswith("./") or spec.startswith("../"), "relative imports only")
                    self.assertTrue(spec.endswith(".js"), "browsers need the .js suffix")
                    target = (path.parent / spec).resolve()
                    self.assertTrue(target.is_relative_to(root))
                    self.assertTrue(target.is_file())

    def test_every_module_is_reachable_from_main(self):
        seen, todo = set(), [(JS_ROOT / "main.js").resolve()]
        while todo:
            path = todo.pop()
            if path in seen:
                continue
            seen.add(path)
            todo.extend((path.parent / spec).resolve() for spec in imports_of(path))
        self.assertEqual(sorted(seen), sorted(p.resolve() for p in modules()))

    def test_no_inline_style_attributes(self):
        # The Content-Security-Policy has style-src 'self', which blocks style="..." in markup.
        for path in [FRONTEND / "index.html", *modules()]:
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"\bstyle\s*=\s*[\"'$]")


class LiveAndDemo(unittest.TestCase):
    """M10: the mode is visible on every screen and the demo buttons send the M7 request shape."""

    def html(self):
        return (FRONTEND / "index.html").read_text(encoding="utf-8")

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_mode_badge_in_the_header_and_switch_in_settings(self):
        # UX overhaul: the header sits outside #screen, so the mode chip stays on every screen;
        # the LIVE / DEMO switch itself moved to Settings (bound once, by delegation, in main.js).
        header = re.search(r"<header\b.*?</header>", self.html(), re.DOTALL)
        self.assertIsNotNone(header)
        self.assertIn('id="mode-badge"', header.group(0))
        self.assertNotIn(">SAMPLE<", header.group(0))
        settings = self.js("screens/settings.js")
        self.assertRegex(settings, r'data-switch="live"')
        self.assertRegex(settings, r'data-switch="demo"')
        self.assertIn('closest("button[data-switch]")', self.js("main.js"))

    def test_walkthrough_notes_are_not_in_the_app(self):
        # UX overhaul: the demo steps left the UI (live can never show them); the script lives in docs.
        self.assertNotIn('id="notes"', self.html())
        self.assertTrue((FRONTEND.parent / "docs" / "DEMO_SCRIPT.md").is_file())

    def test_demo_week_buttons_send_a_scenario(self):
        for path in modules():
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r'data-mode="(sample|empty|over)"')
        settings = self.js("screens/settings.js")
        for scenario in ("sample", "empty", "over"):
            self.assertIn(f'data-scenario="{scenario}"', settings)
        self.assertIn('{ mode: "demo", scenario }', self.js("actions.js"))

    def test_no_hard_coded_dates(self):
        for path in modules():
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"\b(Nov|November)\b")
                self.assertNotRegex(text, r"\b20\d\d-\d\d-\d\d\b")


class ServedAsJavaScript(ApiTest):
    def check_modules(self):
        for path in modules():
            url = "/" + path.relative_to(FRONTEND).as_posix()
            with self.subTest(url=url):
                status, headers, payload = self.request("GET", url)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], "text/javascript; charset=utf-8")
                self.assertEqual(payload, path.read_bytes())

    def test_every_module_is_served_as_text_javascript(self):
        self.check_modules()

    def test_type_does_not_come_from_the_os_mime_table(self):
        # Windows can map .js to text/plain in the registry, and browsers refuse such modules.
        with mock.patch.dict(mimetypes.types_map, {".js": "text/plain"}), \
                mock.patch("mimetypes.guess_type", return_value=("text/plain", None)):
            self.check_modules()


if __name__ == "__main__":
    unittest.main()


class WhereCanIEat(unittest.TestCase):
    """M11: campus choice and the budget fit on the map screen."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_campus_selector_comes_from_the_server_and_is_saved(self):
        screen = self.js("screens/map.js")
        self.assertIn("data-campus", screen)
        self.assertIn("state.data.campuses", screen)
        self.assertIn('"/api/campus"', self.js("actions.js"))
        for path in modules():
            with self.subTest(file=path.name):
                self.assertNotIn("Around HKUST", path.read_text(encoding="utf-8"))

    def test_fit_states_and_estimates_are_shown(self):
        # Changed in P1.5: the map shows each place's honest status, never a band "fits" for an estimate.
        screen = self.js("screens/map.js")
        for word in ("statusOf(place)", "place.label", "place.why", "Estimated - not a real menu price", "Over budget"):
            self.assertIn(word, screen)
        self.assertNotIn("FIT_WORDS[place.fit]", screen)
        self.assertIn("status", self.js("mapview.js"))

    def test_shopping_layer_is_hidden_by_default(self):
        screen = self.js("screens/map.js")
        self.assertIn('<details class="more-layers"', screen)
        self.assertIn('mapKind: "food"', self.js("store.js"))


class MapTiles(unittest.TestCase):
    """OSM tiles need a Referer (tile usage policy); the page itself keeps no-referrer."""

    def tile_layer_options(self):
        source = (JS_ROOT / "mapview.js").read_text(encoding="utf-8")
        found = re.search(r'tileLayer\(\s*"https://tile\.openstreetmap\.org/[^"]+",\s*\{(.*?)\}\s*\)', source, re.DOTALL)
        self.assertIsNotNone(found, "OSM tile layer not found in mapview.js")
        return source, found.group(1)

    def test_tile_requests_send_the_origin_as_referer(self):
        _, options = self.tile_layer_options()
        self.assertRegex(options, r'referrerPolicy:\s*"strict-origin-when-cross-origin"')

    def test_osm_attribution_stays_visible(self):
        source, options = self.tile_layer_options()
        self.assertRegex(options, r'''attribution:\s*(?:'[^']*|"[^"]*)OpenStreetMap''')
        self.assertNotIn("attributionControl", source)
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn("leaflet-control-attribution", css)

    def test_osm_attribution_text_and_link(self):
        # OSM's attribution guideline: "© OpenStreetMap contributors", linked to the copyright page.
        _, options = self.tile_layer_options()
        found = re.search(r'''attribution:\s*(?:'([^']*)'|"([^"]*)")''', options)
        self.assertIsNotNone(found, "attribution option not found")
        text = found.group(1) or found.group(2)
        self.assertEqual(text, '&copy; <a href="https://www.openstreetmap.org/copyright">'
                               'OpenStreetMap</a> contributors')

    def test_page_security_headers_unchanged(self):
        self.assertEqual(dict(SECURITY_HEADERS), {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            # 'wasm-unsafe-eval' lets the vendored offline OCR (tesseract.js) compile its WebAssembly.
            "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; "
                                       "img-src 'self' https://tile.openstreetmap.org",
            "Cache-Control": "no-store",
        })


class SettingsErrors(unittest.TestCase):
    """P0.1: the server's field error is shown next to that field; inputs start from the opening amounts."""

    def test_field_error_reaches_the_field(self):
        api = (JS_ROOT / "api.js").read_text(encoding="utf-8")
        self.assertIn("err.field = data.field", api)
        settings = (JS_ROOT / "budget.js").read_text(encoding="utf-8")  # the budget editor Settings uses
        self.assertIn("state.errorField === id", settings)
        self.assertIn('aria-invalid="true"', settings)

    def test_inputs_start_from_the_opening_amounts_not_todays_balances(self):
        settings = (JS_ROOT / "budget.js").read_text(encoding="utf-8")  # the budget editor Settings uses
        self.assertIn("state.data.opening[id]", settings)
        self.assertNotIn("fundsAtStart[id]", settings)


class NoDoubleSubmit(unittest.TestCase):
    """P0.4: each payment attempt carries a request id, and Save is disabled while it is pending."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_request_id_is_generated_with_a_fallback(self):
        fmt = self.js("format.js")
        self.assertIn("crypto.randomUUID", fmt.replace("c.randomUUID", "crypto.randomUUID"))
        self.assertIn("getRandomValues", fmt)

    def test_payments_send_the_request_id(self):
        actions = self.js("actions.js")
        self.assertIn("{ amount: raw, category, note, requestId }", actions)
        self.assertIn("requestId: pending.requestId", actions)
        self.assertIn("if (state.saving", actions)

    def test_save_button_is_disabled_while_saving(self):
        self.assertIn("disabled", self.js("screens/add.js"))
        self.assertIn("state.saving", self.js("screens/add.js"))
        self.assertIn("btn.disabled = state.saving", self.js("render.js"))


class ReallocationModal(unittest.TestCase):
    """P1.2: an accessible modal; one option is confirmed explicitly; Savings is last and marked."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_modal_semantics(self):
        sheet = self.js("sheet.js")
        for needle in ('role="dialog"', 'aria-modal="true"', "aria-labelledby", 'type="radio"', 'id="confirm-cover"',
                       'id="dismiss"', "Last resort", "tomorrowAfter", "fundsAfter", "cover"):
            with self.subTest(needle=needle):
                self.assertIn(needle, sheet)

    def test_savings_sorts_last(self):
        self.assertRegex(self.js("sheet.js"), r"const ORDER = \{ snack: 0, flex: 1, savings: 2 \};")

    def test_escape_and_focus_trap(self):
        main = self.js("main.js")
        self.assertIn('event.key === "Escape"', main)
        self.assertIn("trapFocus", main)
        self.assertIn(".inert = open", self.js("render.js"))

    def test_confirm_is_explicit_and_guarded(self):
        render = self.js("render.js")
        self.assertIn('getElementById("confirm-cover")', render)
        self.assertNotIn("data-choice", render)  # no option saves on a single click any more
        self.assertIn("if (state.saving || !pending || !choice) return;", self.js("actions.js"))


class UndoUi(unittest.TestCase):
    """P1.3: Undo has an explicit second step and calls the undo route; there is no edit."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_two_step_undo(self):
        rows = self.js("screens/rows.js")
        for needle in ("data-undo=", "data-undo-yes=", "data-undo-no", "aria-label=\"Undo the"):
            self.assertIn(needle, rows)
        self.assertIn('"/api/payments/undo"', self.js("actions.js"))

    def test_past_weeks_get_no_undo(self):
        self.assertIn("week === state.data ? { confirming: state.undoId } : null", self.js("screens/day.js"))


class TodayScreen(unittest.TestCase):
    """P1.4: "Left to spend today" leads, then spent today, then all six balances; Add shows a preview."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_today_order(self):
        today = self.js("screens/today.js")
        order = [today.index(text) for text in ("Left to spend today", ">Spent <", "Funds this week")]
        self.assertEqual(order, sorted(order))
        self.assertIn('const FUND_ORDER = ["main", "snack", "fixed", "experience", "development", "savings"];', today)

    def test_add_preview(self):
        # UX overhaul: plain words. The preview still says what is left, or that a choice is needed.
        self.assertIn('id="preview"', self.js("screens/add.js"))
        preview = self.js("preview.js")
        self.assertIn("Today left:", preview)
        self.assertIn("you choose where it comes from", preview)


class Polish(unittest.TestCase):
    """P1.6: dashes, focus, touch targets, current tab, small screens."""

    def css(self):
        return (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_no_long_or_medium_dashes_in_the_ui(self):
        for path in [FRONTEND / "index.html", *modules()]:
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("—", text)
                self.assertNotIn("–", text)

    def test_visible_keyboard_focus(self):
        self.assertIn(":focus-visible", self.css())
        self.assertNotRegex(self.css(), r"\.amount:focus\s*\{\s*outline:\s*none")

    def test_touch_targets(self):
        css = self.css()
        for selector in (".nav button", ".cats button", ".mode-switch button", ".ghost.small", ".toggle"):
            with self.subTest(selector=selector):
                block = re.search(re.escape(selector) + r"\s*\{[^}]*min-height:\s*44px", css)
                self.assertIsNotNone(block, f"{selector} needs min-height: 44px")

    def test_current_tab_is_announced(self):
        self.assertIn('aria-current', (JS_ROOT / "render.js").read_text(encoding="utf-8"))

    def test_small_screens(self):
        css = self.css()
        self.assertRegex(css, r"@media \(max-width: 480px\)")
        self.assertRegex(css, r"\.phone\s*\{[^}]*width:\s*min\(390px, 100%\)")


class Bonus(unittest.TestCase):
    """P2: a one-line weekly summary and subtle transitions that respect reduced motion."""

    def test_week_summary_line(self):
        week = (JS_ROOT / "screens" / "week.js").read_text(encoding="utf-8")
        self.assertIn("weekSummary", week)
        self.assertIn('class="week-summary"', week)

    def test_motion_is_optional(self):
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        self.assertIn("transition", css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", css)


class MotionTokens(unittest.TestCase):
    """Part A1/A2/A9: shared motion tokens, screen transitions, reduced motion."""

    def css(self):
        return (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_tokens_exist(self):
        css = self.css()
        for token in ("--dur-fast", "--dur-base", "--dur-slow", "--ease-out", "--ease-in", "--ease-spring"):
            with self.subTest(token=token):
                self.assertRegex(css, re.escape(token) + r"\s*:")

    def test_reduced_motion_cuts_the_tokens(self):
        found = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{\s*:root\s*\{([^}]*)\}", self.css())
        self.assertIsNotNone(found, "reduced motion must override the tokens")
        self.assertIn("--dur-base: 0.01ms", found.group(1))

    def test_no_literal_durations_in_transitions(self):
        # Every transition/animation uses the tokens, so the feel stays consistent.
        for line in self.css().splitlines():
            if re.search(r"\b(transition|animation)\s*:", line) and "none" not in line:
                with self.subTest(line=line.strip()):
                    self.assertNotRegex(line, r"\d+(\.\d+)?m?s\b")

    def test_screen_transitions(self):
        css = self.css()
        for name in ("enter-fwd", "enter-back", "enter-up"):
            self.assertIn(name, css)
        self.assertIn("screenEnterClass", (JS_ROOT / "motion.js").read_text(encoding="utf-8"))
        self.assertIn("screenEnterClass", (JS_ROOT / "render.js").read_text(encoding="utf-8"))


class ModalMotion(unittest.TestCase):
    """Part A3: the modal fades and slides in once, and plays an exit before it is removed."""

    def test_open_and_close_animations(self):
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        for needle in (".sheet.is-opening", ".sheet.is-closing", ".sheet::before"):
            with self.subTest(needle=needle):
                self.assertIn(needle, css)
        self.assertNotIn(".sheet:not([hidden]) .panel { animation", css)  # no replay on every re-render

    def test_exit_never_blocks(self):
        motion = (JS_ROOT / "motion.js").read_text(encoding="utf-8")
        self.assertIn("export function closeSheetAnimated", motion)
        self.assertIn("sheet.inert = true", motion)  # nothing in a closing modal can be clicked or focused
        render = (JS_ROOT / "render.js").read_text(encoding="utf-8")
        self.assertIn("closeSheetAnimated(sheet", render)


class NumbersAndBars(unittest.TestCase):
    """Part A4/A5: count-up on integer cents that always lands on the exact value; bars by scaleX."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def test_interpolation_lands_exactly(self):
        motion = self.js("motion.js")
        body = re.search(r"export function interpolateCents\(from, to, t\) \{(.*?)\n\}", motion, re.DOTALL)
        self.assertIsNotNone(body)
        self.assertIn("if (t >= 1) return to;", body.group(1))
        self.assertIn("Math.round(", body.group(1))  # whole cents on every frame

    def test_counted_values(self):
        today = self.js("screens/today.js")
        for key in ('data-count="left"', 'data-count="spent"', 'data-count="fund-${fund}"'):
            with self.subTest(key=key):
                self.assertIn(key, today)
        self.assertIn("animateCounts(root", self.js("render.js"))

    def test_bar_uses_transform(self):
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.bar > span \{[^}]*transform-origin")
        self.assertNotIn("data-width", self.js("screens/today.js"))
        self.assertIn("animateBars(root", self.js("render.js"))


class ListsAndMicro(unittest.TestCase):
    """Part A6/A7: rows enter (staggered on first render, capped), undone rows leave, micro-interactions."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def css(self):
        return (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_rows_are_keyed(self):
        self.assertIn('data-key="p-${p.id}"', self.js("screens/rows.js"))
        self.assertIn('data-key="d-${date}"', self.js("screens/week.js"))
        self.assertIn("animateEntrances(root", self.js("render.js"))

    def test_stagger_is_capped(self):
        self.assertRegex(self.js("motion.js"), r"const STAGGER_MAX = \d;")
        self.assertIn("--stagger", self.css())

    def test_undone_row_leaves(self):
        self.assertIn("await leaveElement(", self.js("actions.js"))
        self.assertIn(".is-leaving", self.css())

    def test_micro_interactions(self):
        css = self.css()
        self.assertRegex(css, r"button:not\(:disabled\):active\s*\{[^}]*transform: scale")
        self.assertIn("@media (hover: hover)", css)
        self.assertIn('id="nav-pill"', (FRONTEND / "index.html").read_text(encoding="utf-8"))
        self.assertIn("moveNavPill(", self.js("render.js"))


class MapMotion(unittest.TestCase):
    """Part A8: place rows fade in; a new campus or filter shows a new list that staggers in."""

    def test_place_rows_are_keyed_and_loading_pulses(self):
        screen = (JS_ROOT / "screens" / "map.js").read_text(encoding="utf-8")
        self.assertIn('data-key="pl-${escapeHtml(place.id)}"', screen)
        self.assertIn('"explain loading"', screen)
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.loading \{[^}]*animation")

    def test_list_after_loading_counts_as_a_first_render(self):
        self.assertIn("!prev || prev.size === 0", (JS_ROOT / "motion.js").read_text(encoding="utf-8"))
        self.assertIn("state.mapFitsOnly", (JS_ROOT / "render.js").read_text(encoding="utf-8"))


def tour_steps():
    import json
    text = (JS_ROOT / "tour-steps.js").read_text(encoding="utf-8")
    found = re.search(r"// STEPS-JSON-BEGIN\s*export const STEPS = (\[.*\]);\s*// STEPS-JSON-END", text, re.DOTALL)
    assert found, "STEPS must sit between the JSON markers"
    return json.loads(found.group(1))


def tour_constant(name):
    found = re.search(rf"export const {name} = (\d+);", (JS_ROOT / "tour.js").read_text(encoding="utf-8"))
    assert found, name
    return int(found.group(1))


class TourSteps(unittest.TestCase):
    """Part B4: the tour data is well formed, honest, and every target can be found."""

    PLACEMENTS = {"auto", "top", "bottom", "left", "right", "center"}
    SCREENS = {"home", "today", "add", "week", "map", "settings", None}  # home: the simulated home screen

    def test_shape(self):
        steps = tour_steps()
        self.assertGreaterEqual(len(steps), 8)
        ids = [s["id"] for s in steps]
        self.assertEqual(len(ids), len(set(ids)), "ids must be unique")
        allowed = {"id", "title", "body", "autoBody", "screen", "target", "autoTarget", "dynamic", "fallback",
                   "placement", "autoAction", "autoOnly"}
        for s in steps:
            with self.subTest(step=s.get("id")):
                self.assertLessEqual(set(s), allowed)
                for key in ("title", "body"):
                    self.assertIsInstance(s[key], str)
                    self.assertTrue(s[key].strip())
                self.assertIn(s["placement"], self.PLACEMENTS)
                self.assertIn(s["screen"], self.SCREENS)
                self.assertIsInstance(s["dynamic"], bool)
                self.assertIsInstance(s["autoOnly"], bool)

    def test_every_target_exists_or_has_a_fallback(self):
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        static_ids = set(re.findall(r'\bid="([^"]+)"', html))

        def in_html(selector):
            first = selector.split()[0]
            return first.startswith("#") and first[1:] in static_ids

        for s in tour_steps():
            for key in ("target", "autoTarget"):
                selector = s.get(key)
                if selector is None:
                    continue
                with self.subTest(step=s["id"], key=key):
                    if s["dynamic"]:
                        self.assertTrue(s["fallback"] and in_html(s["fallback"]),
                                        "a dynamic target needs a fallback from index.html")
                    else:
                        self.assertTrue(in_html(selector))

    def test_auto_actions_exist(self):
        tour = (JS_ROOT / "tour.js").read_text(encoding="utf-8")
        actions = re.search(r"const ACTIONS = \{(.*?)\n\};", tour, re.DOTALL)
        self.assertIsNotNone(actions)
        for s in tour_steps():
            if s["autoAction"]:
                with self.subTest(step=s["id"]):
                    self.assertRegex(actions.group(1), rf"\basync {re.escape(s['autoAction'])}\(")

    def test_honest_copy(self):
        steps = {s["id"]: s for s in tour_steps()}
        words = " ".join(s["title"] + " " + s["body"] + " " + s.get("autoBody", "") for s in steps.values())
        self.assertNotIn("—", words)
        self.assertNotIn("–", words)
        self.assertNotRegex(words.lower(), r"borrow|bank transfer|we pay|sends money")
        self.assertIn("No bank connection", steps["welcome"]["body"])
        self.assertIn("no real money", steps["welcome"]["body"])
        self.assertIn("not a real menu price", steps["map"]["body"])
        self.assertIn("OpenStreetMap", steps["map"]["body"])
        self.assertIn("Long-term Savings only as a last resort", steps["overspend"]["body"])
        # The real rule from money.py: food left (Main meals + Snacks) / days left, today included.
        self.assertIn("Main meals plus Snacks", steps["left-today"]["body"])
        self.assertIn("today included", steps["left-today"]["body"])


class TourTiming(unittest.TestCase):
    """Part B3/B4: each auto-play step lasts 4 to 7 seconds by text length; the run is about 90 s."""

    def duration(self, step):
        text = step["title"] + (step.get("autoBody") or step["body"])
        return min(tour_constant("STEP_MAX_MS"),
                   max(tour_constant("STEP_MIN_MS"), tour_constant("BASE_MS") + tour_constant("MS_PER_CHAR") * len(text)))

    def test_formula_in_tour_js(self):
        tour = (JS_ROOT / "tour.js").read_text(encoding="utf-8")
        self.assertIn("Math.min(STEP_MAX_MS, Math.max(STEP_MIN_MS, BASE_MS + MS_PER_CHAR * text.length))", tour)
        self.assertEqual((tour_constant("STEP_MIN_MS"), tour_constant("STEP_MAX_MS")), (4000, 7000))

    def test_steps_and_total(self):
        durations = [self.duration(s) for s in tour_steps()]
        for ms in durations:
            self.assertTrue(4000 <= ms <= 7000)
        # Reading time only; the scripted actions and animations add a few seconds on top.
        self.assertTrue(55000 <= sum(durations) <= 90000, sum(durations))


class TourSafety(unittest.TestCase):
    """Part B3: auto-play is DEMO only, uses the real UI paths, and storage can fail safely."""

    def tour(self):
        return (JS_ROOT / "tour.js").read_text(encoding="utf-8")

    def test_demo_only_guard(self):
        tour = self.tour()
        self.assertIn('export function canAutoplay(mode) {\n  return mode === "demo";\n}', tour)
        start = re.search(r"export async function startAutoplay\(\) \{(.*?)\n\}", tour, re.DOTALL)
        self.assertIsNotNone(start)
        body = start.group(1)
        self.assertLess(body.index("canAutoplay("), body.index("resetDemo("), "check the mode before any call")
        self.assertIn("function assertDemo()", tour)

    def test_same_paths_as_a_person(self):
        # No hidden shortcuts: the scripted actions click the real buttons (request ids, modal confirm).
        tour = self.tour()
        self.assertNotIn('from "./api.js"', tour)
        self.assertNotIn("fetch(", tour)
        self.assertIn('"#confirm-cover"', tour)

    def test_storage_is_wrapped(self):
        tour = self.tour()
        self.assertNotRegex(tour, r"\b(localStorage|sessionStorage)\.")
        self.assertIn("function storageGet(", tour)
        self.assertIn("function storageSet(", tour)

    def test_never_offered_or_started_in_live(self):
        tour = self.tour()
        offer = re.search(r"export function maybeOfferTour\(\) \{(.*?)\n\}", tour, re.DOTALL)
        self.assertIsNotNone(offer)
        self.assertIn('state.data.mode !== "demo"', offer.group(1))

    def test_wiring(self):
        html = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="tour-btn"', html)
        self.assertIn('data-tour="auto"', html)
        self.assertIn('id="tour-offer"', html)
        self.assertIn('from "./tour.js"', (JS_ROOT / "main.js").read_text(encoding="utf-8"))
        self.assertIn('data-tour="guided"', (JS_ROOT / "screens" / "settings.js").read_text(encoding="utf-8"))
        css = (FRONTEND / "styles.css").read_text(encoding="utf-8")
        for needle in (".tour-bubble", ".tour-spot", ".tour-arrow"):
            self.assertIn(needle, css)


class FundTanksUi(unittest.TestCase):
    """Fund tanks: a List | Tanks toggle on Today, readable numbers under each column, honest motion."""

    def js(self, name):
        return (JS_ROOT / name).read_text(encoding="utf-8")

    def css(self):
        return (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_toggle_on_today_list_stays_default(self):
        today = self.js("screens/today.js")
        self.assertIn('data-fund-view="list"', today)
        self.assertIn('data-fund-view="tanks"', today)
        self.assertIn("aria-pressed", today)
        self.assertIn('id="funds-card"', today)
        self.assertIn('<ul class="funds">', today)  # the list view is still there
        store = self.js("store.js")
        self.assertIn('fundView: readFundView()', store)
        self.assertIn('return "list";', store)  # default, and the fallback when storage throws

    def test_choice_is_stored_safely(self):
        store = self.js("store.js")
        for name in ("readFundView", "setFundView"):
            body = re.search(rf"export function {name}\(.*?\) \{{(.*?)\n\}}", store, re.DOTALL)
            self.assertIsNotNone(body, name)
            self.assertIn("try {", body.group(1))
            self.assertIn("localStorage", body.group(1))
        self.assertIn("[data-fund-view]", self.js("render.js"))

    def test_numbers_stay_visible_and_labelled(self):
        tanks = self.js("screens/tanks.js")
        for needle in ('role="img"', "aria-label=", "tank-name", "tank-left", "tank-of", "tank-pct",
                       'data-count="tank-${', "data-level=", "data-allocation="):
            with self.subTest(needle=needle):
                self.assertIn(needle, tanks)
        self.assertIn("tanksHtml(", self.js("screens/today.js"))

    def test_tones_and_no_alert_on_fixed_bills(self):
        css = self.css()
        for tone in ("high", "mid", "low", "empty", "none", "neutral"):
            with self.subTest(tone=tone):
                self.assertIn(f".tank.tone-{tone}", css)
        self.assertNotRegex(css, r"\.tank\.tone-neutral[^{]*\{[^}]*var\(--red")

    def test_layout_and_touch_targets(self):
        css = self.css()
        self.assertRegex(css, r"\.tanks \{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)")
        self.assertRegex(css, r"\.seg button \{[^}]*min-height: 44px")

    def test_motion_hooks(self):
        motion = self.js("motion.js")
        for name in ("export function captureTanks(", "export function animateTanks(", "export function waterTransform("):
            with self.subTest(name=name):
                self.assertIn(name, motion)
        body = re.search(r"export function animateTanks\(root, flow\) \{(.*?)\n\}", motion, re.DOTALL)
        self.assertIsNotNone(body)
        self.assertIn("prefersReducedMotion()", body.group(1))
        self.assertIn("tankGen", body.group(1))  # a newer render cancels an older animation
        render = self.js("render.js")
        self.assertLess(render.index("captureTanks(root)"), render.index("root.innerHTML = screens"))
        self.assertIn("animateTanks(root, state.tankFlow)", render)
        actions = self.js("actions.js")
        self.assertEqual(actions.count("tankFlow: flowOf("), 2)  # direct save and confirmed reallocation
        css = self.css()
        self.assertIn("@keyframes wave", css)
        self.assertIn(".tank-drop", css)


class FundTanksTour(unittest.TestCase):
    """The tour finds the funds card in both views; auto-play shows the tanks and puts the choice back."""

    def test_steps(self):
        steps = {s["id"]: s for s in tour_steps()}
        ids = [s["id"] for s in tour_steps()]
        # The separate "funds" step was folded into "tanks" to keep auto-play under 130 s; the
        # tanks step now carries the fund rules.
        self.assertNotIn("funds", ids)
        self.assertEqual(ids.index("tanks"), ids.index("this-week") + 1)
        self.assertIn("Fixed Bills never pays", steps["tanks"]["body"])
        tanks = steps["tanks"]
        self.assertEqual(tanks["autoAction"], "showTanks")
        self.assertFalse(tanks["autoOnly"])
        self.assertEqual(tanks["autoTarget"], "#funds-card")
        self.assertEqual(steps["undo"]["autoTarget"], "#funds-card")  # the drain is in the spotlight
        self.assertIn("no bank", (tanks["body"]).lower())

    def test_autoplay_restores_the_view(self):
        tour = (JS_ROOT / "tour.js").read_text(encoding="utf-8")
        self.assertRegex(tour, r"async showTanks\(token\)")
        self.assertIn("fundView: state.fundView", tour)
        end = re.search(r"async function end\(reason, message\) \{(.*?)\n\}", tour, re.DOTALL)
        self.assertIsNotNone(end)
        self.assertLess(end.group(1).index("setFundView(t.fundView)"), end.group(1).index("resetDemo()"))


class BudgetEditor(unittest.TestCase):
    """The weekly budget: a total, each fund in % or HK$, a suggested split and soft minimums."""

    def setUp(self):
        self.budget = (JS_ROOT / "budget.js").read_text(encoding="utf-8")

    def test_percent_and_amount_inputs_are_linked(self):
        self.assertIn('data-pct="${id}"', self.budget)
        self.assertIn('data-budget="${id}"', self.budget)
        self.assertIn('id="week-total"', self.budget)

    def test_suggested_split_and_minimums_come_from_the_server(self):
        self.assertIn("state.data.split", self.budget)
        self.assertIn('id="use-suggested"', self.budget)
        self.assertIn("Below the suggested minimum", self.budget)

    def test_amounts_must_add_up_before_saving(self):
        self.assertIn("budgetMismatch", (JS_ROOT / "actions.js").read_text(encoding="utf-8"))
        self.assertIn('id="rest-to-savings"', self.budget)

    def test_fallback_split_matches_the_server(self):
        from ssust import money
        for name, table in (("FALLBACK_SPLIT", money.SUGGESTED_SPLIT), ("FALLBACK_MIN", money.MIN_SPLIT)):
            expected = "{ " + ", ".join(f"{fund}: {table[fund]}" for fund in money.FUNDS) + " }"
            self.assertIn(f"const {name} = {expected};", self.budget)


class PhoneFrame(unittest.TestCase):
    """Desktop: the app inside a generic phone frame with a status bar and a home screen."""

    def setUp(self):
        self.index = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.device = (JS_ROOT / "device.js").read_text(encoding="utf-8")
        self.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_frame_markup(self):
        for needle in ('id="device"', 'id="statusbar"', 'id="sb-time"', 'id="home"', 'id="home-bar"',
                       'data-open-app'):
            self.assertIn(needle, self.index)

    def test_only_on_wide_screens_and_remembered_safely(self):
        self.assertIn("(min-width: 901px)", self.device)
        store = (JS_ROOT / "store.js").read_text(encoding="utf-8")
        self.assertIn("ssust.phoneView", store)
        body = store[store.index("ssust.phoneView"):]
        self.assertIn("try {", body)
        self.assertIn("catch", body)

    def test_status_bar_shows_hong_kong_time(self):
        self.assertIn('timeZone: "Asia/Hong_Kong"', self.device)

    def test_map_is_resized_when_the_app_shows(self):
        self.assertIn("export function refreshMapSize", (JS_ROOT / "mapview.js").read_text(encoding="utf-8"))
        self.assertIn("refreshMapSize()", self.device)

    def test_settings_toggle(self):
        settings = (JS_ROOT / "screens" / "settings.js").read_text(encoding="utf-8")
        self.assertIn("data-phone-view", settings)
        self.assertIn("Phone view", settings)

    def test_generic_design_only(self):
        for text in (self.index, self.device, self.css):
            self.assertNotIn("", text)  # no vendor logo glyph
            self.assertNotIn("iphone", text.lower())

    def test_zoom_uses_motion_tokens(self):
        self.assertIn("app-zoom", self.css)


class ZeroStartAndSliders(unittest.TestCase):
    """Live starts at HK$0 (no suggested amounts); sliders beside the amount fields; total funds bar."""

    def setUp(self):
        self.budget = (JS_ROOT / "budget.js").read_text(encoding="utf-8")
        self.add = (JS_ROOT / "screens" / "add.js").read_text(encoding="utf-8")
        self.today = (JS_ROOT / "screens" / "today.js").read_text(encoding="utf-8")

    def test_live_starts_at_zero(self):
        start = self.budget[self.budget.index("function startValues"):]
        start = start[:start.index("\n}\n")]
        self.assertIn('state.data.mode === "demo"', start)
        self.assertIn("zeroAmounts()", start)

    def test_today_shows_zero_until_a_budget_is_saved(self):
        self.assertIn("function zeroHero", self.today)
        self.assertIn("zeroHero(view)", self.today)

    def test_budget_sliders(self):
        self.assertIn('type="range"', self.budget)
        self.assertIn('data-slider="${id}"', self.budget)
        self.assertIn('step="10"', self.budget)
        self.assertIn("aria-valuetext", self.budget)
        # Each fund slider goes from 0 to the weekly total (was 0 to max(HK$3,000, 2x the amount)).
        self.assertIn('max="${fundMax(total)}"', self.budget)

    def test_weekly_total_slider(self):
        self.assertIn('id="week-total-slider"', self.budget)
        self.assertIn("TOTAL_FLOOR = 500000", self.budget)

    def test_suggested_split_fills_only_once_a_total_is_typed(self):
        on_total = self.budget[self.budget.index("const onTotal"):]
        on_total = on_total[:on_total.index("\n  };\n")]
        self.assertIn("total > 0 && sum(amounts) === 0", on_total)
        self.assertIn("splitAmounts(total, splitOf().suggested)", on_total)

    def test_total_funds_bar(self):
        self.assertIn('id="stack-bar"', self.budget)
        self.assertIn("paintStack", self.budget)

    def test_add_slider_and_quick_chips(self):
        self.assertIn('type="range"', self.add)
        self.assertIn('id="amount-slider"', self.add)
        self.assertIn('step="1"', self.add)
        self.assertIn("aria-valuetext", self.add)
        for chip in (20, 35, 50, 80):
            self.assertIn(chip, [int(x) for x in re.findall(r"QUICK = \[([\d, ]+)\]", self.add)[0].split(",")])


class ProjectionCard(unittest.TestCase):
    def setUp(self):
        self.card = (JS_ROOT / "screens" / "projection.js").read_text(encoding="utf-8")

    def test_words_not_colour_alone(self):
        self.assertIn('<span class="pill status-${proj.status}">${proj.label}</span>', self.card)
        self.assertIn("Projection starts after 2 days of use", self.card)
        self.assertIn("From your last ${proj.window}", self.card)
        self.assertIn('role="img"', self.card)

    def test_lines(self):
        for cls in ("proj-real", "proj-ahead", "proj-pace"):
            self.assertIn(cls, self.card)

    def test_on_today_not_twice(self):
        # Declutter: the curve is on Today only; Week is "where the money went".
        self.assertIn("projectionCard(state.data.projection", (JS_ROOT / "screens" / "today.js").read_text(encoding="utf-8"))
        self.assertNotIn("projectionCard(", (JS_ROOT / "screens" / "week.js").read_text(encoding="utf-8"))


class ScanReceipt(unittest.TestCase):
    def setUp(self):
        self.ocr = (JS_ROOT / "ocr.js").read_text(encoding="utf-8")
        self.add = (JS_ROOT / "screens" / "add.js").read_text(encoding="utf-8")
        self.actions = (JS_ROOT / "actions.js").read_text(encoding="utf-8")

    def test_ocr_is_vendored_and_lazy(self):
        index = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("tesseract", index)  # loaded only when the button is used
        self.assertIn('"tesseract.min.js"', self.ocr)
        self.assertNotIn("http", self.ocr.replace("import.meta.url", ""))
        for name in ("tesseract.min.js", "worker.min.js", "core/tesseract-core-simd-lstm.wasm.js",
                     "lang/eng.traineddata.gz", "LICENSE", "core/LICENSE"):
            self.assertTrue((FRONTEND / "vendor" / "tesseract" / name).is_file(), name)

    def test_button_and_messages(self):
        self.assertIn('accept="image/*"', self.add)
        self.assertIn("Scan receipt", self.add)
        self.assertIn("Read from receipt: check it", self.add)
        self.assertIn("Could not read a total, type it in.", self.add)

    def test_borders_cut_and_more_passes_only_when_needed(self):
        # A screenshot or a photo with black (or white) bars lost the price column and the total: uniform
        # near-black or near-white borders are cut. Pass 1 is the old pipeline; more passes run only
        # without a sure total, within a time budget: the right-hand price column with a digits whitelist,
        # the plain picture as one block, sparse text, then the picture turned 90 degrees.
        self.assertIn("receiptRegion(picture, width, height)", self.ocr)
        self.assertIn("const LIGHT = ", self.ocr)
        self.assertIn("const FLAT = ", self.ocr)
        self.assertIn('read(images.stretched, "4")', self.ocr)
        self.assertIn("if (rank(best.result) === 2) return best;", self.ocr)
        self.assertIn("const RIGHT_SHARE = 0.45;", self.ocr)
        self.assertIn('const DIGITS = "0123456789.,$-HK";', self.ocr)
        self.assertIn('tessedit_char_whitelist: DIGITS', self.ocr)
        self.assertIn('read(images.plain, "6")', self.ocr)
        self.assertIn('"11"', self.ocr)  # sparse text
        self.assertIn("turn(images.stretched, 90)", self.ocr)
        self.assertIn("turn(images.stretched, 270)", self.ocr)
        self.assertIn("const BUDGET_MS = 10000;", self.ocr)
        self.assertIn('import { mergeWords, rebuildRows, shiftWords, skewOf } from "./rows.js";', self.ocr)
        widget = (JS_ROOT / "widget.js").read_text(encoding="utf-8")
        for source in (self.actions, widget):
            self.assertIn('readTotal(file, (text) => api("/api/receipt/parse", { text })', source)

    def test_row_rebuild_is_a_pure_module(self):
        # Words from several passes are put back on their visual rows ("Amount" + "$1,032.0"), so the
        # same function can serve a native scanner later: no DOM, no globals, no imports.
        rows = (JS_ROOT / "rows.js").read_text(encoding="utf-8")
        for name in ("export function rebuildRows(", "export function mergeWords(", "export function skewOf(",
                     "export function shiftWords("):
            self.assertIn(name, rows)
        for word in ("document", "window", "import ", "fetch(", "Tesseract"):
            self.assertNotIn(word, rows)

    def test_no_prices_read_asks_for_a_new_photo(self):
        # The server answers reason "no_amounts" when fewer than 2 prices were read: no guess, a retake hint,
        # and "What the reader saw" stays under it (Add payment) so the failed photo can be checked.
        fmt = (JS_ROOT / "format.js").read_text(encoding="utf-8")
        self.assertIn('export const RETAKE_HINT = "No prices were read. Retake the photo flat, from above, '
                      'no fingers, whole ticket in frame.";', fmt)
        widget = (JS_ROOT / "widget.js").read_text(encoding="utf-8")
        scan = self.actions[self.actions.index("export async function scanReceipt"):]
        self.assertIn('state.scan = { status: "none", text: read.slice(0, 800), reason: result.reason || "" };', scan)
        self.assertIn('scan.reason === "no_amounts" ? RETAKE_HINT', self.add)
        self.assertIn("What the reader saw", self.add)
        self.assertIn('result.reason === "no_amounts" ? RETAKE_HINT', widget)

    def test_a_guess_never_claims_the_largest_price(self):
        # The best guess is no longer always the largest price (card line, subtotal, most frequent price).
        widget = (JS_ROOT / "widget.js").read_text(encoding="utf-8")
        for source in (self.add, widget):
            self.assertNotIn("largest price", source)
            self.assertIn("best guess, check it", source.lower())

    def test_never_saves_by_itself(self):
        scan = self.actions[self.actions.index("export async function scanReceipt"):]
        scan = scan[:scan.index("\n}\n")]
        self.assertIn("/api/receipt/parse", scan)
        self.assertNotIn("/api/payments", scan)
        self.assertNotIn("onSave", scan)


class ConnectedPayments(unittest.TestCase):
    """Simulated taps: always labelled, never reading a bank, confirmed through the normal flow."""

    def setUp(self):
        self.inbox = (JS_ROOT / "inbox.js").read_text(encoding="utf-8")
        self.actions = (JS_ROOT / "actions.js").read_text(encoding="utf-8")

    def test_simulated_everywhere(self):
        # Declutter: one "Simulated" tag on the connected-payments card instead of one per row.
        self.assertIn("Nothing here reads your bank.", self.inbox)
        self.assertIn("Simulated: no card", self.inbox)
        # the connected card, the review card and the notification
        self.assertGreaterEqual(self.inbox.count('<span class="sim-tag">Simulated</span>'), 3)

    def test_sample_merchants_only(self):
        for merchant in re.findall(r'merchant: "([^"]+)"', self.inbox):
            self.assertTrue(merchant.startswith("Sample "), merchant)

    def test_confirm_goes_through_the_server_flow(self):
        self.assertIn('"/api/inbox/confirm"', self.actions)
        confirm = self.actions[self.actions.index("export async function confirmInbox"):]
        confirm = confirm[:confirm.index("\n}\n")]
        self.assertIn("data.needsConfirm", confirm)  # the overspend step, as in Add payment
        self.assertIn("inboxId: id", confirm)

    def test_review_card_on_today(self):
        self.assertIn("reviewCard()", (JS_ROOT / "screens" / "today.js").read_text(encoding="utf-8"))
        self.assertIn("To review (${items.length})", self.inbox)


class HomeWidgets(unittest.TestCase):
    def setUp(self):
        self.widgets = (JS_ROOT / "widgets.js").read_text(encoding="utf-8")

    def test_same_numbers_as_today(self):
        today = (JS_ROOT / "screens" / "today.js").read_text(encoding="utf-8")
        self.assertIn("Math.max(view.todayRemaining, 0)", self.widgets)
        self.assertIn("hk(Math.max(left, 0))", today)
        self.assertIn("data.view.fundsNow[fund]", self.widgets)
        self.assertIn("view.fundsNow[fund]", today)

    def test_small_and_medium_with_status_time_and_inbox(self):
        for needle in ('class="widget small"', 'class="widget medium"', "Updated ${", "to review", "proj.label"):
            self.assertIn(needle, self.widgets)

    def test_refreshed_after_every_render_and_open_the_review(self):
        render = (JS_ROOT / "render.js").read_text(encoding="utf-8")
        self.assertIn("renderHome();", render)
        self.assertIn('review ? "review" : "today"', self.widgets)
        self.assertIn('"ssust:new-day"', (JS_ROOT / "device.js").read_text(encoding="utf-8"))


class CloseControls(unittest.TestCase):
    """Every close control goes through one delegated handler (closers.js), so a button re-drawn by a
    render can never lose its handler; Escape closes the top overlay from anywhere; a tap on a sheet's
    backdrop closes it."""

    def setUp(self):
        self.closers = (JS_ROOT / "closers.js").read_text(encoding="utf-8")
        self.js = {p.name: p.read_text(encoding="utf-8") for p in JS_ROOT.rglob("*.js")}

    def test_one_delegated_handler_on_the_document(self):
        self.assertIn('document.addEventListener("click"', self.closers)
        self.assertIn('closest("[data-close]")', self.closers)
        self.assertIn('document.addEventListener("keydown"', self.closers)
        self.assertIn('"Escape"', self.closers)
        self.assertIn("export function registerOverlay", self.closers)

    def test_close_controls_use_data_close(self):
        for name, marker in (("add.js", 'id="cancel-add" data-close="add"'), ("sheet.js", 'id="dismiss" data-close="sheet"'),
                             ("widget.js", 'data-close="camera"'), ("widget.js", 'data-close="quick"'),
                             ("notifications.js", 'data-close="notify"')):
            with self.subTest(file=name, marker=marker):
                self.assertIn(marker, self.js[name])

    def test_no_per_button_close_listeners_left(self):
        for name, text in self.js.items():
            with self.subTest(file=name):
                self.assertNotRegex(text, r'getElementById\("(cancel-add|dismiss)"\)\?\.addEventListener')
                self.assertNotIn("[data-w-close]", text)

    def test_every_overlay_is_registered(self):
        registered = set(re.findall(r'registerOverlay\(\{\s*name: "(\w+)"', "".join(self.js.values())))
        self.assertLessEqual({"add", "sheet", "camera", "quick", "notify"}, registered)

    def test_backdrop_tap_closes_a_sheet(self):
        self.assertIn("backdrop", self.closers)

    def test_unchanged_html_is_not_redrawn(self):
        # Re-drawing the home screen on every clock tick replaced buttons under the pointer.
        self.assertIn("export function setHtml", self.closers)
        self.assertIn("setHtml(", self.js["device.js"])
        self.assertIn("setHtml(", self.js["widget.js"])


class HomePager(unittest.TestCase):
    """The simulated home screen is a horizontal pager (like a phone): pages side by side with
    scroll-snap on x, no vertical scroll on the home screen itself, swipe / mouse drag / arrow keys /
    page dots, widgets on page 1 and apps on page 2, the SSUST icon in a dock on every page."""

    def setUp(self):
        self.index = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.device = (JS_ROOT / "device.js").read_text(encoding="utf-8")
        self.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_two_pages_and_dots(self):
        self.assertIn('id="home-pager"', self.index)
        self.assertEqual(self.index.count('class="home-page"'), 2)
        pages = self.index[self.index.index('id="home-pager"'):self.index.index('id="home-dots"')]
        first, second = pages.split('class="home-page"')[1:3]
        self.assertIn('id="home-widgets"', first)
        self.assertIn('id="home-quick"', first)
        self.assertIn('class="home-grid"', second)
        self.assertIn('id="home-dots"', self.index)
        dock = self.index[self.index.index('class="home-dock"'):]
        self.assertIn('id="ssust-icon"', dock[:dock.index("</div>")])

    def test_snap_on_x_and_no_vertical_scroll(self):
        self.assertIn("scroll-snap-type: x mandatory", self.css)
        home = self.css[self.css.index("body.phone-view .home {"):]
        home = home[:home.index("}")]
        self.assertIn("overflow: hidden", home)
        self.assertNotIn("overflow: auto", home)

    def test_swipe_drag_keys_and_dots(self):
        for needle in ("export function goToPage", '"pointerdown"', '"pointermove"', '"pointerup"',
                       '"ArrowLeft"', '"ArrowRight"', "data-page-dot", "scrollTo("):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.device)

    def test_a_drag_never_opens_what_is_under_it(self):
        self.assertIn("dragged", self.device)
        self.assertIn('addEventListener("click"', self.device)


class Notifications(unittest.TestCase):
    """Simulated in-phone notifications: a banner from the top (about 4 s, X, swipe up, tap opens the
    screen), a notification centre (status bar tap or swipe down, Clear all), an unread badge on the
    app icon, and five deterministic triggers the auto-play can also fire by name."""

    def setUp(self):
        self.js = (JS_ROOT / "notifications.js").read_text(encoding="utf-8")
        self.index = (FRONTEND / "index.html").read_text(encoding="utf-8")
        self.inbox = (JS_ROOT / "inbox.js").read_text(encoding="utf-8")

    def test_banner(self):
        self.assertIn("BANNER_MS = 4000", self.js)
        self.assertIn('data-close="notify"', self.js)
        self.assertIn("data-note-open", self.js)
        self.assertIn("swipe", self.js.lower())
        self.assertIn('registerOverlay({ name: "notify"', self.js)

    def test_centre(self):
        self.assertIn('id="notify-center"', self.index)
        for needle in ("Clear all", 'data-close="center"', 'registerOverlay({ name: "center"', '"statusbar"'):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.js)

    def test_badge_on_the_app_icon(self):
        self.assertIn("app-badge", self.js)
        self.assertIn('"ssust-icon"', self.js)

    def test_five_triggers(self):
        kinds = re.findall(r'^  (\w+)\(data', self.js[self.js.index("const RULES"):], re.M)
        self.assertEqual(set(kinds), {"payment", "fundEmpty", "tooFast", "weekClosed", "daily"})
        self.assertIn("export function fire(", self.js)
        self.assertIn("export function setAutoNotify(", self.js)

    def test_payment_banner_is_simulated_and_opens_the_review(self):
        self.assertIn('<span class="sim-tag">Simulated</span>', self.inbox)
        self.assertIn('review: true', self.inbox)


class CookedCard(unittest.TestCase):
    """Today: the Cooked gauge (score + label, colours of the projection), its three factors behind a
    tap, and the zero point marked on the Next 30 days curve."""

    def setUp(self):
        self.card = (JS_ROOT / "screens" / "cooked.js").read_text(encoding="utf-8")
        self.proj = (JS_ROOT / "screens" / "projection.js").read_text(encoding="utf-8")
        self.today = (JS_ROOT / "screens" / "today.js").read_text(encoding="utf-8")
        self.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_on_today_above_the_curve(self):
        self.assertLess(self.today.index("cookedCard("), self.today.index("projectionCard("))

    def test_gauge_with_score_and_label_in_words(self):
        for needle in ('class="cooked-gauge', "c.score", "c.label", 'aria-expanded="${open}"', "data-cooked-toggle",
                       "f.points", "f.max", "f.detail", "not AI"):
            with self.subTest(needle=needle):
                self.assertIn(needle, self.card)

    def test_five_levels_have_colours(self):
        for level in ("chill", "fine", "sweating", "cooked", "well_done"):
            with self.subTest(level=level):
                self.assertIn(f".level-{level}", self.css)

    def test_zero_point_on_the_curve(self):
        self.assertIn("proj-zero", self.proj)
        self.assertIn("HK$0 around ${dayLabel(zero.date)}", self.proj)


class DemoTimeline(unittest.TestCase):
    """The auto-play is one timeline with exact timestamps, exactly 2:00, its actions exist in
    tour.js, it is driven by one clock, and docs/DEMO_SCRIPT.md is generated from it."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("demo_script", FRONTEND.parent / "tools" / "demo_script.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)
        cls.timeline = cls.tool.load_timeline()
        cls.tour = (JS_ROOT / "tour.js").read_text(encoding="utf-8")

    def test_no_problems_and_at_most_2_00(self):
        self.assertEqual(self.tool.problems(self.timeline), [])
        total = self.timeline[-1]["end"]
        print(f"\nAuto-play timeline total: {self.tool.clock(total)} ({total} s)")
        self.assertLessEqual(total, 120)

    def test_total_is_exactly_two_minutes(self):
        self.assertEqual(self.timeline[-1]["end"], 120)
        self.assertEqual(self.tool.MAX_SECONDS, 120)
        self.assertIn("total 2:00", (JS_ROOT / "demo-timeline.js").read_text(encoding="utf-8"))

    def test_the_ten_scripted_steps(self):
        starts = [self.tool.clock(s["start"]) for s in self.timeline]
        self.assertEqual(starts, ["0:00", "0:10", "0:22", "0:33", "0:43", "0:57", "1:11", "1:25", "1:41", "1:52"])
        for step in self.timeline:
            with self.subTest(step=step["id"]):
                self.assertTrue(step["caption"].strip() and step["narration"].strip() and step["title"].strip())
                self.assertNotIn("—", step["caption"] + step["narration"])

    def test_every_action_exists(self):
        actions = re.search(r"const TIMELINE_ACTIONS = \{(.*?)\n\};", self.tour, re.DOTALL)
        self.assertIsNotNone(actions)
        for step in self.timeline:
            for action in step["actions"] + step["setup"]:
                with self.subTest(step=step["id"], action=action["do"]):
                    self.assertRegex(actions.group(1), rf"\basync {re.escape(action['do'])}\(")

    def test_one_clock_no_timeout_chain(self):
        tick = self.tour[self.tour.index("function tick()"):]
        tick = tick[:tick.index("\n}\n")]
        self.assertIn("requestAnimationFrame(tick)", tick)
        self.assertNotIn("setTimeout", tick)
        self.assertIn("performance.now() - tour.t0", self.tour)
        self.assertIn('get("timer") !== "0"', self.tour)
        for needle in ('id="tour-restart"', "function seek(", "step.setup", "resetDemo()"):
            self.assertIn(needle, self.tour)

    def test_honest_outro(self):
        outro = self.timeline[-1]["caption"]
        for words in ("Simulated: connected payments", "offline rules", "No bank connection"):
            self.assertIn(words, outro)

    def test_demo_script_is_generated_from_the_timeline(self):
        script = (FRONTEND.parent / "docs" / "DEMO_SCRIPT.md").read_text(encoding="utf-8")
        self.assertEqual(script.replace("\r\n", "\n"), self.tool.markdown(self.timeline))
        self.assertIn("## Record mode", script)
        self.assertIn("?record=1", script)


class RecordMode(unittest.TestCase):
    """The demo video: ?record=1 shows a pointer that glides and clicks, captions only."""

    @classmethod
    def setUpClass(cls):
        cls.cursor = (JS_ROOT / "cursor.js").read_text(encoding="utf-8")
        cls.tour = (JS_ROOT / "tour.js").read_text(encoding="utf-8")
        cls.main = (JS_ROOT / "main.js").read_text(encoding="utf-8")
        cls.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_cursor_module_is_imported(self):
        self.assertTrue((JS_ROOT / "cursor.js").is_file())
        self.assertIn("./cursor.js", imports_of(JS_ROOT / "tour.js"))
        self.assertIn("./cursor.js", imports_of(JS_ROOT / "main.js"))
        for name in ("recordMode", "cursorWanted", "showCursor", "hideCursor", "cursorOn", "aimAt", "moveTo",
                     "follow", "press", "clickEffect", "showRecordHint"):
            with self.subTest(name=name):
                self.assertRegex(self.cursor, rf"export (async )?function {name}\(")

    def test_url_params(self):
        self.assertIn('param("record")', self.cursor)
        self.assertIn('param("cursor")', self.cursor)
        self.assertIn('get(name) === "1"', self.cursor)
        self.assertIn("aria-hidden", self.cursor)

    def test_pointer_never_moves_while_seeking(self):
        pointing = re.search(r"function pointing\(\) \{(.*?)\n\}", self.tour, re.DOTALL)
        self.assertIsNotNone(pointing)
        self.assertIn("!tour.seeking", pointing.group(1))
        self.assertIn("cursorOn()", pointing.group(1))

    def test_actions_press_the_real_controls(self):
        self.assertIn("async function pressEl(target, token)", self.tour)
        self.assertIn("async function typeText(input, text, token)", self.tour)
        press = re.search(r"async function pressEl\(target, token\) \{(.*?)\n\}", self.tour, re.DOTALL).group(1)
        self.assertIn("target.click()", press)
        actions = re.search(r"const TIMELINE_ACTIONS = \{(.*?)\n\};", self.tour, re.DOTALL).group(1)
        # addPayment (setup only) stays programmatic; every other timeline click goes through pressEl.
        actions = re.sub(r"async addPayment\(.*?\n  \},", "", actions, flags=re.DOTALL)
        self.assertNotIn(".click()", actions)
        self.assertIn("showCursor(", self.tour)
        self.assertIn("hideCursor()", self.tour)

    def test_record_mode_is_clean(self):
        self.assertIn('"is-record"', self.tour)
        self.assertIn('classList.add("record-mode")', self.main)
        record = self.main[self.main.index("if (recordMode())"):]
        self.assertLess(record.index("return;"), record.index("maybeOfferTour()"), "no welcome tip in record mode")
        for needle in (".tour.is-record .tour-head", ".tour.is-record .tour-actions", "body.record-mode .desk-side",
                       ".ghost-cursor", ".record-hint"):
            with self.subTest(css=needle):
                self.assertIn(needle, self.css)


class CameraPreview(unittest.TestCase):
    """The camera shows what it reads: the scanned image in the viewfinder, readable samples,
    and the last picked photo on the gallery button."""

    @classmethod
    def setUpClass(cls):
        cls.widget = (JS_ROOT / "widget.js").read_text(encoding="utf-8")
        cls.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_viewfinder_shows_the_scanned_image(self):
        finder = self.widget[self.widget.index("function finderHtml()"):]
        finder = finder[:finder.index("\n}\n")]
        # a sample: an <img> of that file; a picked photo: drawn on a canvas
        self.assertIn('<img class="lk-shot" src="${escapeHtml(shot.src)}"', finder)
        self.assertIn('data-w-canvas="shot"', finder)
        self.assertIn('id="lk-status"', finder, "the reading progress sits on the image")
        self.assertIn("`img/samples/${file}`);", self.widget, "a sample passes its path to readImage")
        self.assertIn('w.shot = { kind: "sample", src: sample }', self.widget)

    def test_picked_photo_needs_no_blob_url(self):
        # The CSP's img-src is 'self' only: a bitmap on a canvas, one kept, the old one closed.
        self.assertNotIn("createObjectURL", self.widget)
        self.assertIn("createImageBitmap(file)", self.widget)
        self.assertIn("if (picked) picked.close();", self.widget)
        self.assertIn('data-w-canvas="thumb"', self.widget)
        self.assertIn("drawPicked(root)", self.widget)

    def test_sample_thumbnails_show_the_whole_receipt(self):
        rule = re.search(r"\.lk-sample img \{([^}]*)\}\s*\n\.lk-sample span", self.css)
        self.assertIsNotNone(rule)
        self.assertIn("object-fit: contain", rule.group(1))
        self.assertIn("height: 80px", rule.group(1))
        self.assertIn("-webkit-line-clamp: 2", self.css)
        self.assertIn(".lk-shot", self.css)

    def test_zoom_never_starts_from_the_corner(self):
        device = (JS_ROOT / "device.js").read_text(encoding="utf-8")
        self.assertIn("box.width / 2", device)
        self.assertIn('querySelector("[data-w-check]")?.getBoundingClientRect()', self.widget)


class Declutter(unittest.TestCase):
    """Secondary details are one tap away, and the demo still reaches them with real clicks."""

    def test_sources_folded_and_opened_by_the_demo(self):
        screen = (JS_ROOT / "screens" / "map.js").read_text(encoding="utf-8")
        self.assertIn('<details class="place-src-box"><summary>Source</summary>', screen)
        timeline = (JS_ROOT / "demo-timeline.js").read_text(encoding="utf-8")
        for kind in ("range_fits", "chain_fits"):
            self.assertIn(f'"do": "click", "selector": "#screen .place.status-{kind} + .place-src-box summary"', timeline)

    def test_source_box_comes_right_after_its_row(self):
        # The demo's "+ .place-src-box" selector needs the folded source to be the row's next sibling,
        # so the "Log a meal here" button goes after it, not between them.
        screen = (JS_ROOT / "screens" / "map.js").read_text(encoding="utf-8")
        self.assertIn("</button>${source}${log}`", screen)

    def test_hook_points_at_the_amount(self):
        self.assertIn('"aim": ".hero .big"', (JS_ROOT / "demo-timeline.js").read_text(encoding="utf-8"))
        self.assertIn("a.aim ? document.querySelector(a.aim)", (JS_ROOT / "tour.js").read_text(encoding="utf-8"))

    def test_settings_budget_and_mode_first(self):
        settings = (JS_ROOT / "screens" / "settings.js").read_text(encoding="utf-8")
        tail = settings[settings.rindex("return `"):]
        order = [tail.index(x) for x in ("${budgetCard}", "${modeCard}", "${connectedCard()}", "${display}", "${help}")]
        self.assertEqual(order, sorted(order))
        self.assertIn('<details class="card fold" id="connected-card">', (JS_ROOT / "inbox.js").read_text(encoding="utf-8"))
