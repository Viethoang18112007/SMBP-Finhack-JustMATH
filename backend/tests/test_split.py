"""The weekly budget sliders: one fund moves, the others follow proportionally, the sum stays exact.

split.py is the reference; frontend/js/split.js must give the same answers (checked with node
when it is installed, else skipped).
"""

import itertools
import json
import random
import shutil
import subprocess
import unittest
from pathlib import Path

from ssust import split
from ssust.money import FUNDS
from ssust.server import FRONTEND

SPLIT_JS = FRONTEND / "js" / "split.js"


def amounts(*values):
    return dict(zip(FUNDS, values))


class Distribute(unittest.TestCase):
    def test_exact_sum_and_largest_remainder(self):
        # 100 cents over three equal weights: 34, 33, 33 (the first fund in FUNDS order wins the tie).
        self.assertEqual(split.distribute(100, {"main": 1, "snack": 1, "fixed": 1}), {"main": 34, "snack": 33, "fixed": 33})

    def test_proportional(self):
        self.assertEqual(split.distribute(1000, {"main": 3, "snack": 1}), {"main": 750, "snack": 250})

    def test_zero_weights_split_equally(self):
        self.assertEqual(split.distribute(1, {"snack": 0, "fixed": 0, "experience": 0}),
                         {"snack": 1, "fixed": 0, "experience": 0})

    def test_nothing_to_share(self):
        self.assertEqual(split.distribute(0, {"main": 5, "snack": 0}), {"main": 0, "snack": 0})
        self.assertEqual(split.distribute(10, {}), {})

    def test_refuses_floats_and_negatives(self):
        for bad in (1.5, -1, True, "10"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                split.distribute(bad, {"main": 1})
        with self.assertRaises(ValueError):
            split.distribute(10, {"main": -1})


class Rebalance(unittest.TestCase):
    TOTAL = 150000
    START = amounts(60000, 7500, 22500, 15000, 15000, 30000)  # 40/5/15/10/10/20

    def check(self, result, total=TOTAL):
        self.assertEqual(sum(result.values()), total)
        self.assertEqual(set(result), set(FUNDS))
        for fund, cents in result.items():
            self.assertIsInstance(cents, int, fund)
            self.assertGreaterEqual(cents, 0, fund)

    def test_increase_takes_from_the_others_proportionally(self):
        result = split.rebalance(self.START, "main", 90000, self.TOTAL)
        self.check(result)
        self.assertEqual(result["main"], 90000)
        # The others held 90000 and now hold 60000: each keeps 2/3 of what it had.
        self.assertEqual(result, amounts(90000, 5000, 15000, 10000, 10000, 20000))

    def test_decrease_gives_to_the_others_proportionally(self):
        result = split.rebalance(self.START, "main", 30000, self.TOTAL)
        self.check(result)
        # The others held 90000 and now hold 120000: each gets 4/3 of what it had.
        self.assertEqual(result, amounts(30000, 10000, 30000, 20000, 20000, 40000))

    def test_ratios_between_the_others_are_kept(self):
        result = split.rebalance(self.START, "snack", 20000, self.TOTAL)
        self.check(result)
        self.assertEqual(result["snack"], 20000)
        # Main was 4x Experience and Fixed Bills 3/4 of Savings: still so, to the cent.
        self.assertLessEqual(abs(result["main"] - 4 * result["experience"]), 4)
        self.assertLessEqual(abs(4 * result["fixed"] - 3 * result["savings"]), 4)

    def test_clamped_to_zero_and_the_total(self):
        self.check(split.rebalance(self.START, "main", -500, self.TOTAL))
        self.assertEqual(split.rebalance(self.START, "main", -500, self.TOTAL)["main"], 0)
        top = split.rebalance(self.START, "main", 10 ** 9, self.TOTAL)
        self.check(top)
        self.assertEqual(top, amounts(self.TOTAL, 0, 0, 0, 0, 0))

    def test_from_the_grab_amounts_the_split_comes_back(self):
        top = split.rebalance(self.START, "main", self.TOTAL, self.TOTAL)
        self.assertEqual(top, amounts(self.TOTAL, 0, 0, 0, 0, 0))
        # Computed from the amounts at grab time (not from `top`), the old split returns exactly.
        self.assertEqual(split.rebalance(self.START, "main", 60000, self.TOTAL), self.START)

    def test_others_at_zero_share_equally_when_money_comes_back(self):
        start = amounts(self.TOTAL, 0, 0, 0, 0, 0)
        result = split.rebalance(start, "main", self.TOTAL - 1, self.TOTAL)
        self.check(result)
        self.assertEqual(result, amounts(self.TOTAL - 1, 1, 0, 0, 0, 0))
        result = split.rebalance(start, "main", self.TOTAL - 5, self.TOTAL)
        self.assertEqual(result, amounts(self.TOTAL - 5, 1, 1, 1, 1, 1))

    def test_three_funds_at_zero_one_cent(self):
        start = amounts(1, 0, 0, 0, 1, 1)
        result = split.rebalance(start, "main", 0, 3)
        self.check(result, 3)
        self.assertEqual(result, amounts(0, 0, 0, 0, 2, 1))

    def test_floors_are_never_crossed(self):
        floors = {"snack": 7000, "fixed": 22500}
        result = split.rebalance(self.START, "main", 140000, self.TOTAL, floors=floors)
        self.check(result)
        self.assertGreaterEqual(result["snack"], 7000)
        self.assertGreaterEqual(result["fixed"], 22500)
        # Main can only take what is above the others' floors.
        self.assertEqual(result["main"], self.TOTAL - 7000 - 22500)

    def test_the_moved_fund_keeps_its_own_floor(self):
        result = split.rebalance(self.START, "main", 0, self.TOTAL, floors={"main": 12000})
        self.check(result)
        self.assertEqual(result["main"], 12000)

    def test_locked_funds_stay(self):
        result = split.rebalance(self.START, "main", 90000, self.TOTAL, locked={"savings"})
        self.check(result)
        self.assertEqual(result["savings"], 30000)
        self.assertEqual(result["main"], 90000)

    def test_everything_else_locked_means_no_move(self):
        others = set(FUNDS) - {"main"}
        result = split.rebalance(self.START, "main", 90000, self.TOTAL, locked=others)
        self.assertEqual(result, self.START)

    def test_unbalanced_input_comes_out_balanced(self):
        start = amounts(100, 0, 0, 0, 0, 0)  # sums to 100, total is 1000
        result = split.rebalance(start, "main", 400, 1000)
        self.check(result, 1000)
        self.assertEqual(result["main"], 400)

    def test_zero_total(self):
        self.assertEqual(split.rebalance(amounts(0, 0, 0, 0, 0, 0), "main", 500, 0), amounts(0, 0, 0, 0, 0, 0))

    def test_order_independence(self):
        for order in itertools.islice(itertools.permutations(FUNDS), 0, 720, 37):
            shuffled = {fund: self.START[fund] for fund in order}
            self.assertEqual(split.rebalance(shuffled, "experience", 41234, self.TOTAL),
                             split.rebalance(self.START, "experience", 41234, self.TOTAL))

    def test_random_moves_keep_every_rule(self):
        rng = random.Random(7)
        for _ in range(500):
            total = rng.choice([0, 1, 3, 7, 100, 99999, 150000, 2_000_00])
            start = split.distribute(total, {fund: rng.randint(0, 5) for fund in FUNDS})
            fund = rng.choice(FUNDS)
            target = rng.randint(-100, total + 100)
            locked = {f for f in FUNDS if f != fund and rng.random() < 0.2}
            result = split.rebalance(start, fund, target, total, locked=locked)
            self.check(result, total)
            for f in locked:
                self.assertEqual(result[f], start[f])

    def test_refuses_unknown_fund_and_floats(self):
        with self.assertRaises(ValueError):
            split.rebalance(self.START, "rent", 10, self.TOTAL)
        with self.assertRaises(ValueError):
            split.rebalance(self.START, "main", 10.5, self.TOTAL)
        with self.assertRaises(ValueError):
            split.rebalance({**self.START, "main": 1.5}, "main", 10, self.TOTAL)


class FitTotal(unittest.TestCase):
    """Never more than 100%: funds above the total shrink in proportion, to the cent."""

    def test_shrinks_in_proportion(self):
        start = amounts(80000, 10000, 30000, 20000, 20000, 40000)  # 200000, the total is now 150000
        result = split.fit_total(start, 150000)
        self.assertEqual(result, amounts(60000, 7500, 22500, 15000, 15000, 30000))

    def test_locked_funds_stay_when_they_fit(self):
        start = amounts(80000, 10000, 30000, 20000, 20000, 40000)
        result = split.fit_total(start, 150000, locked={"savings"})
        self.assertEqual(result["savings"], 40000)
        self.assertEqual(sum(result.values()), 150000)
        too_big = split.fit_total(start, 30000, locked={"savings"})  # the lock alone is over the total
        self.assertEqual(sum(too_big.values()), 30000)

    def test_rounding_and_zero(self):
        self.assertEqual(sum(split.fit_total(amounts(1, 1, 1, 0, 0, 0), 2).values()), 2)
        self.assertEqual(split.fit_total(amounts(5, 0, 0, 0, 0, 0), 0), amounts(0, 0, 0, 0, 0, 0))

    def test_random(self):
        rng = random.Random(5)
        for _ in range(300):
            start = {f: rng.randint(0, 50000) for f in FUNDS}
            total = rng.randint(0, 300000)
            locked = {f for f in FUNDS if rng.random() < 0.2}
            result = split.fit_total(start, total, locked=locked)
            self.assertEqual(sum(result.values()), total)
            self.assertTrue(all(type(v) is int and v >= 0 for v in result.values()))


class Percents(unittest.TestCase):
    def test_whole_percents_always_sum_to_100(self):
        rng = random.Random(3)
        for _ in range(300):
            total = rng.randint(1, 500000)
            values = split.distribute(total, {fund: rng.randint(0, 9) for fund in FUNDS})
            pcts = split.percents(values, total)
            self.assertEqual(sum(pcts.values()), 100)
            self.assertTrue(all(isinstance(p, int) and p >= 0 for p in pcts.values()))

    def test_zero_total(self):
        self.assertEqual(sum(split.percents(amounts(0, 0, 0, 0, 0, 0), 0).values()), 0)

    def test_tenths_sum_to_one_thousand(self):
        # A third each: 33.4 + 33.3 + 33.3, never 99.9 or 100.1.
        tenths = split.percents(amounts(100, 100, 100, 0, 0, 0), 300, scale=1000)
        self.assertEqual(tenths, amounts(334, 333, 333, 0, 0, 0))

    def test_exact_split(self):
        self.assertEqual(split.percents(amounts(60000, 7500, 22500, 15000, 15000, 30000), 150000),
                         amounts(40, 5, 15, 10, 10, 20))


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class SameAnswersInTheBrowser(unittest.TestCase):
    """frontend/js/split.js against split.py on the same cases."""

    def test_js_matches_python(self):
        rng = random.Random(11)
        cases = []
        for _ in range(300):
            total = rng.choice([0, 1, 3, 100, 12345, 150000])
            start = split.distribute(total, {fund: rng.randint(0, 4) for fund in FUNDS})
            fund = rng.choice(FUNDS)
            floors = {f: rng.randint(0, start[f]) for f in FUNDS if rng.random() < 0.3}
            locked = sorted(f for f in FUNDS if f != fund and rng.random() < 0.2)
            cases.append({"amounts": start, "fund": fund, "target": rng.randint(-50, total + 50), "total": total,
                          "floors": floors, "locked": locked})
        script = (
            "import { rebalance, percents, fitTotal } from " + json.dumps(SPLIT_JS.as_uri()) + ";\n"
            "let data = ''; process.stdin.on('data', (c) => data += c); process.stdin.on('end', () => {\n"
            "  const out = JSON.parse(data).map((c) => { const r = rebalance(c.amounts, c.fund, c.target, c.total,"
            " { floors: c.floors, locked: new Set(c.locked) }); return { r, p: percents(r, c.total),"
            " t: percents(r, c.total, 1000), f: fitTotal(c.amounts, c.total, { locked: new Set(c.locked) }) }; });\n"
            "  process.stdout.write(JSON.stringify(out)); });\n"
        )
        proc = subprocess.run(["node", "--input-type=module", "-e", script], input=json.dumps(cases),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        got = json.loads(proc.stdout)
        for case, answer in zip(cases, got):
            want = split.rebalance(case["amounts"], case["fund"], case["target"], case["total"],
                                   floors=case["floors"], locked=set(case["locked"]))
            self.assertEqual(answer["r"], want, case)
            self.assertEqual(answer["p"], split.percents(want, case["total"]), case)
            self.assertEqual(answer["t"], split.percents(want, case["total"], scale=1000), case)
            self.assertEqual(answer["f"], split.fit_total(case["amounts"], case["total"], locked=set(case["locked"])),
                             case)


class SliderUi(unittest.TestCase):
    """budget.js: the sliders use split.js, update on animation frames, and never call the server."""

    def setUp(self):
        self.budget = (FRONTEND / "js" / "budget.js").read_text(encoding="utf-8")
        self.css = (FRONTEND / "styles.css").read_text(encoding="utf-8")

    def test_uses_the_shared_rules(self):
        self.assertIn('from "./split.js"', self.budget)
        self.assertIn("rebalance(", self.budget)
        self.assertIn("percents(", self.budget)
        self.assertIn("fitTotal(", self.budget)
        # A drag starts from the amounts at grab time: up to the top and back restores the split.
        self.assertIn("dragBase", self.budget)
        self.assertIn("moveFund(slider.dataset.slider, Number(slider.value) * 100, null, dragBase)", self.budget)

    def test_one_dollar_steps_and_frames(self):
        self.assertIn('data-slider="${id}"', self.budget)
        row = self.budget[self.budget.index("function fundRow"):]
        row = row[:row.index("\n}\n")]
        self.assertIn('step="1"', row)
        self.assertIn("requestAnimationFrame", self.budget)

    def test_bubble_lock_and_touch(self):
        self.assertIn("data-bubble", self.budget)
        self.assertIn('data-lock="${id}"', self.budget)
        self.assertIn("aria-pressed", self.budget)
        self.assertRegex(self.css, r"\.slider\s*\{[^}]*touch-action:\s*pan-y")
        self.assertIn(".slider-bubble", self.css)

    def test_saved_on_release_only_and_never_sent_while_dragging(self):
        self.assertIn('"change"', self.budget)
        self.assertIn("saveDraft", self.budget)
        self.assertNotIn("api(", self.budget)
        self.assertNotIn("render()", self.budget)
