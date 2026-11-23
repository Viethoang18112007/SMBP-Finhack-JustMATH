import sqlite3
import tempfile
import unittest
from pathlib import Path

from ssust import money
from ssust.store import DEMO_FILE, LIVE_FILE, SCHEMA_VERSION, Store, open_books

OPENING = dict(money.SAMPLE_OPENING)


def payment(date="2026-11-10", amount=4800, category="main", note="lunch", **taken):
    source = {**money.empty_from(), **(taken or {category: amount})}
    return {"date": date, "amount": amount, "category": category, "note": note, "from": source}


class TempDir(unittest.TestCase):
    """Every test gets its own temporary folder; the real data/ folder is never used."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def live(self):
        return Store(self.dir / "live.db", "live")

    def demo(self):
        return Store(self.dir / "demo.db", "demo")


class Schema(TempDir):
    def test_new_file_gets_the_current_user_version(self):
        self.live()
        con = sqlite3.connect(self.dir / "live.db")
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            con.close()
        self.assertTrue({"meta", "weeks", "payments"} <= tables)
        self.assertEqual(SCHEMA_VERSION, 5)  # v5: meals logged at a place, and feedback

    def test_reopening_does_not_migrate_again(self):
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
        store = self.live()
        with store.session() as s:
            self.assertEqual(s.get_week("2026-11-09"), OPENING)

    def test_a_newer_schema_is_refused(self):
        con = sqlite3.connect(self.dir / "live.db")
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        con.close()
        with self.assertRaises(RuntimeError):
            self.live()

    def test_missing_folder_is_created(self):
        Store(self.dir / "data" / "nested" / "x.db", "live")
        self.assertTrue((self.dir / "data" / "nested" / "x.db").exists())

    def test_unknown_book_is_refused(self):
        with self.assertRaises(ValueError):
            Store(self.dir / "x.db", "sample")


class Persistence(TempDir):
    def test_weeks_payments_and_meta_survive_close_and_reopen(self):
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
            pid = s.add_payment(payment(), created_at="2026-11-10T12:00:00+00:00")
            s.set_meta("campus", "hkbu")
            s.set_mode("demo")
        del store

        again = self.live()
        with again.session() as s:
            self.assertEqual(s.get_week("2026-11-09"), OPENING)
            self.assertEqual(s.get_meta("campus"), "hkbu")
            self.assertEqual(s.get_mode(), "demo")
            [saved] = s.payments("2026-11-09")
        self.assertEqual(saved["id"], pid)
        self.assertEqual(saved["createdAt"], "2026-11-10T12:00:00+00:00")
        self.assertEqual(saved["from"], {**money.empty_from(), "main": 4800})

    def test_failed_write_session_rolls_back(self):
        store = self.live()
        with self.assertRaises(ZeroDivisionError):
            with store.session(write=True) as s:
                s.set_week("2026-11-09", OPENING)
                1 / 0
        with store.session() as s:
            self.assertIsNone(s.get_week("2026-11-09"))


class Isolation(TempDir):
    def test_open_books_uses_two_files_in_the_data_folder(self):
        books = open_books(self.dir)
        self.assertEqual(set(books), {"live", "demo"})
        self.assertEqual(books["live"].path, self.dir / LIVE_FILE)
        self.assertEqual(books["demo"].path, self.dir / DEMO_FILE)
        self.assertNotEqual(LIVE_FILE, DEMO_FILE)

    def test_open_books_creates_a_missing_data_folder(self):
        folder = self.dir / "fresh" / "data"
        self.assertFalse(folder.exists())
        books = open_books(folder)
        self.assertTrue(folder.is_dir())
        self.assertTrue((folder / LIVE_FILE).is_file())
        self.assertTrue((folder / DEMO_FILE).is_file())
        with books["live"].session() as s:
            self.assertEqual(s.weeks(), [])

    def test_demo_writes_never_show_up_in_live(self):
        books = open_books(self.dir)
        with books["demo"].session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
            s.add_payment(payment())
            s.set_meta("scenario", "over")
        with books["live"].session() as s:
            self.assertIsNone(s.get_week("2026-11-09"))
            self.assertEqual(s.payments("2026-11-09"), [])
            self.assertEqual(s.weeks(), [])
            self.assertIsNone(s.get_meta("scenario"))

    def test_a_file_cannot_be_opened_as_the_other_book(self):
        self.live()
        with self.assertRaises(ValueError):
            Store(self.dir / "live.db", "demo")

    def test_demo_reset_clears_weeks_and_payments_but_keeps_meta(self):
        demo = self.demo()
        with demo.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
            s.add_payment(payment())
            s.set_meta("scenario", "sample")
            s.reset()
        with demo.session() as s:
            self.assertEqual(s.weeks(), [])
            self.assertEqual(s.payments("2026-11-09"), [])
            self.assertEqual(s.get_meta("scenario"), "sample")

    def test_live_book_cannot_be_reset(self):
        live = self.live()
        with live.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
        with self.assertRaises(PermissionError):
            with live.session(write=True) as s:
                s.reset()
        with live.session() as s:
            self.assertEqual(s.get_week("2026-11-09"), OPENING)


class Weeks(TempDir):
    def test_set_week_replaces_the_amounts(self):
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
            s.set_week("2026-11-09", {**OPENING, "main": 1})
        with store.session() as s:
            self.assertEqual(s.get_week("2026-11-09")["main"], 1)
            self.assertEqual(s.weeks(), ["2026-11-09"])

    def test_previous_week_is_the_latest_one_before(self):
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-10-26", {**OPENING, "main": 1})
            s.set_week("2026-11-02", {**OPENING, "main": 2})
            s.set_week("2026-11-16", {**OPENING, "main": 3})
        with store.session() as s:
            self.assertEqual(s.previous_week("2026-11-09"), ("2026-11-02", {**OPENING, "main": 2}))
            self.assertEqual(s.previous_week("2026-11-02")[0], "2026-10-26")
            self.assertIsNone(s.previous_week("2026-10-26"))
            self.assertEqual(s.weeks(), ["2026-10-26", "2026-11-02", "2026-11-16"])

    def test_week_must_start_on_a_monday(self):
        with self.live().session(write=True) as s:
            with self.assertRaises(ValueError):
                s.set_week("2026-11-10", OPENING)

    def test_bad_amounts_are_refused(self):
        bad = [
            {**OPENING, "main": 770.0},
            {**OPENING, "main": "77000"},
            {**OPENING, "main": True},
            {**OPENING, "main": -1},
            {**OPENING, "main": None},
            {k: v for k, v in OPENING.items() if k != "savings"},
            {**OPENING, "extra": 1},
        ]
        store = self.live()
        for amounts in bad:
            with self.subTest(amounts=amounts):
                with self.assertRaises(ValueError):
                    with store.session(write=True) as s:
                        s.set_week("2026-11-09", amounts)
        with store.session() as s:
            self.assertEqual(s.weeks(), [])


class Payments(TempDir):
    def test_payments_are_listed_by_week_in_order(self):
        store = self.live()
        with store.session(write=True) as s:
            s.add_payment(payment(date="2026-11-15", note="sun"))
            s.add_payment(payment(date="2026-11-09", note="mon"))
            s.add_payment(payment(date="2026-11-16", note="next mon"))
            s.add_payment(payment(date="2026-11-08", note="last sun"))
            s.add_payment(payment(date="2026-11-09", note="mon again"))
        with store.session() as s:
            notes = [p["note"] for p in s.payments("2026-11-09")]
            self.assertEqual(notes, ["mon", "mon again", "sun"])
            self.assertEqual([p["note"] for p in s.payments("2026-11-16")], ["next mon"])

    def test_payment_shape_matches_money_rules(self):
        store = self.live()
        with store.session(write=True) as s:
            s.add_payment({**payment(amount=10000, snack=2000, main=5000, savings=3000), "uncovered": 0})
            [p] = s.payments("2026-11-09")
        self.assertEqual(set(p), {"id", "date", "amount", "category", "note", "from", "uncovered", "createdAt"})
        self.assertEqual(set(p["from"]), set(money.FUNDS))
        state = {"weekStart": "2026-11-09", "today": "2026-11-11", "opening": OPENING, "payments": [p]}
        self.assertEqual(money.snapshot(state)["fundsNow"]["savings"], OPENING["savings"] - 3000)

    def test_exact_cents_round_trip(self):
        amounts = [1, 99, 101, 4999, 12345, 99_999_999, 100_000_000]
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-11-09", {fund: 100_000_000 - i for i, fund in enumerate(money.FUNDS)})
            for amount in amounts:
                s.add_payment({**payment(amount=amount, category="experience"), "uncovered": amount // 3})
        with store.session() as s:
            saved = s.payments("2026-11-09")
            week = s.get_week("2026-11-09")
        self.assertEqual([p["amount"] for p in saved], amounts)
        self.assertEqual([p["from"]["experience"] for p in saved], amounts)
        self.assertEqual([p["uncovered"] for p in saved], [a // 3 for a in amounts])
        for p in saved:
            self.assertIs(type(p["amount"]), int)
            self.assertIs(type(p["uncovered"]), int)
        self.assertEqual(week, {fund: 100_000_000 - i for i, fund in enumerate(money.FUNDS)})
        self.assertTrue(all(type(v) is int for v in week.values()))

    def test_columns_hold_integers_on_disk(self):
        store = self.live()
        with store.session(write=True) as s:
            s.set_week("2026-11-09", OPENING)
            s.add_payment(payment())
        con = sqlite3.connect(store.path)
        try:
            kinds = set(con.execute("SELECT typeof(amount), typeof(from_main), typeof(uncovered) FROM payments").fetchone())
            kinds |= set(con.execute("SELECT typeof(main), typeof(savings) FROM weeks").fetchone())
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE payments SET amount = 48.5")
        finally:
            con.close()
        self.assertEqual(kinds, {"integer"})

    def test_bad_payments_are_refused(self):
        bad = [
            payment(amount=48.0),
            payment(amount=0),
            payment(amount=-1),
            payment(amount=True),
            payment(category="savings"),
            payment(date="2026-11-1"),
            payment(note=None),
            {**payment(), "from": {"main": 4800}},
            {**payment(), "from": {**money.empty_from(), "main": 48.0}},
            {**payment(), "uncovered": -5},
            {k: v for k, v in payment().items() if k != "date"},
        ]
        store = self.live()
        for item in bad:
            with self.subTest(item=item):
                with self.assertRaises(ValueError):
                    with store.session(write=True) as s:
                        s.add_payment(item)
        with store.session() as s:
            self.assertEqual(s.payments("2026-11-09"), [])


class Mode(TempDir):
    def test_default_mode_is_live(self):
        with self.live().session() as s:
            self.assertEqual(s.get_mode(), "live")

    def test_mode_must_be_live_or_demo(self):
        with self.live().session(write=True) as s:
            s.set_mode("demo")
            self.assertEqual(s.get_mode(), "demo")
            with self.assertRaises(ValueError):
                s.set_mode("sample")

    def test_meta_values_must_be_text(self):
        with self.live().session(write=True) as s:
            with self.assertRaises(ValueError):
                s.set_meta("campus", 3)


if __name__ == "__main__":
    unittest.main()


def make_v1_file(path):
    """A database exactly as version 1 of the app wrote it, with one week and one payment."""
    from ssust import store as store_module
    con = sqlite3.connect(path)
    for statement in store_module._SCHEMA_V1:
        con.execute(statement)
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO meta (key, value) VALUES ('book', 'live')")
    con.execute("INSERT INTO weeks VALUES ('2026-11-09', 77000, 8000, 20000, 12000, 8000, 50000)")
    con.execute("INSERT INTO payments (date, amount, category, note, from_main, from_snack, from_fixed, "
                "from_experience, from_development, from_savings, uncovered, created_at) "
                "VALUES ('2026-11-10', 4800, 'main', 'lunch', 4800, 0, 0, 0, 0, 0, 0, '2026-11-10T04:00:00+00:00')")
    con.commit()
    con.close()


class Migration(TempDir):
    """P0.4: an existing version 1 database opens, keeps its data and gains the request id column."""

    def test_v1_file_is_migrated_in_place(self):
        make_v1_file(self.dir / "live.db")
        store = self.live()
        with store.session() as s:
            self.assertEqual(s.get_week("2026-11-09"), OPENING)
            [p] = s.payments("2026-11-09")
        self.assertEqual((p["amount"], p["note"]), (4800, "lunch"))
        con = sqlite3.connect(self.dir / "live.db")
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            columns = {row[1] for row in con.execute("PRAGMA table_info(payments)")}
        finally:
            con.close()
        self.assertIn("request_id", columns)
        self.assertIn("voided_at", columns)


class RequestIds(TempDir):
    def test_a_request_id_is_unique(self):
        store = self.live()
        with store.session(write=True) as s:
            first = s.add_payment(payment(), request_id="abcdef12-0001")
            self.assertEqual(s.payment_by_request("abcdef12-0001")["id"], first)
            self.assertIsNone(s.payment_by_request("abcdef12-0002"))
        with self.assertRaises(sqlite3.IntegrityError):
            with store.session(write=True) as s:
                s.add_payment(payment(), request_id="abcdef12-0001")
        with store.session(write=True) as s:
            s.add_payment(payment())  # no id: never conflicts
            s.add_payment(payment())
            self.assertEqual(len(s.payments("2026-11-09")), 3)

    def test_bad_request_ids_are_refused(self):
        store = self.live()
        for bad in ("short", "x" * 65, "has space 123", "<script>12", 12345678, ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    with store.session(write=True) as s:
                        s.add_payment(payment(), request_id=bad)


class Voiding(TempDir):
    """P1.3: an undone payment is kept but voided, and no longer counts."""

    def test_void_hides_the_payment_from_the_week(self):
        store = self.live()
        with store.session(write=True) as s:
            keep = s.add_payment(payment(note="keep"))
            gone = s.add_payment(payment(note="gone"), request_id="req-gone-01")
            self.assertTrue(s.void_payment(gone))
            self.assertFalse(s.void_payment(gone))  # already void: nothing changes
            self.assertEqual([p["id"] for p in s.payments("2026-11-09")], [keep])
            self.assertIsNotNone(s.get_payment(gone)["voidedAt"])
            self.assertIsNone(s.get_payment(keep)["voidedAt"])
            self.assertIsNone(s.get_payment(9999))
            self.assertEqual(s.payment_by_request("req-gone-01")["id"], gone)

    def test_read_session_cannot_void(self):
        store = self.live()
        with store.session(write=True) as s:
            pid = s.add_payment(payment())
        with store.session() as s:
            with self.assertRaises(PermissionError):
                s.void_payment(pid)


class InboxStore(TempDir):
    """Schema v4: incoming payments to review, idempotent by external id, and the fund per merchant."""

    ITEM = {"externalId": "tap-0001-abcd", "source": "apple_pay", "amount": 3800,
            "merchant": "Sample Coffee Kiosk", "card": "Sample card 0000", "receivedAt": "2026-11-11T04:00:00+00:00"}

    def test_add_is_idempotent_by_external_id(self):
        store = self.live()
        with store.session(write=True) as s:
            first, created = s.add_inbox(self.ITEM)
            again, created_again = s.add_inbox({**self.ITEM, "amount": 9999})
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, again)
        with store.session() as s:
            [item] = s.inbox("pending")
        self.assertEqual((item["amount"], item["status"], item["source"]), (3800, "pending", "apple_pay"))

    def test_status_changes_and_payment_link(self):
        store = self.live()
        with store.session(write=True) as s:
            item_id, _ = s.add_inbox(self.ITEM)
            self.assertTrue(s.set_inbox_status(item_id, "confirmed", payment_id=7))
            self.assertFalse(s.set_inbox_status(item_id, "dismissed"))  # only a pending item changes
            self.assertEqual(s.get_inbox(item_id)["paymentId"], 7)
            self.assertEqual(s.inbox("pending"), [])
            with self.assertRaises(ValueError):
                s.set_inbox_status(item_id, "lost")

    def test_bad_items_are_refused(self):
        store = self.live()
        with store.session(write=True) as s:
            for bad in ({"source": "bank"}, {"amount": 0}, {"amount": 12.5}, {"externalId": "x"}):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    s.add_inbox({**self.ITEM, **bad})

    def test_merchant_fund_memory(self):
        store = self.live()
        with store.session(write=True) as s:
            self.assertIsNone(s.merchant_fund("Sample Coffee Kiosk"))
            s.remember_merchant_fund("Sample Coffee Kiosk", "snack")
            s.remember_merchant_fund("sample coffee kiosk ", "main")  # same merchant, any case
            self.assertEqual(s.merchant_fund("SAMPLE COFFEE KIOSK"), "main")

    def test_demo_reset_clears_the_inbox(self):
        store = Store(self.dir / "demo.db", "demo")
        with store.session(write=True) as s:
            s.add_inbox(self.ITEM)
            s.remember_merchant_fund("Sample Coffee Kiosk", "snack")
            s.reset()
            self.assertEqual(s.inbox("pending"), [])
            self.assertIsNone(s.merchant_fund("Sample Coffee Kiosk"))

    def test_v3_file_gains_the_inbox(self):
        make_v1_file(self.dir / "live.db")
        con = sqlite3.connect(self.dir / "live.db")
        from ssust import store as store_module
        for statement in store_module._SCHEMA_V2 + store_module._SCHEMA_V3:
            con.execute(statement)
        con.execute("PRAGMA user_version = 3")
        con.commit()
        con.close()
        store = self.live()
        with store.session(write=True) as s:
            self.assertEqual(len(s.payments("2026-11-09")), 1)
            s.add_inbox(self.ITEM)
