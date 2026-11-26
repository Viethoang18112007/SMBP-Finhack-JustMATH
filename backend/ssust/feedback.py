"""Private feedback: students send it, only the team reads it.

    box = FeedbackBox(data_dir / FEEDBACK_FILE)
    box.add(rating=4, message="Nice", screen="settings")   # -> id
    box.all()                                              # team only (admin route, CSV export)

Stored per entry: id, created_at (UTC), rating (1-5 or none), message (<= 500 characters, or
empty), screen (from SCREENS), an optional context id (a receipt, insight or recipe id), the app
version, and an optional anonymous device id (32 random hex characters made by the browser). No
name, e-mail, IP address or account. The file is separate from the budget books, so it never
changes their schema and is shared by Live and Demo.

Reading is for the team only: the server exposes it at GET /api/admin/feedback when the
SSUST_ADMIN_TOKEN environment variable is set, and checks the token with hmac.compare_digest.
"""

import csv
import hmac
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

APP_VERSION = __version__
FEEDBACK_FILE = "feedback.db"
TOKEN_ENV = "SSUST_ADMIN_TOKEN"
MAX_MESSAGE = 500
MAX_ROWS = 20000  # a full box refuses more instead of growing without limit
SCREENS = ("today", "map", "week", "day", "settings", "add", "home", "groceries", "receipt", "insight", "budget",
           "feedback", "other")
# "text" is the field name of the first app builds (iPhone app on TestFlight): read as "message".
REQUEST_KEYS = frozenset({"rating", "message", "text", "screen", "contextId", "deviceId"})
_CONTEXT = re.compile(r"[A-Za-z0-9_.:/-]{1,64}")
_DEVICE = re.compile(r"[0-9a-f]{32}")
COLUMNS = ("id", "created_at", "rating", "message", "screen", "context_id", "app_version", "device_id")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    rating INTEGER CHECK (rating IS NULL OR (typeof(rating) = 'integer' AND rating BETWEEN 1 AND 5)),
    message TEXT NOT NULL CHECK (length(message) <= 500),
    screen TEXT NOT NULL,
    context_id TEXT,
    app_version TEXT NOT NULL,
    device_id TEXT,
    CHECK (rating IS NOT NULL OR length(message) > 0)
)
"""


class FeedbackError(ValueError):
    """Feedback the server refuses. The message is safe to show."""


def clean_message(raw):
    """The message as stored: newlines kept, tabs as spaces, other control characters removed."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise FeedbackError("The message must be text.")
    if len(raw) > MAX_MESSAGE * 2:
        raise FeedbackError(f"Keep the message under {MAX_MESSAGE} characters.")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = "".join(ch for ch in text if ch == "\n" or ch.isprintable()).strip()
    if len(text) > MAX_MESSAGE:
        raise FeedbackError(f"Keep the message under {MAX_MESSAGE} characters.")
    return text


def check_entry(rating, message, screen, context_id=None, device_id=None):
    """The validated fields, or FeedbackError."""
    if rating is not None and (type(rating) is not int or not 1 <= rating <= 5):
        raise FeedbackError("A rating is a whole number from 1 to 5.")
    message = clean_message(message)
    if rating is None and not message:
        raise FeedbackError("Pick a rating or write a message.")
    if screen not in SCREENS:
        raise FeedbackError("Unknown screen.")
    if context_id is not None and (not isinstance(context_id, str) or not _CONTEXT.fullmatch(context_id)):
        raise FeedbackError("Unknown context.")
    if device_id is not None and (not isinstance(device_id, str) or not _DEVICE.fullmatch(device_id)):
        raise FeedbackError("Unknown device id.")
    return {"rating": rating, "message": message, "screen": screen, "context_id": context_id, "device_id": device_id}


def parse_request(data):
    """A POST /api/feedback body ({rating, message, screen, contextId, deviceId}) as add() arguments."""
    if not isinstance(data, dict) or set(data) - REQUEST_KEYS or ("text" in data and "message" in data):
        raise FeedbackError("Unknown feedback fields.")
    message = data.get("message", data.get("text"))
    return check_entry(data.get("rating"), message, data.get("screen", "feedback"), data.get("contextId"),
                       data.get("deviceId"))


def token_ok(expected, header):
    """True only for "Authorization: Bearer <expected>", compared in constant time."""
    if not expected or not isinstance(header, str) or not header.startswith("Bearer "):
        return False
    given = header[len("Bearer "):]
    if not given:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def _row(row):
    return {"id": row[0], "createdAt": row[1], "rating": row[2], "message": row[3], "screen": row[4],
            "contextId": row[5], "appVersion": row[6], "deviceId": row[7]}


class FeedbackBox:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.execute(_SCHEMA)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def add(self, rating, message, screen, context_id=None, device_id=None):
        entry = check_entry(rating, message, screen, context_id, device_id)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] >= MAX_ROWS:
                raise FeedbackError("Feedback is full for now. Thanks for trying.")
            cur = con.execute(
                "INSERT INTO feedback (created_at, rating, message, screen, context_id, app_version, device_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (created, entry["rating"], entry["message"], entry["screen"], entry["context_id"], APP_VERSION,
                 entry["device_id"]))
            return cur.lastrowid

    def all(self):
        """Every entry, newest first. Team only."""
        with closing(self._connect()) as con:
            return [_row(r) for r in con.execute(f"SELECT {', '.join(COLUMNS)} FROM feedback ORDER BY id DESC")]

    def count(self):
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]


def _safe_cell(value):
    """A spreadsheet must never run a cell as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return "" if value is None else value


def export_csv(db_path, out_path):
    """Write every entry (newest first) to `out_path` as CSV; returns how many. A missing
    database writes the header only and creates nothing."""
    db_path = Path(db_path)
    rows = FeedbackBox(db_path).all() if db_path.is_file() else []
    keys = ("id", "createdAt", "rating", "message", "screen", "contextId", "appVersion", "deviceId")
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([_safe_cell(row[key]) for key in keys])
    return len(rows)
