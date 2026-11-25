"""The backup document of one phone: its shape, strict checks and revision. Pure, no I/O.

The iPhone app keeps a copy of this document on the phone. When the hosting platform wipes the
server's disk, the app sends it back (POST /api/restore) and store.Session.merge_tables rebuilds
the data. Every amount is integer cents.

    {"format": "ssust-backup", "schemaVersion": 5, "device": "<32 hex>",
     "exportedAt": "2027-03-03T10:00:00+00:00", "revision": "<sha256 hex>",
     "tables": {"meta": {...}, "weeks": [...], "payments": [...], "inbox": [...],
                "merchantFunds": [...], "visits": [...], "feedback": [...]}}

The revision is a hash of the tables only (not the export time): the same data gives the same
revision, and a document changed after export is refused. Error messages never quote the data.
"""

import hashlib
import json
import re
from datetime import datetime

from . import places
from .dates import parse_day, week_dates
from .money import CATEGORIES, FUNDS
from .store import INBOX_SOURCES, INBOX_STATUSES, REQUEST_ID, SCHEMA_VERSION, WALLET_SOURCE, merchant_key
from .validate import MAX_CENTS, clean_note

FORMAT = "ssust-backup"
SUPPORTED_VERSIONS = (SCHEMA_VERSION,)
TABLES = ("meta", "weeks", "payments", "inbox", "merchantFunds", "visits", "feedback")
META_KEYS = ("campus", "connected", "wallet_last")
MAX_ROWS = 10_000  # per table; the request size limit (server.MAX_RESTORE_BODY) comes first in practice
MAX_META_CHARS = 2000
MAX_ID = 2 ** 63 - 1
FEEDBACK_CHARS = 500
MERCHANT_CHARS = 80
TIMESTAMP_CHARS = 40
HEX64 = re.compile(r"[0-9a-f]{64}")
DEVICE_ID = re.compile(r"[0-9a-f]{32}")
PLACE_ID = re.compile(r"(node|way|relation)/[0-9]{1,20}")  # the same rule as service._place

_TOP = {"format", "schemaVersion", "device", "exportedAt", "revision", "tables"}
_PAYMENT = {"id", "date", "amount", "category", "note", "from", "uncovered", "createdAt", "requestId", "voidedAt"}
_INBOX = {"id", "externalId", "source", "amount", "merchant", "card", "receivedAt", "status", "paymentId"}
_WEEK = {"weekStart", *FUNDS}


class Invalid(ValueError):
    """The document cannot be restored. The message is safe to show and names no data."""


def revision(tables):
    """sha256 of the tables in canonical JSON (sorted keys, no spaces)."""
    text = json.dumps(tables, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def document(tables, device, exported_at):
    return {"format": FORMAT, "schemaVersion": SCHEMA_VERSION, "device": device, "exportedAt": exported_at,
            "revision": revision(tables), "tables": tables}


# field checks: each raises Invalid naming the place, never the value
def _fail(where, what):
    raise Invalid(f"Backup {where}: {what}.")


def _keys(row, expected, where):
    if not isinstance(row, dict) or set(row) != expected:
        _fail(where, "unexpected or missing fields")


def _id(value, where):
    if type(value) is not int or not 1 <= value <= MAX_ID:
        _fail(where, "bad id")
    return value


def _cents(value, where, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_CENTS:
        _fail(where, "money must be whole cents")
    return value


def _timestamp(value, where, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not 0 < len(value) <= TIMESTAMP_CHARS:
        _fail(where, "bad time")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        _fail(where, "bad time")
    return value


def _day(value, where):
    try:
        if parse_day(value).isoformat() != value:
            raise ValueError
    except (ValueError, TypeError):
        _fail(where, "bad date")
    return value


def _clean(value, where, required=True):
    """Text exactly as the app stores it (clean_note: printable, no < >, trimmed, at most 40)."""
    if not isinstance(value, str) or clean_note(value) != value or (required and not value):
        _fail(where, "bad text")
    return value


def _choice(value, allowed, where):
    if not isinstance(value, str) or value not in allowed:
        _fail(where, "unknown value")
    return value


def _rows(tables, name):
    rows = tables[name]
    if not isinstance(rows, list):
        _fail(name, "must be a list")
    if len(rows) > MAX_ROWS:
        _fail(name, "too many rows")
    return rows


def _unique(values, where):
    seen = set()
    for value in values:
        if value in seen:
            _fail(where, "duplicate")
        seen.add(value)


def _meta(meta):
    if not isinstance(meta, dict) or not set(meta) <= set(META_KEYS):
        _fail("meta", "unknown keys")
    for key, value in meta.items():
        where = f"meta {key}"
        if not isinstance(value, str) or len(value) > MAX_META_CHARS:
            _fail(where, "bad text")
        if key == "campus" and value not in places.CAMPUSES:
            _fail(where, "unknown campus")
        if key in ("connected", "wallet_last"):
            try:
                parsed = json.loads(value)
            except ValueError:
                _fail(where, "bad value")
            if not isinstance(parsed, dict):
                _fail(where, "bad value")
            if key == "connected" and not (set(parsed) <= set(INBOX_SOURCES)
                                           and all(type(on) is bool for on in parsed.values())):
                _fail(where, "bad value")


def _week(row, where):
    _keys(row, _WEEK, where)
    try:
        week_dates(row["weekStart"])
    except (ValueError, TypeError):
        _fail(where, "a week starts on a Monday")
    for fund in FUNDS:
        _cents(row[fund], where)


def _payment(row, where):
    _keys(row, _PAYMENT, where)
    _id(row["id"], where)
    _day(row["date"], where)
    _cents(row["amount"], where, minimum=1)
    _choice(row["category"], CATEGORIES, where)
    _clean(row["note"], where, required=False)
    _keys(row["from"], set(FUNDS), where)
    for fund in FUNDS:
        _cents(row["from"][fund], where)
    _cents(row["uncovered"], where)
    _timestamp(row["createdAt"], where)
    if row["requestId"] is not None and not (isinstance(row["requestId"], str)
                                             and REQUEST_ID.fullmatch(row["requestId"])):
        _fail(where, "bad request id")
    _timestamp(row["voidedAt"], where, optional=True)


def _inbox(row, where, payment_ids):
    _keys(row, _INBOX, where)
    _id(row["id"], where)
    if not isinstance(row["externalId"], str) or not REQUEST_ID.fullmatch(row["externalId"]):
        _fail(where, "bad external id")
    _choice(row["source"], (*INBOX_SOURCES, WALLET_SOURCE), where)
    _cents(row["amount"], where, minimum=1)
    _clean(row["merchant"], where)
    _clean(row["card"], where)
    _timestamp(row["receivedAt"], where)
    _choice(row["status"], INBOX_STATUSES, where)
    if row["paymentId"] is not None and (type(row["paymentId"]) is not int or row["paymentId"] not in payment_ids):
        _fail(where, "links to a missing payment")


def _merchant_fund(row, where):
    _keys(row, {"merchant", "fund"}, where)
    merchant = row["merchant"]
    if (not isinstance(merchant, str) or not 0 < len(merchant) <= MERCHANT_CHARS
            or merchant_key(merchant) != merchant or any(ch in "<>" for ch in merchant)):
        _fail(where, "bad merchant")
    _choice(row["fund"], CATEGORIES, where)


def _visit(row, where, payment_ids):
    _keys(row, {"paymentId", "campus", "placeId", "name", "within"}, where)
    if type(row["paymentId"]) is not int or row["paymentId"] not in payment_ids:
        _fail(where, "links to a missing payment")
    _choice(row["campus"], places.CAMPUSES, where)
    if not isinstance(row["placeId"], str) or not PLACE_ID.fullmatch(row["placeId"]):
        _fail(where, "bad place")
    _clean(row["name"], where)
    if type(row["within"]) is not bool:
        _fail(where, "bad value")


def _feedback(row, where):
    _keys(row, {"id", "rating", "text", "createdAt"}, where)
    _id(row["id"], where)
    if type(row["rating"]) is not int or not 1 <= row["rating"] <= 5:
        _fail(where, "bad rating")
    text = row["text"]
    if (not isinstance(text, str) or len(text) > FEEDBACK_CHARS or text != text.strip()
            or any(not (ch.isprintable() or ch == "\n") or ch in "<>" for ch in text)):
        _fail(where, "bad text")
    _timestamp(row["createdAt"], where)


def check(doc, device):
    """The tables of a backup document for `device`, every row checked. Raises Invalid."""
    if not isinstance(doc, dict) or set(doc) != _TOP or doc.get("format") != FORMAT:
        raise Invalid("This is not an SSUST backup.")
    version = doc["schemaVersion"]
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        raise Invalid("This backup's version is not supported by the server.")
    if not isinstance(doc["device"], str) or not DEVICE_ID.fullmatch(doc["device"]) or doc["device"] != device:
        raise Invalid("This backup belongs to another phone.")
    _timestamp(doc["exportedAt"], "time")
    if not isinstance(doc["revision"], str) or not HEX64.fullmatch(doc["revision"]):
        raise Invalid("This backup is damaged.")
    tables = doc["tables"]
    if not isinstance(tables, dict) or set(tables) != set(TABLES):
        raise Invalid("Backup tables: unexpected or missing tables.")

    _meta(tables["meta"])
    weeks = _rows(tables, "weeks")
    for n, row in enumerate(weeks, 1):
        _week(row, f"weeks row {n}")
    _unique((row["weekStart"] for row in weeks), "weeks")

    payments = _rows(tables, "payments")
    for n, row in enumerate(payments, 1):
        _payment(row, f"payments row {n}")
    _unique((row["id"] for row in payments), "payments ids")
    _unique((row["requestId"] for row in payments if row["requestId"] is not None), "payments request ids")
    payment_ids = {row["id"] for row in payments}

    inbox = _rows(tables, "inbox")
    for n, row in enumerate(inbox, 1):
        _inbox(row, f"inbox row {n}", payment_ids)
    _unique((row["id"] for row in inbox), "inbox ids")
    _unique((row["externalId"] for row in inbox), "inbox external ids")

    funds = _rows(tables, "merchantFunds")
    for n, row in enumerate(funds, 1):
        _merchant_fund(row, f"merchantFunds row {n}")
    _unique((row["merchant"] for row in funds), "merchantFunds")

    visits = _rows(tables, "visits")
    for n, row in enumerate(visits, 1):
        _visit(row, f"visits row {n}", payment_ids)
    _unique((row["paymentId"] for row in visits), "visits")

    feedback = _rows(tables, "feedback")
    for n, row in enumerate(feedback, 1):
        _feedback(row, f"feedback row {n}")
    _unique((row["id"] for row in feedback), "feedback ids")

    if revision(tables) != doc["revision"]:
        raise Invalid("This backup is damaged.")
    return tables
