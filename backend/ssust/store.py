"""SQLite storage. Every amount is integer cents.

Live and demo data live in two separate database files (`open_books`).
Each file records which book it holds, so one can't be opened as the other.
Use one session per request:

    with store.session(write=True) as s:
        s.set_week("2026-11-09", amounts)

A write session runs inside BEGIN IMMEDIATE, so plan-then-insert is atomic.
"""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .dates import parse_day, week_dates
from .money import CATEGORIES, FUNDS
from .validate import MAX_CENTS

SCHEMA_VERSION = 5
BOOKS = ("live", "demo")
MODES = ("live", "demo")
LIVE_FILE = "ssust.db"
DEMO_FILE = "ssust-demo.db"
_RESERVED_META = frozenset({"book"})
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
INBOX_SOURCES = ("apple_pay", "octopus", "hsbc")
INBOX_STATUSES = ("pending", "confirmed", "dismissed")


def _cents_column(name, minimum=0):
    return f"{name} INTEGER NOT NULL CHECK (typeof({name}) = 'integer' AND {name} >= {minimum})"


_SCHEMA_V1 = [
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE weeks (week_start TEXT PRIMARY KEY, "
    + ", ".join(_cents_column(fund) for fund in FUNDS)
    + ")",
    "CREATE TABLE payments (id INTEGER PRIMARY KEY, date TEXT NOT NULL, "
    + _cents_column("amount", 1)
    + ", category TEXT NOT NULL, note TEXT NOT NULL, "
    + ", ".join(_cents_column(f"from_{fund}") for fund in FUNDS)
    + ", " + _cents_column("uncovered")
    + ", created_at TEXT NOT NULL)",
    "CREATE INDEX payments_by_date ON payments (date, id)",
]

# Version 2: an optional client request id per payment, unique, so a repeated submit saves once.
_SCHEMA_V2 = [
    "ALTER TABLE payments ADD COLUMN request_id TEXT",
    "CREATE UNIQUE INDEX payments_by_request ON payments (request_id)",
]

# Version 3: undo. An undone payment keeps its row (and request id) but is voided and no longer counts.
_SCHEMA_V3 = [
    "ALTER TABLE payments ADD COLUMN voided_at TEXT",
]


# Version 4: an inbox of incoming payments to review (simulated in the demo), idempotent by an
# external id, and the fund last chosen per merchant (pre-selected next time).
_SCHEMA_V4 = [
    "CREATE TABLE inbox (id INTEGER PRIMARY KEY, external_id TEXT NOT NULL UNIQUE, source TEXT NOT NULL, "
    + _cents_column("amount_cents", 1)
    + ", merchant TEXT NOT NULL, card TEXT NOT NULL, received_at TEXT NOT NULL, "
    "status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'dismissed')), "
    "payment_id INTEGER)",
    "CREATE INDEX inbox_by_status ON inbox (status, id)",
    "CREATE TABLE merchant_funds (merchant TEXT PRIMARY KEY, fund TEXT NOT NULL)",
]

# Version 5: a meal logged at a map place (one row per payment; `within` = it fit that day's food
# money, which is what the campus medals count), and the app feedback people send.
_SCHEMA_V5 = [
    "CREATE TABLE visits (payment_id INTEGER PRIMARY KEY, campus TEXT NOT NULL, place_id TEXT NOT NULL, "
    "name TEXT NOT NULL, within INTEGER NOT NULL CHECK (within IN (0, 1)))",
    "CREATE TABLE feedback (id INTEGER PRIMARY KEY, rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5), "
    "text TEXT NOT NULL, created_at TEXT NOT NULL)",
]


def _merchant_key(merchant):
    return " ".join(str(merchant).split()).casefold()


def _cents(value, what, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_CENTS:
        raise ValueError(f"{what} must be whole cents between {minimum} and {MAX_CENTS}.")
    return value


def _amounts(amounts, what):
    if not isinstance(amounts, dict) or set(amounts) != set(FUNDS):
        raise ValueError(f"{what} needs exactly these funds: {', '.join(FUNDS)}.")
    return {fund: _cents(amounts[fund], f"{what} {fund}") for fund in FUNDS}


def _monday(day):
    week_dates(day)  # raises ValueError unless it is a Monday
    return day


class Store:
    """One database file holding one book ("live" or "demo")."""

    def __init__(self, path, book):
        if book not in BOOKS:
            raise ValueError(f"Unknown book: {book!r}.")
        self.path = Path(path)
        self.book = book
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction(write=True) as con:
            self._migrate(con)
            row = con.execute("SELECT value FROM meta WHERE key = 'book'").fetchone()
            if row is None:
                con.execute("INSERT INTO meta (key, value) VALUES ('book', ?)", (book,))
            elif row[0] != book:
                raise ValueError(f"{self.path} holds the {row[0]} book, not {book}.")

    @staticmethod
    def _migrate(con):
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"Database schema {version} is newer than this app ({SCHEMA_VERSION}).")
        if version < 1:
            for statement in _SCHEMA_V1:
                con.execute(statement)
            con.execute("PRAGMA user_version = 1")
        if version < 2:
            for statement in _SCHEMA_V2:
                con.execute(statement)
            con.execute("PRAGMA user_version = 2")
        if version < 3:
            for statement in _SCHEMA_V3:
                con.execute(statement)
            con.execute("PRAGMA user_version = 3")
        if version < 4:
            for statement in _SCHEMA_V4:
                con.execute(statement)
            con.execute("PRAGMA user_version = 4")
        if version < 5:
            for statement in _SCHEMA_V5:
                con.execute(statement)
            con.execute("PRAGMA user_version = 5")

    @contextmanager
    def _transaction(self, write):
        con = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        try:
            con.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield con
            except BaseException:
                con.execute("ROLLBACK")
                raise
            con.execute("COMMIT")
        finally:
            con.close()

    @contextmanager
    def session(self, write=False):
        with self._transaction(write) as con:
            yield Session(con, self.book, write)


def open_books(data_dir):
    """The live and demo stores, as two files in `data_dir`."""
    folder = Path(data_dir)
    return {"live": Store(folder / LIVE_FILE, "live"), "demo": Store(folder / DEMO_FILE, "demo")}


class Session:
    def __init__(self, con, book, write):
        self._con = con
        self.book = book
        self._write = write

    def _writing(self):
        if not self._write:
            raise PermissionError("This session is read-only.")

    # meta
    def get_meta(self, key):
        row = self._con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row[0]

    def set_meta(self, key, value):
        self._writing()
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Meta keys and values are text.")
        if key in _RESERVED_META:
            raise ValueError(f"{key!r} is reserved.")
        self._con.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_mode(self):
        return self.get_meta("mode") or "live"

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode!r}.")
        self.set_meta("mode", mode)

    # weeks
    def get_week(self, week_start):
        row = self._con.execute(
            f"SELECT {', '.join(FUNDS)} FROM weeks WHERE week_start = ?", (_monday(week_start),)
        ).fetchone()
        return None if row is None else dict(zip(FUNDS, row))

    def set_week(self, week_start, amounts):
        self._writing()
        start = _monday(week_start)
        clean = _amounts(amounts, "Opening")
        columns = ", ".join(FUNDS)
        updates = ", ".join(f"{fund} = excluded.{fund}" for fund in FUNDS)
        self._con.execute(
            f"INSERT INTO weeks (week_start, {columns}) VALUES (?{', ?' * len(FUNDS)}) "
            f"ON CONFLICT(week_start) DO UPDATE SET {updates}",
            (start, *(clean[fund] for fund in FUNDS)),
        )

    def weeks(self):
        return [row[0] for row in self._con.execute("SELECT week_start FROM weeks ORDER BY week_start")]

    def previous_week(self, week_start):
        """(week_start, amounts) of the latest week before `week_start`, or None."""
        row = self._con.execute(
            f"SELECT week_start, {', '.join(FUNDS)} FROM weeks WHERE week_start < ? "
            "ORDER BY week_start DESC LIMIT 1",
            (_monday(week_start),),
        ).fetchone()
        return None if row is None else (row[0], dict(zip(FUNDS, row[1:])))

    # payments
    def add_payment(self, payment, created_at=None, request_id=None):
        """Save a payment in the money.py shape and return its id.

        `request_id` (optional, 8 to 64 of A-Z a-z 0-9 _ -) is unique: a second insert raises IntegrityError.
        """
        self._writing()
        if request_id is not None and not (isinstance(request_id, str) and REQUEST_ID.fullmatch(request_id)):
            raise ValueError("A request id is 8 to 64 letters, digits, - or _.")
        if not isinstance(payment, dict):
            raise ValueError("A payment is a dict.")
        try:
            day = parse_day(payment.get("date")).isoformat()
        except ValueError:
            raise ValueError("A payment needs a date like 2026-11-11.") from None
        amount = _cents(payment.get("amount"), "Amount", minimum=1)
        category = payment.get("category")
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}.")
        note = payment.get("note", "")
        if not isinstance(note, str):
            raise ValueError("The note is text.")
        taken = _amounts(payment.get("from"), "From")
        uncovered = _cents(payment.get("uncovered", 0), "Uncovered")
        stamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        columns = ", ".join(f"from_{fund}" for fund in FUNDS)
        cursor = self._con.execute(
            f"INSERT INTO payments (date, amount, category, note, {columns}, uncovered, created_at, request_id) "
            f"VALUES (?, ?, ?, ?{', ?' * len(FUNDS)}, ?, ?, ?)",
            (day, amount, category, note, *(taken[fund] for fund in FUNDS), uncovered, stamp, request_id),
        )
        return cursor.lastrowid

    def _rows(self, where, params, with_void=False):
        columns = ", ".join(f"from_{fund}" for fund in FUNDS)
        rows = self._con.execute(
            f"SELECT id, date, amount, category, note, {columns}, uncovered, created_at, voided_at FROM payments "
            f"WHERE {where} ORDER BY date, id",
            params,
        ).fetchall()
        n = len(FUNDS)
        out = []
        for row in rows:
            item = {
                "id": row[0],
                "date": row[1],
                "amount": row[2],
                "category": row[3],
                "note": row[4],
                "from": dict(zip(FUNDS, row[5:5 + n])),
                "uncovered": row[5 + n],
                "createdAt": row[6 + n],
            }
            if with_void:
                item["voidedAt"] = row[7 + n]
            out.append(item)
        return out

    def payment_by_request(self, request_id):
        """The payment saved with `request_id` (even if it was undone since), or None."""
        found = self._rows("request_id = ?", (request_id,), with_void=True)
        return found[0] if found else None

    def get_payment(self, payment_id):
        """One payment by id, with "voidedAt" (None unless undone), or None."""
        found = self._rows("id = ?", (payment_id,), with_void=True)
        return found[0] if found else None

    def void_payment(self, payment_id, voided_at=None):
        """Undo a payment: it stays in the file but no longer counts. False if it was already void or missing."""
        self._writing()
        stamp = voided_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = self._con.execute(
            "UPDATE payments SET voided_at = ? WHERE id = ? AND voided_at IS NULL", (stamp, payment_id))
        return cursor.rowcount == 1

    def payments(self, week_start):
        """Payments dated inside the week, oldest first. Undone payments are left out."""
        days = week_dates(week_start)
        return self._rows("date BETWEEN ? AND ? AND voided_at IS NULL", (days[0], days[-1]))

    # inbox
    def add_inbox(self, item):
        """Add an incoming payment. Returns (id, created): the same external id is stored once."""
        self._writing()
        external = item.get("externalId")
        if not (isinstance(external, str) and REQUEST_ID.fullmatch(external)):
            raise ValueError("An external id is 8 to 64 letters, digits, - or _.")
        found = self._con.execute("SELECT id FROM inbox WHERE external_id = ?", (external,)).fetchone()
        if found:
            return found[0], False
        if item.get("source") not in INBOX_SOURCES:
            raise ValueError("Unknown payment source.")
        amount = _cents(item.get("amount"), "Amount", minimum=1)
        texts = [item.get(key) for key in ("merchant", "card", "receivedAt")]
        if not all(isinstance(text, str) and text for text in texts):
            raise ValueError("Merchant, card and time are text.")
        cursor = self._con.execute(
            "INSERT INTO inbox (external_id, source, amount_cents, merchant, card, received_at) VALUES (?, ?, ?, ?, ?, ?)",
            (external, item["source"], amount, *texts))
        return cursor.lastrowid, True

    def _inbox_rows(self, where, params):
        rows = self._con.execute(
            "SELECT id, external_id, source, amount_cents, merchant, card, received_at, status, payment_id "
            f"FROM inbox WHERE {where} ORDER BY id", params).fetchall()
        keys = ("id", "externalId", "source", "amount", "merchant", "card", "receivedAt", "status", "paymentId")
        return [dict(zip(keys, row)) for row in rows]

    def get_inbox(self, item_id):
        found = self._inbox_rows("id = ?", (item_id,))
        return found[0] if found else None

    def inbox(self, status="pending"):
        if status not in INBOX_STATUSES:
            raise ValueError("Unknown inbox status.")
        return self._inbox_rows("status = ?", (status,))

    def set_inbox_status(self, item_id, status, payment_id=None):
        """Confirm or dismiss a pending item. False if it is missing or already handled."""
        self._writing()
        if status not in ("confirmed", "dismissed"):
            raise ValueError("Unknown inbox status.")
        cursor = self._con.execute(
            "UPDATE inbox SET status = ?, payment_id = ? WHERE id = ? AND status = 'pending'",
            (status, payment_id, item_id))
        return cursor.rowcount == 1

    def merchant_fund(self, merchant):
        row = self._con.execute("SELECT fund FROM merchant_funds WHERE merchant = ?", (_merchant_key(merchant),)).fetchone()
        return None if row is None else row[0]

    def remember_merchant_fund(self, merchant, fund):
        self._writing()
        if fund not in CATEGORIES:
            raise ValueError(f"Unknown category: {fund!r}.")
        self._con.execute(
            "INSERT INTO merchant_funds (merchant, fund) VALUES (?, ?) "
            "ON CONFLICT(merchant) DO UPDATE SET fund = excluded.fund", (_merchant_key(merchant), fund))

    def payment_dates(self):
        """Every day with at least one payment that still counts, oldest first."""
        rows = self._con.execute("SELECT DISTINCT date FROM payments WHERE voided_at IS NULL ORDER BY date")
        return [row[0] for row in rows]

    def payment_count(self):
        return self._con.execute("SELECT COUNT(*) FROM payments WHERE voided_at IS NULL").fetchone()[0]

    # meals logged at a place (campus medals)
    def add_visit(self, payment_id, campus, place_id, name, within):
        """Record that payment `payment_id` was a meal at a map place. Once per payment."""
        self._writing()
        self._con.execute(
            "INSERT OR IGNORE INTO visits (payment_id, campus, place_id, name, within) VALUES (?, ?, ?, ?, ?)",
            (payment_id, campus, place_id, name, 1 if within else 0))

    def visit_counts(self):
        """{campus: different places with a meal that fit that day's money}, undone payments left out."""
        rows = self._con.execute(
            "SELECT v.campus, COUNT(DISTINCT v.place_id) FROM visits v JOIN payments p ON p.id = v.payment_id "
            "WHERE v.within = 1 AND p.voided_at IS NULL GROUP BY v.campus")
        return {campus: count for campus, count in rows}

    # feedback about the app
    def add_feedback(self, rating, text, created_at=None):
        self._writing()
        stamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = self._con.execute("INSERT INTO feedback (rating, text, created_at) VALUES (?, ?, ?)",
                                   (rating, text, stamp))
        return cursor.lastrowid

    def feedback(self, limit=20):
        """The latest feedback, newest first."""
        rows = self._con.execute("SELECT id, rating, text, created_at FROM feedback ORDER BY id DESC LIMIT ?",
                                 (limit,))
        return [{"id": r[0], "rating": r[1], "text": r[2], "createdAt": r[3]} for r in rows]

    # demo
    def reset(self):
        """Delete every week and payment. Only the demo book can be reset."""
        self._writing()
        if self.book != "demo":
            raise PermissionError("Only the demo book can be reset.")
        self._con.execute("DELETE FROM payments")
        self._con.execute("DELETE FROM weeks")
        self._con.execute("DELETE FROM inbox")
        self._con.execute("DELETE FROM merchant_funds")
        self._con.execute("DELETE FROM visits")
        self._con.execute("DELETE FROM feedback")
