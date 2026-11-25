"""Backup and restore for the iPhone app: the phone keeps a copy of its own data and rebuilds the
server from it after the hosting platform wipes the disk.

GET /api/backup gives one JSON document with everything stored for the calling phone.
POST /api/restore merges such a document back, in one transaction: rows already on the server are
kept, missing ones are added, nothing is half written. Only the phone named in X-SSUST-Device.
"""

import copy
import http.client
import json
import socket
import unittest

from ssust import backup
from ssust.server import MAX_BODY, MAX_RESTORE_BODY

from tests.test_api import FUNDS_TEXT, ApiTest

PHONE = "a" * 32
OTHER = "b" * 32


class DeviceApi(ApiTest):
    def send(self, method, path, body=None, device=PHONE, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"127.0.0.1:{self.port}")
            if device:
                conn.putheader("X-SSUST-Device", device)
            data = raw if raw is not None else (None if body is None else json.dumps(body).encode("utf-8"))
            if data is not None:
                conn.putheader("Content-Type", "application/json")
                conn.putheader("Content-Length", str(len(data)))
            conn.endheaders(data)
            response = conn.getresponse()
            return response.status, json.loads(response.read() or b"null")
        finally:
            conn.close()

    def ok(self, method, path, body=None, device=PHONE):
        status, data = self.send(method, path, body, device)
        self.assertEqual(status, 200, data)
        return data

    def refused(self, path, body=None, device=PHONE, method="POST"):
        status, data = self.send(method, path, body, device)
        self.assertEqual(status, 400, data)
        self.assertIsInstance(data.get("error"), str)
        return data["error"]

    def backup(self, device=PHONE):
        return self.ok("GET", "/api/backup", device=device)

    def restore(self, doc, device=PHONE):
        return self.ok("POST", "/api/restore", doc, device)

    def state(self, device=PHONE):
        return self.ok("GET", "/api/state", device=device)

    def wipe(self):
        """What Render does on a restart: a new server with an empty disk."""
        self.stop(self.server, self.thread)
        self.dir = self.dir.parent / f"wiped-{id(self)}-{self.port}"
        self.start()

    def populate(self, device=PHONE):
        """A phone with a bit of everything: budget, payments (one undone, one at a map place),
        Apple Pay items (one confirmed, one waiting), a campus and feedback."""
        self.ok("POST", "/api/settings", FUNDS_TEXT, device)
        self.ok("POST", "/api/campus", {"campus": "hkbu"}, device)
        self.ok("POST", "/api/payments", {"amount": "48.50", "category": "main", "note": "lunch",
                                          "requestId": "req-lunch-0001",
                                          "place": {"id": "node/123", "name": "Canteen"}}, device)
        tea = self.ok("POST", "/api/payments", {"amount": "12", "category": "snack", "note": "tea"}, device)
        self.ok("POST", "/api/payments/undo", {"id": tea["payment"]["id"]}, device)
        self.ok("POST", "/api/shortcut/wallet", {"amount": "HK$38.00", "merchant": "Cafe"}, device)
        self.ok("POST", "/api/shortcut/wallet", {"amount": "20", "merchant": "Shop"}, device)
        first = self.state(device)["inbox"][0]
        self.ok("POST", "/api/inbox/confirm", {"id": first["id"], "category": "main"}, device)
        self.ok("POST", "/api/feedback", {"rating": 5, "text": "Nice"}, device)


class Document(DeviceApi):
    def test_backup_holds_every_table_with_a_version_time_and_revision(self):
        self.populate()
        doc = self.backup()
        self.assertEqual(doc["format"], backup.FORMAT)
        self.assertEqual(doc["schemaVersion"], backup.SCHEMA_VERSION)
        self.assertEqual(doc["device"], PHONE)
        self.assertIsInstance(doc["exportedAt"], str)
        self.assertRegex(doc["revision"], r"^[0-9a-f]{64}$")
        tables = doc["tables"]
        self.assertEqual(set(tables), set(backup.TABLES))
        self.assertEqual(len(tables["weeks"]), 1)
        self.assertEqual(len(tables["payments"]), 3)  # lunch, the undone tea, the confirmed Apple Pay
        self.assertEqual([p["voidedAt"] is None for p in tables["payments"]], [True, False, True])
        self.assertEqual(len(tables["inbox"]), 2)
        self.assertEqual(len(tables["visits"]), 1)
        self.assertEqual(len(tables["feedback"]), 1)
        self.assertEqual(tables["merchantFunds"], [{"merchant": "cafe", "fund": "main"}])
        self.assertEqual(tables["meta"]["campus"], "hkbu")
        for payment in tables["payments"]:
            self.assertIs(type(payment["amount"]), int)

    def test_revision_changes_with_the_data_only(self):
        self.populate()
        first = self.backup()
        self.assertEqual(self.backup()["revision"], first["revision"])
        self.ok("POST", "/api/payments", {"amount": "5", "category": "snack"})
        self.assertNotEqual(self.backup()["revision"], first["revision"])

    def test_backup_and_restore_need_the_phone_header(self):
        self.refused("/api/backup", method="GET", device=None)
        self.refused("/api/restore", {"x": 1}, device=None)
        self.refused("/api/backup", method="GET", device="nope")

    def test_web_data_is_never_in_a_phone_backup(self):
        self.call("POST", "/api/settings", FUNDS_TEXT)  # the shared web book
        self.assertEqual(self.backup()["tables"]["weeks"], [])


class Fresh(DeviceApi):
    def test_a_new_phone_is_fresh_until_it_has_data(self):
        self.assertTrue(self.state()["fresh"])
        self.ok("POST", "/api/settings", FUNDS_TEXT)
        self.assertFalse(self.state()["fresh"])

    def test_an_apple_pay_item_alone_keeps_the_phone_fresh(self):
        self.ok("POST", "/api/shortcut/wallet", {"amount": "38"})
        state = self.state()
        self.assertTrue(state["fresh"])
        self.assertEqual(len(state["inbox"]), 1)

    def test_after_a_wipe_the_phone_is_fresh_again(self):
        self.populate()
        self.wipe()
        self.assertTrue(self.state()["fresh"])

    def test_ping_wakes_the_server_without_touching_data(self):
        self.assertEqual(self.ok("GET", "/api/ping", device=None), {"ok": True})
        self.assertEqual(list((self.dir / "devices").glob("*")) if (self.dir / "devices").exists() else [], [])


class Restore(DeviceApi):
    def test_round_trip_gives_back_the_same_data(self):
        self.populate()
        doc = self.backup()
        before = self.state()
        self.wipe()
        result = self.restore(doc)
        self.assertGreater(result["added"]["payments"], 0)
        again = self.backup()
        self.assertEqual(again["tables"], doc["tables"])
        self.assertEqual(again["revision"], doc["revision"])
        after = self.state()
        for key in ("opening", "payments", "view", "inbox", "campus", "rewards", "walletLast"):
            with self.subTest(key=key):
                self.assertEqual(after[key], before[key])
        self.assertFalse(after["fresh"])

    def test_restore_into_an_empty_server(self):
        self.populate()
        doc = self.backup()
        self.wipe()
        self.assertTrue(self.state()["fresh"])
        result = self.restore(doc)
        self.assertEqual(result["added"], {"meta": 2, "weeks": 1, "payments": 3, "inbox": 2,
                                           "merchantFunds": 1, "visits": 1, "feedback": 1})
        self.assertFalse(result["state"]["fresh"])
        self.assertEqual(len(result["state"]["payments"]), 2)  # the undone one does not count

    def test_restoring_twice_gives_the_same_result(self):
        self.populate()
        doc = self.backup()
        self.wipe()
        self.restore(doc)
        once = self.backup()
        result = self.restore(doc)
        self.assertEqual(set(result["added"].values()), {0})
        twice = self.backup()
        self.assertEqual(twice["tables"], once["tables"])
        self.assertEqual(twice["revision"], once["revision"])

    def test_merge_keeps_apple_pay_items_that_arrived_after_the_wipe(self):
        self.populate()
        doc = self.backup()
        self.wipe()
        # Paid while the server was empty: it lands in To review with id 1, like a snapshot item.
        self.ok("POST", "/api/shortcut/wallet", {"amount": "HK$55.00", "merchant": "Late shop"})
        self.restore(doc)
        state = self.state()
        merchants = sorted(item["merchant"] for item in state["inbox"])
        self.assertEqual(merchants, ["Late shop", "Shop"])
        tables = self.backup()["tables"]
        self.assertEqual(len(tables["inbox"]), 3)
        self.assertEqual(len({item["id"] for item in tables["inbox"]}), 3)
        # The newer Apple Pay message stays the one Settings shows.
        self.assertIn("Late shop", state["walletLast"]["detail"])
        # And a second restore still adds nothing.
        self.assertEqual(set(self.restore(doc)["added"].values()), {0})

    def test_merge_keeps_rows_the_server_already_has_and_remaps_ids(self):
        self.populate()
        doc = self.backup()
        self.wipe()
        # A payment made on the empty server takes id 1, which the snapshot's lunch also uses.
        self.ok("POST", "/api/settings", FUNDS_TEXT)
        self.ok("POST", "/api/payments", {"amount": "7", "category": "snack", "note": "water"})
        self.restore(doc)
        tables = self.backup()["tables"]
        notes = sorted(p["note"] for p in tables["payments"])
        self.assertEqual(notes, sorted(["water", "lunch", "tea", "Cafe"]))
        lunch = next(p for p in tables["payments"] if p["note"] == "lunch")
        self.assertNotEqual(lunch["id"], 1)
        self.assertEqual([v["paymentId"] for v in tables["visits"]], [lunch["id"]])
        cafe = next(p for p in tables["payments"] if p["note"] == "Cafe")
        confirmed = next(i for i in tables["inbox"] if i["status"] == "confirmed")
        self.assertEqual(confirmed["paymentId"], cafe["id"])
        # The server's own week was kept (same numbers here), and nothing doubles on a second run.
        self.assertEqual(len(tables["weeks"]), 1)
        self.restore(doc)
        self.assertEqual(self.backup()["tables"], tables)

    def test_a_phone_cannot_restore_into_another_phones_data(self):
        self.populate(PHONE)
        doc = self.backup(PHONE)
        error = self.refused("/api/restore", doc, device=OTHER)
        self.assertIn("phone", error.lower())
        self.assertTrue(self.state(OTHER)["fresh"])
        # Restoring its own copy never touches another phone.
        self.populate(OTHER)
        other_before = self.backup(OTHER)["tables"]
        self.restore(doc, PHONE)
        self.assertEqual(self.backup(OTHER)["tables"], other_before)


class Rejected(DeviceApi):
    def setUp(self):
        super().setUp()
        self.populate()
        self.doc = self.backup()
        self.wipe()

    def assert_nothing_written(self):
        self.assertTrue(self.state()["fresh"])
        self.assertEqual(self.backup()["tables"]["payments"], [])

    def resigned(self, doc):
        """A changed document with a matching revision, so the check under test is the one that fails."""
        doc["revision"] = backup.revision(doc["tables"])
        return doc

    def test_wrong_schema_version(self):
        for version in (4, 7, "5", "6", None):
            with self.subTest(version=version):
                doc = copy.deepcopy(self.doc)
                doc["schemaVersion"] = version
                self.assertIn("version", self.refused("/api/restore", doc).lower())
        self.assert_nothing_written()

    def test_money_must_be_integer_cents(self):
        for bad in (48.5, "4850", True, -1, 0, 10 ** 12):
            with self.subTest(amount=bad):
                doc = copy.deepcopy(self.doc)
                doc["tables"]["payments"][-1]["amount"] = bad
                self.refused("/api/restore", self.resigned(doc))
        for path in (("weeks", 0, "main"), ("inbox", 0, "amount")):
            with self.subTest(field=path):
                doc = copy.deepcopy(self.doc)
                doc["tables"][path[0]][path[1]][path[2]] = 100.0
                self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["tables"]["payments"][0]["from"]["main"] = 1.5
        self.refused("/api/restore", self.resigned(doc))
        # A bad last row means nothing at all is written.
        self.assert_nothing_written()

    def test_unknown_tables_and_fields(self):
        doc = copy.deepcopy(self.doc)
        doc["tables"]["accounts"] = []
        self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["tables"]["payments"][0]["extra"] = 1
        self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["tables"]["meta"]["book"] = "demo"
        self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["surprise"] = True
        self.refused("/api/restore", doc)
        doc = copy.deepcopy(self.doc)
        del doc["tables"]["feedback"]
        self.refused("/api/restore", self.resigned(doc))
        self.assert_nothing_written()

    def test_types_and_lengths(self):
        changes = [
            ("payments", 0, "note", "x" * 41),
            ("payments", 0, "note", "<b>"),
            ("payments", 0, "date", "2026-13-45"),
            ("payments", 0, "category", "rent"),
            ("payments", 0, "id", "1"),
            ("payments", 0, "requestId", "short"),
            ("payments", 0, "createdAt", "yesterday"),
            ("inbox", 0, "status", "paid"),
            ("inbox", 0, "source", "bank"),
            ("inbox", 0, "merchant", ""),
            ("weeks", 0, "weekStart", "2027-03-02"),  # not a Monday
            ("visits", 0, "within", 1),
            ("visits", 0, "placeId", "node/abc"),
            ("feedback", 0, "rating", 6),
        ]
        for table, row, field, value in changes:
            with self.subTest(table=table, field=field, value=value):
                doc = copy.deepcopy(self.doc)
                doc["tables"][table][row][field] = value
                self.refused("/api/restore", self.resigned(doc))
        self.assert_nothing_written()

    def test_links_and_duplicates(self):
        doc = copy.deepcopy(self.doc)
        doc["tables"]["visits"][0]["paymentId"] = 999
        self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["tables"]["payments"][1]["id"] = doc["tables"]["payments"][0]["id"]
        self.refused("/api/restore", self.resigned(doc))
        doc = copy.deepcopy(self.doc)
        doc["tables"]["inbox"][1]["externalId"] = doc["tables"]["inbox"][0]["externalId"]
        self.refused("/api/restore", self.resigned(doc))
        self.assert_nothing_written()

    def test_a_damaged_document_is_refused(self):
        doc = copy.deepcopy(self.doc)
        doc["tables"]["payments"][0]["note"] = "changed"
        self.assertIn("damaged", self.refused("/api/restore", doc).lower())
        self.assert_nothing_written()

    def test_not_json_or_not_an_object(self):
        status, data = self.send("POST", "/api/restore", raw=b"[1, 2]")
        self.assertEqual(status, 400, data)
        status, data = self.send("POST", "/api/restore", raw=b"{not json")
        self.assertEqual(status, 400, data)
        self.assert_nothing_written()

    def test_oversized_body(self):
        self.assertGreater(MAX_RESTORE_BODY, MAX_BODY)
        with socket.create_connection(("127.0.0.1", self.port), timeout=10) as sock:
            head = (f"POST /api/restore HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
                    f"X-SSUST-Device: {PHONE}\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {MAX_RESTORE_BODY + 1}\r\n\r\n")
            sock.sendall(head.encode("ascii"))
            answer = b""
            while b"\r\n\r\n" not in answer:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                answer += chunk
        self.assertTrue(answer.startswith(b"HTTP/1.0 400") or answer.startswith(b"HTTP/1.1 400"), answer[:40])
        self.assert_nothing_written()

    def test_other_routes_keep_the_small_body_limit(self):
        big = {"amount": "1", "category": "main", "note": "x" * (MAX_BODY + 10)}
        status, _ = self.send("POST", "/api/payments", big)
        self.assertEqual(status, 400)


class StoreMerge(unittest.TestCase):
    def test_two_equal_payments_without_request_id_stay_two(self):
        import tempfile
        from pathlib import Path
        from ssust.store import Store
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = Store(Path(tmp.name) / "a.db", "live")
        payment = {"date": "2027-03-03", "amount": 500, "category": "snack", "note": "water",
                   "from": {fund: 0 for fund in backup.FUNDS}, "uncovered": 0}
        payment["from"]["snack"] = 500
        with source.session(write=True) as s:
            s.add_payment(payment, created_at="2027-03-03T10:00:00+00:00")
            s.add_payment(payment, created_at="2027-03-03T10:00:00+00:00")
        with source.session() as s:
            tables = s.export_tables(backup.META_KEYS)
        target = Store(Path(tmp.name) / "b.db", "live")
        for _ in range(2):
            with target.session(write=True) as s:
                s.merge_tables(tables)
        with target.session() as s:
            self.assertEqual(s.export_tables(backup.META_KEYS), tables)


class Validate(unittest.TestCase):
    """backup.py checks a document without any database."""

    def empty(self):
        tables = {name: [] for name in backup.TABLES}
        tables["meta"] = {}
        return {"format": backup.FORMAT, "schemaVersion": backup.SCHEMA_VERSION, "device": PHONE,
                "exportedAt": "2027-03-03T10:00:00+00:00", "revision": backup.revision(tables), "tables": tables}

    def test_an_empty_document_is_valid(self):
        self.assertEqual(backup.check(self.empty(), PHONE)["payments"], [])

    def test_revision_ignores_the_export_time(self):
        doc = self.empty()
        doc["exportedAt"] = "2030-01-01T00:00:00+00:00"
        backup.check(doc, PHONE)

    def test_meta_values_are_checked(self):
        for key, value in (("campus", "mit"), ("connected", "{not json"), ("connected", '{"apple_pay": 1}'),
                           ("wallet_last", "[]"), ("mode", "demo")):
            with self.subTest(key=key):
                doc = self.empty()
                doc["tables"]["meta"] = {key: value}
                doc["revision"] = backup.revision(doc["tables"])
                with self.assertRaises(ValueError):
                    backup.check(doc, PHONE)

    def test_too_many_rows(self):
        doc = self.empty()
        doc["tables"]["feedback"] = [{"id": i + 1, "rating": 3, "text": "", "createdAt": "2027-03-03T10:00:00+00:00"}
                                     for i in range(backup.MAX_ROWS + 1)]
        doc["revision"] = backup.revision(doc["tables"])
        with self.assertRaises(ValueError):
            backup.check(doc, PHONE)


if __name__ == "__main__":
    unittest.main()
