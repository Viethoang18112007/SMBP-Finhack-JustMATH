import unittest
from money import make_state, plan, snapshot


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
        borrow = next(item for item in result["options"] if item["choice"] == "borrow")
        self.assertEqual(snack["hole"], 1)
        self.assertEqual(snack["from"]["snack"], 800)
        self.assertEqual(snack["tomorrowAfter"], 13800)
        self.assertEqual(snack["fundsAfter"]["snack"], 3200)
        self.assertEqual(borrow["hole"], 2)
        self.assertEqual(borrow["from"]["experience"], 800)
        self.assertEqual(borrow["tomorrowAfter"], 14000)
        self.assertEqual(borrow["fundsAfter"]["experience"], 11200)
        self.assertEqual(borrow["fundsAfter"]["snack"], 4000)

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

    def test_experience_borrows_development(self):
        state = make_state("sample")
        result = plan(state, 15000, "experience")
        self.assertEqual(result["level"], 2)
        option = result["options"][0]
        self.assertEqual(option["from"]["experience"], 12000)
        self.assertEqual(option["from"]["development"], 3000)
        self.assertEqual(option["fundsAfter"]["experience"], 0)
        self.assertEqual(option["fundsAfter"]["development"], 5000)
        self.assertEqual(option["tomorrowAfter"], 14000)

    def test_fixed_bill_does_not_borrow(self):
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


if __name__ == "__main__":
    unittest.main()
