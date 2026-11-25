"""Wallet taps that arrive without an amount (Octopus in Apple Wallet gives Shortcuts no amount).

A tap with a card or merchant but no amount is kept as an "amount unknown" item in To review, so it
is never lost and never taken for a test run. iOS can fire twice for one tap: within
service.TAP_WINDOW_SECONDS the same card collapses into one item, and a later amount fills it in.
Settings shows which fields the last message carried (names only, plus the card name).
"""

import copy
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ssust import backup, money, service as service_module, store as store_module
from ssust.dates import FixedClock
from ssust.service import TAP_WINDOW_SECONDS, Service, ServiceError, is_octopus_card
from ssust.store import SCHEMA_VERSION, Store, open_books

from tests.test_api import FUNDS_TEXT
from tests.test_backup import PHONE, DeviceApi
from tests.test_store import make_v1_file
from tests.test_wallet_shortcuts import DeviceClient

T0 = datetime(2027, 3, 3, 4, 0, 0, tzinfo=timezone.utc)  # 12:00 in Hong Kong


def at(seconds):
    return T0 + timedelta(seconds=seconds)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.svc = Service(open_books(Path(self._tmp.name) / "data"), FixedClock("2027-03-03"))
        self.svc.set_funds(dict(money.SAMPLE_OPENING))

    def tap(self, seconds=0, **body):
        return self.svc.wallet_tap(body.get("amount"), body.get("merchant"), body.get("card"), now=at(seconds))

    def inbox(self):
        return self.svc.get_state()["inbox"]

    def last(self):
        return self.svc.get_state()["walletLast"]


class Window(unittest.TestCase):
    def test_the_window_is_two_minutes(self):
        self.assertEqual(TAP_WINDOW_SECONDS, 120)


class OctopusNames(unittest.TestCase):
    def test_octopus_like_names(self):
        for card in ("Octopus", "octopus", "My OCTOPUS card", "八達通", "八达通", "Smart 八達通"):
            with self.subTest(card=card):
                self.assertTrue(is_octopus_card(card))
        for card in ("Visa 1234", "", None, "Apple Pay", 5):
            with self.subTest(card=card):
                self.assertFalse(is_octopus_card(card))


class Rules(Base):
    def test_a_valid_amount_is_unchanged(self):
        result = self.tap(amount="HK$38.00", merchant="Pacific Coffee", card="Visa 1234")
        self.assertEqual(result["amount"], 3800)
        [item] = self.inbox()
        self.assertEqual((item["amount"], item["merchant"], item["card"], item["amountUnknown"]),
                         (3800, "Pacific Coffee", "Visa 1234", False))
        self.assertTrue(self.last()["ok"])

    def test_no_amount_with_a_card_is_kept_as_amount_unknown(self):
        result = self.tap(card="Octopus")
        self.assertTrue(result["ok"])
        self.assertTrue(result["amountUnknown"])
        self.assertIsNone(result["amount"])
        [item] = self.inbox()
        self.assertIsNone(item["amount"])
        self.assertTrue(item["amountUnknown"])
        self.assertTrue(item["octopus"])
        self.assertEqual(item["label"], "Octopus tap")
        self.assertEqual(item["source"], "wallet")
        self.assertEqual(item["merchant"], "Octopus tap")
        self.assertIsNone(item["typo"])
        self.assertIn(item["suggestedFund"], money.CATEGORIES)
        self.assertTrue(item["suggestedReason"])
        last = self.last()
        self.assertTrue(last["ok"])
        self.assertTrue(last["amountUnknown"])
        self.assertEqual(last["detail"], "Tap received without amount: open SSUST to add it.")
        self.assertEqual(self.svc.get_state()["payments"], [])  # nothing is spent

    def test_zero_amount_with_a_merchant_is_amount_unknown(self):
        for amount in ("0", "HK$0.00", 0, 0.0):
            with self.subTest(amount=amount):
                self.tap(seconds=1000 * len(self.inbox()), amount=amount, merchant="Bakery", card=f"Card {amount}")
        self.assertEqual(len(self.inbox()), 4)
        self.assertTrue(all(i["amountUnknown"] for i in self.inbox()))
        self.assertTrue(all(not i["octopus"] for i in self.inbox()))
        self.assertEqual(self.inbox()[0]["label"], "Card 0 tap")

    def test_all_fields_empty_stays_a_test_run(self):
        for body in ({}, {"amount": "", "merchant": "", "card": ""}, {"amount": None, "card": "   "}):
            with self.subTest(body=body):
                with self.assertRaises(ServiceError):
                    self.tap(**body)
                self.assertTrue(self.last()["linkOk"])
                self.assertIn("the link works", self.last()["detail"])
        self.assertEqual(self.inbox(), [])

    def test_an_amount_that_is_not_understood_is_still_refused(self):
        with self.assertRaises(ServiceError):
            self.tap(amount="abc", merchant="Bakery")
        self.assertEqual(self.inbox(), [])


class Duplicates(Base):
    def test_two_taps_within_the_window_give_one_item(self):
        self.tap(card="Octopus")
        self.tap(seconds=TAP_WINDOW_SECONDS - 1, card="octopus")
        self.assertEqual(len(self.inbox()), 1)

    def test_a_later_amount_upgrades_the_item(self):
        self.tap(card="Octopus")
        result = self.tap(seconds=30, amount="HK$24.50", merchant="7-Eleven", card="Octopus")
        self.assertEqual(result["amount"], 2450)
        [item] = self.inbox()
        self.assertEqual((item["amount"], item["merchant"], item["amountUnknown"]), (2450, "7-Eleven", False))
        self.assertTrue(item["octopus"])

    def test_a_later_amount_without_a_merchant_keeps_the_label(self):
        self.tap(card="Octopus")
        self.tap(seconds=30, amount="24.50", card="Octopus")
        [item] = self.inbox()
        self.assertEqual((item["amount"], item["merchant"]), (2450, "Octopus tap"))

    def test_an_amountless_tap_after_a_paid_one_adds_nothing(self):
        self.tap(amount="38", merchant="Cafe", card="Visa 1234")
        self.tap(seconds=5, card="Visa 1234")
        [item] = self.inbox()
        self.assertEqual(item["amount"], 3800)

    def test_outside_the_window_gives_two_items(self):
        self.tap(card="Octopus")
        self.tap(seconds=TAP_WINDOW_SECONDS + 1, card="Octopus")
        self.assertEqual(len(self.inbox()), 2)

    def test_another_card_gives_two_items(self):
        self.tap(card="Octopus")
        self.tap(seconds=10, card="Visa 1234")
        self.tap(seconds=20, amount="38", card="Visa 1234")
        items = self.inbox()
        self.assertEqual([(i["card"], i["amount"]) for i in items], [("Octopus", None), ("Visa 1234", 3800)])

    def test_two_paid_taps_stay_two_payments(self):
        self.tap(amount="20", merchant="7-Eleven", card="Visa")
        self.tap(seconds=10, amount="20", merchant="7-Eleven", card="Visa")
        self.assertEqual(len(self.inbox()), 2)

    def test_a_reviewed_item_is_not_reused(self):
        self.tap(card="Octopus")
        self.svc.inbox_dismiss(self.inbox()[0]["id"])
        self.tap(seconds=10, card="Octopus")
        self.assertEqual(len(self.inbox()), 1)


class Confirm(Base):
    def item(self):
        self.tap(card="Octopus")
        return self.inbox()[0]["id"]

    def test_confirming_without_an_amount_is_refused(self):
        item_id = self.item()
        for amount in (None, 0, -100):
            with self.subTest(amount=amount), self.assertRaises(ServiceError):
                self.svc.inbox_confirm(item_id, "main", amount=amount)
        self.assertEqual(len(self.inbox()), 1)
        self.assertEqual(self.svc.get_state()["payments"], [])

    def test_confirming_with_an_amount_saves_the_cents(self):
        item_id = self.item()
        result = self.svc.inbox_confirm(item_id, "snack", amount=1250)
        self.assertEqual((result["payment"]["amount"], result["payment"]["category"]), (1250, "snack"))
        self.assertEqual(result["payment"]["note"], "Octopus tap")
        self.assertEqual(self.inbox(), [])
        with self.svc._books["live"].session() as s:
            row = s.get_inbox(item_id)
        self.assertEqual((row["status"], row["amount"]), ("confirmed", 1250))

    def test_the_typo_check_asks_first(self):
        item_id = self.item()
        result = self.svc.inbox_confirm(item_id, "snack", amount=48000)
        self.assertTrue(result["needsTypoCheck"])
        self.assertEqual(result["typo"]["suggestion"], 4800)
        self.assertEqual(self.svc.get_state()["payments"], [])
        result = self.svc.inbox_confirm(item_id, "snack", amount=48000, typo_checked=True)
        self.assertNotIn("needsTypoCheck", result)

    def test_an_item_with_an_amount_keeps_it(self):
        self.tap(amount="38", merchant="Cafe", card="Visa")
        item_id = self.inbox()[0]["id"]
        with self.assertRaises(ServiceError):
            self.svc.inbox_confirm(item_id, "snack", amount=9900)
        result = self.svc.inbox_confirm(item_id, "snack")
        self.assertEqual(result["payment"]["amount"], 3800)

    def test_dismiss_works(self):
        item_id = self.item()
        self.svc.inbox_dismiss(item_id)
        self.assertEqual(self.inbox(), [])


class Diagnostics(Base):
    def test_field_presence_only(self):
        self.tap(card="Octopus")
        last = self.last()
        self.assertEqual(last["received"], {"amount": False, "merchant": False, "card": True})
        self.assertEqual(last["cardName"], "Octopus")

    def test_never_stores_the_amount_or_merchant_values(self):
        self.tap(amount="0", merchant="Secret Shop", card="Octopus")
        text = json.dumps(self.last())
        self.assertNotIn("Secret Shop", text)
        self.assertEqual(self.last()["received"], {"amount": True, "merchant": True, "card": True})
        self.tap(seconds=1000, amount="HK$77.70", merchant="Hidden Cafe", card="Visa 9")
        last = self.last()
        self.assertEqual(set(last["received"].values()), {True})
        self.assertNotIn("77", json.dumps(last["received"]) + json.dumps(last["cardName"]))
        self.assertNotIn("Hidden", json.dumps(last["received"]) + json.dumps(last["cardName"]))

    def test_a_test_run_records_nothing_received(self):
        with self.assertRaises(ServiceError):
            self.tap()
        self.assertEqual(self.last()["received"], {"amount": False, "merchant": False, "card": False})
        self.assertIsNone(self.last()["cardName"])


class Route(DeviceClient):
    def test_amountless_tap_is_accepted(self):
        status, _, payload = self.post({"card": "Octopus", "amount": "", "merchant": ""})
        self.assertEqual(status, 200, payload)
        data = json.loads(payload)
        self.assertTrue(data["amountUnknown"])
        self.assertIn("open SSUST to add it", data["message"])
        [item] = self.device_state()["inbox"]
        self.assertTrue(item["amountUnknown"])

    def test_merchant_only_is_a_real_trigger(self):
        self.assertEqual(self.post({"merchant": "x"})[0], 200)

    def test_confirm_route_takes_the_amount(self):
        self.post({"card": "Octopus"})
        item_id = self.device_state()["inbox"][0]["id"]
        status, _, payload = self.post({"id": item_id, "category": "main"}, path="/api/inbox/confirm")
        self.assertEqual(status, 400, payload)
        status, _, payload = self.post({"id": item_id, "category": "main", "amount": "abc"}, path="/api/inbox/confirm")
        self.assertEqual(status, 400, payload)
        self.post_settings()
        status, _, payload = self.post({"id": item_id, "category": "main", "amount": "24.50"}, path="/api/inbox/confirm")
        self.assertEqual(status, 200, payload)
        self.assertEqual(json.loads(payload)["payment"]["amount"], 2450)

    def post_settings(self):
        status, _, payload = self.post(FUNDS_TEXT, path="/api/settings")
        self.assertEqual(status, 200, payload)


class MigrationV6(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "live.db"

    def test_schema_version(self):
        self.assertEqual(SCHEMA_VERSION, 6)

    def test_a_v5_file_keeps_its_inbox_and_allows_unknown_amounts(self):
        make_v1_file(self.path)
        con = sqlite3.connect(self.path)
        for statement in (store_module._SCHEMA_V2 + store_module._SCHEMA_V3 + store_module._SCHEMA_V4
                          + store_module._SCHEMA_V5):
            con.execute(statement)
        con.execute("PRAGMA user_version = 5")
        con.execute("INSERT INTO inbox (external_id, source, amount_cents, merchant, card, received_at, status, "
                    "payment_id) VALUES ('wallet-old-0001', 'wallet', 3800, 'Cafe', 'Visa', "
                    "'2027-03-03T04:00:00+00:00', 'confirmed', 1)")
        con.commit()
        con.close()
        store = Store(self.path, "live")
        with store.session(write=True) as s:
            [old] = s.inbox("confirmed")
            self.assertEqual((old["amount"], old["merchant"], old["paymentId"]), (3800, "Cafe", 1))
            item_id, _ = s.add_inbox({"externalId": "wallet-new-0001", "source": "wallet", "amount": None,
                                      "merchant": "Octopus tap", "card": "Octopus",
                                      "receivedAt": "2027-03-03T04:00:00+00:00"})
            self.assertIsNone(s.get_inbox(item_id)["amount"])
        con = sqlite3.connect(self.path)
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 6)
            indexes = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
            self.assertIn("inbox_by_status", indexes)
            # the database itself refuses a confirmed item without an amount, and a float
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE inbox SET status = 'confirmed' WHERE amount_cents IS NULL")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE inbox SET amount_cents = 12.5")
        finally:
            con.close()

    def test_only_wallet_items_may_lack_an_amount(self):
        store = Store(self.path, "live")
        with store.session(write=True) as s, self.assertRaises(ValueError):
            s.add_inbox({"externalId": "tap-0001-abcd", "source": "octopus", "amount": None,
                         "merchant": "Shop", "card": "Card", "receivedAt": "2027-03-03T04:00:00+00:00"})


class Backup(DeviceApi):
    def test_unknown_amount_items_survive_backup_and_restore(self):
        self.ok("POST", "/api/settings", FUNDS_TEXT)
        self.ok("POST", "/api/shortcut/wallet", {"card": "Octopus"})
        doc = self.backup()
        self.assertEqual(doc["schemaVersion"], 6)
        [row] = doc["tables"]["inbox"]
        self.assertIsNone(row["amount"])
        self.wipe()
        self.restore(doc)
        [item] = self.state()["inbox"]
        self.assertTrue(item["amountUnknown"])
        self.assertTrue(item["octopus"])
        self.assertTrue(self.state()["walletLast"]["received"]["card"])  # diagnostics come back too

    def test_an_older_backup_still_restores(self):
        self.ok("POST", "/api/settings", FUNDS_TEXT)
        self.ok("POST", "/api/shortcut/wallet", {"amount": "38", "merchant": "Cafe", "card": "Visa"})
        doc = self.backup()
        old = copy.deepcopy(doc)
        old["schemaVersion"] = 5
        old["tables"]["meta"]["wallet_last"] = json.dumps(
            {"at": "2027-03-03T04:00:00+00:00", "ok": True, "amount": "38", "detail": "HK$38 from Cafe"})
        old["revision"] = backup.revision(old["tables"])
        self.wipe()
        self.restore(old)
        state = self.state()
        self.assertEqual([i["amount"] for i in state["inbox"]], [3800])
        self.assertTrue(state["walletLast"]["ok"])

    def test_an_older_backup_cannot_hold_an_unknown_amount(self):
        self.ok("POST", "/api/shortcut/wallet", {"card": "Octopus"})
        doc = self.backup()
        doc["schemaVersion"] = 5
        self.refused("/api/restore", doc)

    def test_a_confirmed_item_needs_an_amount(self):
        self.ok("POST", "/api/shortcut/wallet", {"card": "Octopus"})
        doc = self.backup()
        doc["tables"]["inbox"][0]["status"] = "confirmed"
        doc["revision"] = backup.revision(doc["tables"])
        self.refused("/api/restore", doc)

    def test_only_wallet_items_may_lack_an_amount(self):
        self.ok("POST", "/api/shortcut/wallet", {"card": "Octopus"})
        doc = self.backup()
        doc["tables"]["inbox"][0]["source"] = "octopus"
        doc["revision"] = backup.revision(doc["tables"])
        self.refused("/api/restore", doc)


if __name__ == "__main__":
    unittest.main()
