import unittest
from ssust.money import js_round, make_state, plan, snapshot
from ssust import money


def add(state, amount, category, choice=None):
    result = plan(state, amount, category)
    if result.get("saveNow"):
        taken = result["from"]
    else:
        taken = next(item["from"] for item in result["options"] if item["choice"] == choice)
    state["payments"].append({
        "id": "t",
        "date": state["today"],
        "amount": amount,
        "category": category,
        "note": "",
        "from": taken,
    })
    return result


class FiveFunds(unittest.TestCase):
    def test_wednesday_morning(self):
        view = snapshot(make_state("sample"))
        self.assertEqual(view["lifeAtStart"], 70000)
        self.assertEqual(view["allowance"], 14000)
        self.assertEqual(view["todayRemaining"], 14000)
        self.assertEqual(view["tomorrow"], 14000)
        self.assertEqual(view["daysLeft"], 5)
        self.assertEqual(view["fundsNow"]["main"], 66000)
        self.assertEqual(view["fundsNow"]["snack"], 4000)
        self.assertEqual(view["fundsNow"]["fixed"], 20000)
        self.assertEqual(view["fundsNow"]["experience"], 12000)
        self.assertEqual(view["fundsNow"]["development"], 8000)
        self.assertEqual(view["fundsNow"]["savings"], 50000)

    def test_main_meal_48_stays_inside_today(self):
        state = make_state("sample")
        result = add(state, 4800, "main")
        self.assertEqual(result["level"], 0)
        view = snapshot(state)
        self.assertEqual(view["todayRemaining"], 9200)
        self.assertEqual(view["lifeNow"], 65200)
        self.assertEqual(view["fundsNow"]["main"], 61200)
        self.assertEqual(view["fundsNow"]["snack"], 4000)
        self.assertEqual(view["tomorrow"], 14000)
        self.assertFalse(view["notice"])

    def test_100_can_use_snacks_or_experience(self):
        state = make_state("sample")
        add(state, 4800, "main")
        result = plan(state, 10000, "main")
        self.assertFalse(result["saveNow"])
        snack = next(item for item in result["options"] if item["choice"] == "snack")
        flex = next(item for item in result["options"] if item["choice"] == "flex")
        self.assertEqual(snack["hole"], 1)
        self.assertEqual(snack["from"]["snack"], 800)
        self.assertEqual(snack["tomorrowAfter"], 13800)
        self.assertEqual(snack["fundsAfter"]["snack"], 3200)
        self.assertEqual(flex["hole"], 2)
        self.assertEqual(flex["from"]["experience"], 800)
        self.assertEqual(flex["tomorrowAfter"], 14000)
        self.assertEqual(flex["fundsAfter"]["experience"], 11200)
        self.assertEqual(flex["fundsAfter"]["snack"], 4000)

    def test_70_is_the_quiet_notice(self):
        state = make_state("sample")
        add(state, 4800, "main")
        result = add(state, 7000, "main")
        self.assertTrue(result["saveNow"])
        self.assertEqual(result["level"], 1)
        view = snapshot(state)
        self.assertEqual(view["spentToday"], 11800)
        self.assertEqual(view["todayRemaining"], 2200)
        self.assertEqual(view["lifeNow"], 58200)
        self.assertEqual(view["tomorrow"], 14000)
        self.assertTrue(view["notice"])

    def test_experience_uses_development(self):
        state = make_state("sample")
        result = plan(state, 15000, "experience")
        self.assertEqual(result["level"], 2)
        option = result["options"][0]
        self.assertEqual(option["from"]["experience"], 12000)
        self.assertEqual(option["from"]["development"], 3000)
        self.assertEqual(option["fundsAfter"]["experience"], 0)
        self.assertEqual(option["fundsAfter"]["development"], 5000)
        self.assertEqual(option["tomorrowAfter"], 14000)

    def test_fixed_bill_uses_no_other_fund(self):
        state = make_state("sample")
        result = add(state, 5000, "fixed")
        self.assertEqual(result["level"], 0)
        view = snapshot(state)
        self.assertEqual(view["fundsNow"]["fixed"], 15000)
        self.assertEqual(view["todayRemaining"], 14000)
        self.assertEqual(view["fundsNow"]["savings"], 50000)

    def test_week_over_uses_long_term_savings(self):
        state = make_state("over")
        self.assertEqual(snapshot(state)["lifeAtStart"], 0)
        result = plan(state, 3000, "main")
        self.assertEqual(result["level"], 3)
        option = result["options"][0]
        self.assertEqual(option["from"]["savings"], 3000)
        self.assertEqual(option["fundsAfter"]["savings"], 47000)
        self.assertEqual(option["tomorrowAfter"], 0)


def custom_state(today="2026-11-11", **opening):
    funds = {"main": 10000, "snack": 2000, "fixed": 0, "experience": 1000, "development": 500, "savings": 50000}
    funds.update(opening)
    return {"mode": "sample", "weekStart": "2026-11-09", "today": today, "opening": funds, "payments": []}


class Characterization(unittest.TestCase):
    """M2: pin the current money rules. No logic changes."""

    def test_snack_payment_spills_into_main(self):
        result = plan(make_state("sample"), 5000, "snack")
        self.assertTrue(result["saveNow"])
        self.assertEqual(result["level"], 0)
        self.assertEqual(result["from"]["snack"], 4000)
        self.assertEqual(result["from"]["main"], 1000)

    def test_main_meal_spills_into_snack(self):
        result = plan(custom_state(main=0), 300, "main")
        self.assertTrue(result["saveNow"])
        self.assertEqual(result["from"]["main"], 0)
        self.assertEqual(result["from"]["snack"], 300)

    def test_full_ladder_snack_experience_development_savings(self):
        # Allowance 12000 / 5 = 2400. Excess 7600: neither snack nor flex alone covers it.
        state = custom_state()
        self.assertEqual(snapshot(state)["allowance"], 2400)
        result = plan(state, 10000, "main")
        self.assertFalse(result["saveNow"])
        self.assertEqual(result["level"], 3)
        self.assertEqual(len(result["options"]), 1)
        option = result["options"][0]
        self.assertEqual(option["choice"], "savings")
        self.assertEqual(option["from"], {"main": 2400, "snack": 2000, "fixed": 0,
                                          "experience": 1000, "development": 500, "savings": 4100})
        self.assertEqual(option["fundsAfter"]["savings"], 45900)

    def test_ladder_that_stops_before_savings_is_a_flex_cover(self):
        # Excess 3000: snack (2000) alone and flex (1500) alone fall short, together they cover it.
        result = plan(custom_state(), 5400, "main")
        self.assertEqual(result["level"], 2)
        option = result["options"][0]
        self.assertEqual(option["choice"], "flex")
        self.assertEqual(option["from"]["snack"], 2000)
        self.assertEqual(option["from"]["experience"], 1000)
        self.assertEqual(option["from"]["development"], 0)
        self.assertEqual(option["from"]["savings"], 0)

    def test_cannot_cover_food(self):
        state = custom_state()
        everything = 2400 + 2000 + 1000 + 500 + 50000
        self.assertEqual(plan(state, everything, "main")["options"][0]["from"]["savings"], 50000)
        self.assertEqual(plan(state, everything + 1, "main"), {"error": "The five funds cannot cover this."})

    def test_cannot_cover_experience(self):
        state = make_state("sample")
        self.assertEqual(plan(state, 12000 + 8000 + 50000, "experience")["level"], 3)
        self.assertEqual(plan(state, 12000 + 8000 + 50000 + 1, "experience"),
                         {"error": "The five funds cannot cover this."})

    def test_development_uses_experience_then_savings(self):
        option = plan(make_state("sample"), 25000, "development")["options"][0]
        self.assertEqual(option["choice"], "savings")
        self.assertEqual(option["from"]["development"], 8000)
        self.assertEqual(option["from"]["experience"], 12000)
        self.assertEqual(option["from"]["savings"], 5000)

    def test_fixed_bill_partly_covered(self):
        result = plan(make_state("sample"), 25000, "fixed")
        self.assertTrue(result["saveNow"])
        self.assertEqual(result["level"], 0)
        self.assertEqual(result["from"]["fixed"], 20000)
        self.assertEqual(result["uncovered"], 5000)
        self.assertEqual(sum(result["from"].values()), 20000)

    def test_fixed_bill_with_empty_fund_is_all_uncovered(self):
        result = plan(custom_state(fixed=0), 3000, "fixed")
        self.assertEqual(result["from"]["fixed"], 0)
        self.assertEqual(result["uncovered"], 3000)

    def test_last_day_of_the_week(self):
        view = snapshot({**make_state("sample"), "today": "2026-11-15"})
        self.assertEqual(view["daysLeft"], 1)
        self.assertEqual(view["daysAfter"], 0)
        self.assertEqual(view["allowance"], 70000)
        self.assertEqual(view["todayRemaining"], 70000)
        self.assertEqual(view["tomorrow"], 0)
        self.assertFalse(view["overToday"])

    def test_date_after_the_week_ends(self):
        state = {**make_state("sample"), "today": "2026-11-16"}
        view = snapshot(state)
        self.assertEqual(view["daysLeft"], 0)
        self.assertEqual(view["daysAfter"], 0)
        self.assertEqual(view["allowance"], 0)
        self.assertEqual(view["tomorrow"], 0)
        self.assertEqual(view["threshold"], 0)
        self.assertTrue(view["overToday"])
        self.assertFalse(view["notice"])
        result = plan(state, 1000, "main")
        self.assertEqual([item["choice"] for item in result["options"]], ["snack", "flex"])
        self.assertEqual(result["level"], 1)

    def test_notice_boundaries(self):
        # Allowance 14000, threshold js_round(14000 * 0.8) = 11200.
        state = make_state("sample")
        self.assertEqual(snapshot(state)["threshold"], 11200)
        self.assertEqual(plan(state, 11199, "main")["level"], 0)
        self.assertEqual(plan(state, 11200, "main")["level"], 1)
        at_allowance = plan(state, 14000, "main")
        self.assertTrue(at_allowance["saveNow"])
        self.assertEqual(at_allowance["level"], 1)
        self.assertFalse(plan(state, 14001, "main")["saveNow"])

    def test_notice_flag_at_exact_threshold_and_allowance(self):
        state = make_state("sample")
        add(state, 11200, "main")
        view = snapshot(state)
        self.assertTrue(view["notice"])
        self.assertFalse(view["overToday"])
        add(state, 2800, "main")
        view = snapshot(state)
        self.assertEqual(view["spentToday"], 14000)
        self.assertEqual(view["todayRemaining"], 0)
        self.assertTrue(view["notice"])
        self.assertFalse(view["overToday"])

    def test_spending_past_allowance_from_snacks_is_over_today(self):
        state = make_state("sample")
        add(state, 14001, "main", "snack")
        view = snapshot(state)
        self.assertTrue(view["overToday"])
        self.assertFalse(view["notice"])

    def test_not_ready(self):
        state = make_state("empty")
        view = snapshot(state)
        self.assertFalse(view["ready"])
        self.assertIsNone(view["allowance"])
        self.assertIsNone(view["todayRemaining"])
        for category in ("main", "snack", "fixed", "experience", "development"):
            with self.subTest(category=category):
                self.assertEqual(plan(state, 1000, category), {"error": "Set the five funds first."})

    def test_unknown_category(self):
        self.assertEqual(plan(make_state("sample"), 1000, "savings"), {"error": "Unknown category."})

    def test_allowance_rounds(self):
        # 10000 over 3 days (Fri to Sun) = 3333.33
        self.assertEqual(snapshot(custom_state(today="2026-11-13", snack=0))["allowance"], 3333)

    def test_js_round_halves(self):
        self.assertEqual(js_round(0.5), 1)
        self.assertEqual(js_round(1.5), 2)
        self.assertEqual(js_round(2.5), 3)
        self.assertEqual(js_round(2.4999), 2)
        self.assertEqual(js_round(0), 0)
        self.assertEqual(js_round(-0.4), 0)

    def test_js_round_negative_halves_match_javascript(self):
        # Finding M2-4 (fixed): Math.round rounds halves towards +infinity.
        self.assertEqual(js_round(-0.5), 0)
        self.assertEqual(js_round(-1.5), -1)
        self.assertEqual(js_round(-2.5), -2)
        self.assertEqual(js_round(-2.6), -3)
        self.assertEqual(js_round(-2.4), -2)



class WeekDatesSource(unittest.TestCase):
    def test_money_uses_the_dates_module_for_week_dates(self):
        from ssust import dates, money
        self.assertIs(money.week_dates, dates.week_dates)
        self.assertFalse(hasattr(money, "add_days"))

if __name__ == "__main__":
    unittest.main()


def ready_state(today="2026-11-11", payments=(), **opening):
    base = {fund: 0 for fund in money.FUNDS}
    base.update(opening)
    return {"mode": "sample", "weekStart": "2026-11-09", "today": today, "opening": base, "payments": list(payments)}


class ZeroFunds(unittest.TestCase):
    """P0.2: any fund may be 0, with no division error and no None in the figures."""

    def test_snacks_zero(self):
        state = ready_state(main=50000, snack=0, experience=10000, savings=10000)
        view = money.snapshot(state)
        self.assertEqual(view["allowance"], 10000)  # 50000 / 5 days
        result = money.plan(state, 12000, "main")
        # Snacks is empty, so the only cover is Experience.
        self.assertEqual([o["choice"] for o in result["options"]], [money.FLEX])
        self.assertEqual(result["options"][0]["from"]["experience"], 2000)

    def test_all_food_zero(self):
        state = ready_state(experience=1000, savings=5000)
        view = money.snapshot(state)
        for key in ("allowance", "todayRemaining", "tomorrow", "threshold", "lifeAtStart", "lifeNow"):
            self.assertEqual(view[key], 0, key)
        self.assertTrue(view["overToday"])
        self.assertFalse(view["notice"])
        result = money.plan(state, 3000, "snack")
        [option] = result["options"]
        self.assertEqual(option["choice"], "savings")
        self.assertEqual((option["from"]["experience"], option["from"]["savings"]), (1000, 2000))

    def test_everything_zero(self):
        state = ready_state()
        self.assertEqual(money.snapshot(state)["allowance"], 0)
        self.assertEqual(money.plan(state, 1, "main"), {"error": "The five funds cannot cover this."})
        fixed = money.plan(state, 500, "fixed")
        self.assertEqual((fixed["from"]["fixed"], fixed["uncovered"]), (0, 500))


def pick(result, choice):
    return next(o for o in result["options"] if o["choice"] == choice)


class DailyBudgetEdges(unittest.TestCase):
    """P0.3: exact cents for the daily allowance and every reallocation choice."""

    def test_first_day_of_the_week(self):
        view = snapshot(ready_state("2026-11-09", main=70000, snack=7000))
        self.assertEqual((view["daysLeft"], view["daysAfter"]), (7, 6))
        self.assertEqual((view["allowance"], view["tomorrow"]), (11000, 11000))

    def test_last_day_of_the_week_gets_all_food(self):
        view = snapshot(ready_state("2026-11-15", main=70000, snack=7000))
        self.assertEqual((view["daysLeft"], view["daysAfter"]), (1, 0))
        self.assertEqual((view["allowance"], view["tomorrow"]), (77000, 0))

    def test_budget_exhausted_exactly(self):
        state = ready_state(main=45000, snack=5000)
        self.assertEqual(add(state, 10000, "main")["saveNow"], True)
        view = snapshot(state)
        self.assertEqual((view["todayRemaining"], view["overToday"], view["notice"]), (0, False, True))
        self.assertEqual(view["tomorrow"], 10000)

    def over_state(self):
        return ready_state(main=45000, snack=5000, fixed=30000, experience=10000, development=5000, savings=20000)

    def test_spend_above_budget_offers_snacks_then_flex(self):
        result = plan(self.over_state(), 13000, "main")
        self.assertEqual([o["choice"] for o in result["options"]], ["snack", money.FLEX])
        snack, flex = pick(result, "snack"), pick(result, money.FLEX)
        self.assertEqual((snack["from"]["main"], snack["from"]["snack"]), (10000, 3000))
        self.assertEqual((flex["from"]["main"], flex["from"]["experience"]), (10000, 3000))

    def test_snack_choice_goes_negative_today_and_lowers_tomorrow(self):
        state = self.over_state()
        add(state, 13000, "main", "snack")
        view = snapshot(state)
        self.assertEqual(view["todayRemaining"], -3000)
        self.assertTrue(view["overToday"])
        self.assertEqual(view["tomorrow"], 9250)  # (50000 - 13000) / 4
        self.assertEqual((view["fundsNow"]["main"], view["fundsNow"]["snack"]), (35000, 2000))

    def test_flex_choice_keeps_tomorrow(self):
        state = self.over_state()
        add(state, 13000, "main", money.FLEX)
        view = snapshot(state)
        self.assertEqual((view["todayRemaining"], view["tomorrow"]), (0, 10000))
        self.assertEqual(view["fundsNow"]["experience"], 7000)
        self.assertEqual(view["fundsNow"]["fixed"], 30000)

    def ladder_state(self, savings):
        return ready_state(main=45000, snack=1000, fixed=50000, experience=2000, development=1000, savings=savings)

    def test_ladder_draws_snack_experience_development_then_savings(self):
        state = self.ladder_state(20000)
        self.assertEqual(snapshot(state)["allowance"], 9200)  # 46000 / 5
        result = add(state, 20000, "main", "savings")
        [option] = result["options"]
        self.assertEqual(option["hole"], 3)
        self.assertEqual(option["from"], {"main": 9200, "snack": 1000, "fixed": 0,
                                          "experience": 2000, "development": 1000, "savings": 6800})
        view = snapshot(state)
        self.assertEqual(view["fundsNow"], {"main": 35800, "snack": 0, "fixed": 50000,
                                            "experience": 0, "development": 0, "savings": 13200})
        self.assertEqual((view["todayRemaining"], view["tomorrow"]), (-1000, 8950))

    def test_insufficient_savings_is_refused_and_fixed_is_never_used(self):
        state = self.ladder_state(6799)  # one cent short; Fixed Bills holds HK$500 but never lends
        self.assertEqual(plan(state, 20000, "main"), {"error": "The five funds cannot cover this."})

    def test_fund_edit_mid_week_changes_today_and_tomorrow(self):
        monday = {"id": "x", "date": "2026-11-09", "amount": 5000, "category": "main", "note": "",
                  "from": {**money.empty_from(), "main": 5000}}
        state = ready_state(payments=[monday], main=45000, snack=5000)
        view = snapshot(state)
        self.assertEqual((view["allowance"], view["tomorrow"]), (9000, 9000))  # 45000 / 5
        state["opening"]["main"] = 60000
        view = snapshot(state)
        self.assertEqual((view["allowance"], view["tomorrow"]), (12000, 12000))  # 60000 / 5


class IntegerCentsOnly(unittest.TestCase):
    """P0.5: the money rules use integer arithmetic only (no float division, no float constants)."""

    def test_no_float_maths_in_money_py(self):
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(money))
        for node in ast.walk(tree):
            with self.subTest(line=getattr(node, "lineno", None)):
                self.assertFalse(isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div), "use round_div")
                self.assertFalse(isinstance(node, ast.Constant) and isinstance(node.value, float), "float constant")

    def test_round_div_matches_javascript_rounding(self):
        for a in range(-2000, 2001, 7):
            for d in (1, 2, 3, 4, 5, 6, 7, 10):
                with self.subTest(a=a, d=d):
                    self.assertEqual(money.round_div(a, d), js_round(a / d))
        self.assertEqual(money.round_div(5, 2), 3)
        self.assertEqual(money.round_div(-5, 2), -2)

    def test_hk_text(self):
        self.assertEqual(money.hk(1234), "HK$12.34")
        self.assertEqual(money.hk(30000), "HK$300")
        self.assertEqual(money.hk(123456789), "HK$1,234,567.89")
        self.assertEqual(money.hk(-5), "-HK$0.05")


class CoverParts(unittest.TestCase):
    """P1.2: each option says which funds cover the gap and by how much (for the confirmation modal)."""

    def test_food_options_cover(self):
        state = make_state("sample")
        add(state, 4800, "main")
        result = plan(state, 10000, "main")
        by_choice = {o["choice"]: o for o in result["options"]}
        self.assertEqual(by_choice["snack"]["cover"], {"snack": 800})
        self.assertEqual(by_choice[money.FLEX]["cover"], {"experience": 800})

    def test_flex_category_cover(self):
        [option] = plan(make_state("sample"), 15000, "experience")["options"]
        self.assertEqual(option["cover"], {"development": 3000})

    def test_ladder_cover_lists_funds_in_order_with_savings_last(self):
        state = ready_state(main=45000, snack=1000, fixed=50000, experience=2000, development=1000, savings=20000)
        [option] = plan(state, 20000, "main")["options"]
        self.assertEqual(list(option["cover"].items()),
                         [("snack", 1000), ("experience", 2000), ("development", 1000), ("savings", 6800)])

    def test_fixed_is_never_a_cover(self):
        state = ready_state(main=1000, snack=0, fixed=99999, experience=0, development=0, savings=5000)
        for category in ("main", "snack", "experience", "development"):
            with self.subTest(category=category):
                for option in plan(state, 3000, category)["options"]:
                    self.assertNotIn("fixed", option["cover"])
                    self.assertEqual(option["from"]["fixed"], 0)


class FundTanks(unittest.TestCase):
    """The water level of each fund: remaining / weekly allocation, in integers only."""

    def tank(self, opening, remaining, fund="main"):
        state = {**make_state("sample"), "payments": []}
        state["opening"] = {**state["opening"], fund: opening}
        state["payments"] = [{"id": "x", "date": state["today"], "amount": opening - remaining, "category": "main",
                              "note": "", "from": {**money.empty_from(), fund: opening - remaining}}]
        return next(t for t in money.fund_tanks(state) if t["fund"] == fund)

    def test_sample_week_order_and_amounts(self):
        tanks = money.fund_tanks(make_state("sample"))
        self.assertEqual([t["fund"] for t in tanks], list(money.FUNDS))
        self.assertEqual([t["name"] for t in tanks], [money.FUND_NAMES[f] for f in money.FUNDS])
        main = tanks[0]
        self.assertEqual((main["allocation"], main["remaining"]), (77000, 66000))
        self.assertEqual(main["level"], 8571)  # basis points, 66000 / 77000
        self.assertEqual(main["percent"], 86)
        self.assertEqual(main["tone"], "high")
        snack = tanks[1]
        self.assertEqual((snack["allocation"], snack["remaining"], snack["percent"], snack["tone"]), (8000, 4000, 50, "mid"))
        for tank in tanks:
            for key in ("allocation", "remaining", "level", "percent"):
                self.assertIs(type(tank[key]), int)

    def test_tone_thresholds(self):
        cases = [
            (10000, 10000, 100, "high"),
            (10000, 5001, 50, "high"),  # above 50%
            (10000, 5000, 50, "mid"),   # 50% is amber
            (10000, 2000, 20, "mid"),   # 20% is still amber
            (10000, 1999, 20, "low"),   # below 20%: red, even if it rounds to 20
            (10000, 1, 1, "low"),       # a cent left never shows 0%
            (10000, 0, 0, "empty"),
        ]
        for opening, remaining, percent, tone in cases:
            with self.subTest(remaining=remaining):
                tank = self.tank(opening, remaining)
                self.assertEqual((tank["percent"], tank["tone"]), (percent, tone))

    def test_almost_full_never_shows_100(self):
        tank = self.tank(100000, 99999)
        self.assertEqual(tank["percent"], 99)
        self.assertLess(tank["level"], 10000)

    def test_zero_allocation_is_neutral_without_division(self):
        tank = self.tank(0, 0, fund="development")
        self.assertEqual((tank["allocation"], tank["remaining"], tank["level"], tank["percent"]), (0, 0, 0, 0))
        self.assertEqual(tank["tone"], "none")

    def test_fixed_bills_never_alerts(self):
        for remaining in (20000, 5000, 100, 0):
            with self.subTest(remaining=remaining):
                tank = self.tank(20000, remaining, fund="fixed")
                self.assertEqual(tank["tone"], "neutral")
        self.assertEqual(self.tank(0, 0, fund="fixed")["tone"], "none")

    def test_level_is_clamped(self):
        state = make_state("sample")
        state["payments"] = [{"id": "x", "date": state["today"], "amount": 99999, "category": "main", "note": "",
                              "from": {**money.empty_from(), "main": 99999}}]
        main = money.fund_tanks(state)[0]
        self.assertEqual((main["remaining"], main["level"], main["percent"], main["tone"]), (-22999, 0, 0, "empty"))

    def test_not_ready_week_has_no_tanks(self):
        self.assertEqual(money.fund_tanks(make_state("empty")), [])
