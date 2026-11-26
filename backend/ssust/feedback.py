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

Where it is kept: feedback is the only thing that leaves a local SSUST. A local server (run.py)
sends each entry to the central feedback server (DEFAULT_HUB, the hosted serve.py) with Relay,
server to server, and keeps it in a local outbox (same file) until that server has it. The
central server (serve.py, no feedback URL) keeps it in its own box. The budget, payments and every
other data stay in the local data folder.
"""

import csv
import hmac
import json
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

APP_VERSION = __version__
FEEDBACK_FILE = "feedback.db"
TOKEN_ENV = "SSUST_ADMIN_TOKEN"
# Where a local SSUST sends feedback (run.py; "local" keeps it here). serve.py keeps it by default.
URL_ENV = "SSUST_FEEDBACK_URL"
DEFAULT_HUB = "https://ssust-api.onrender.com/api/feedback"
# A small online database (Supabase) as the receiver: docs/FEEDBACK_DATABASE.md. Its URL and its
# public insert-only key come from SSUST_FEEDBACK_URL / SSUST_FEEDBACK_KEY, else from this file.
KEY_ENV = "SSUST_FEEDBACK_KEY"
HUB_CONFIG = Path(__file__).resolve().parent / "data" / "feedback_hub.json"
DATABASE_TABLE = "feedback"
RELAY_TIMEOUT = 8  # seconds per attempt
MAX_OUTBOX = 500  # feedback waiting for the central server, at most
MAX_MESSAGE = 500
MAX_ROWS = 20000  # a full box refuses more instead of growing without limit
SCREENS = ("today", "map", "week", "day", "settings", "add", "home", "groceries", "receipt", "insight", "budget",
           "feedback", "other")
# "text" is the field name of the first app builds (iPhone app on TestFlight): read as "message".
# "appVersion" comes from a local SSUST that relays its users' feedback to the central server.
REQUEST_KEYS = frozenset({"rating", "message", "text", "screen", "contextId", "deviceId", "appVersion"})
_VERSION = re.compile(r"[0-9A-Za-z.+-]{1,20}")
_CONTEXT = re.compile(r"[A-Za-z0-9_.:/-]{1,64}")
_DEVICE = re.compile(r"[0-9a-f]{32}")
COLUMNS = ("id", "created_at", "rating", "message", "screen", "context_id", "app_version", "device_id")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (length(payload) <= 4000)
);
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
    entry = check_entry(data.get("rating"), message, data.get("screen", "feedback"), data.get("contextId"),
                        data.get("deviceId"))
    version = data.get("appVersion")
    if version is not None:
        if not isinstance(version, str) or not _VERSION.fullmatch(version):
            raise FeedbackError("Unknown app version.")
        entry["app_version"] = version
    return entry


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
            con.executescript(_SCHEMA)

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def add(self, rating, message, screen, context_id=None, device_id=None, app_version=None):
        entry = check_entry(rating, message, screen, context_id, device_id)
        if app_version is not None and (not isinstance(app_version, str) or not _VERSION.fullmatch(app_version)):
            raise FeedbackError("Unknown app version.")
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] >= MAX_ROWS:
                raise FeedbackError("Feedback is full for now. Thanks for trying.")
            cur = con.execute(
                "INSERT INTO feedback (created_at, rating, message, screen, context_id, app_version, device_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (created, entry["rating"], entry["message"], entry["screen"], entry["context_id"],
                 app_version or APP_VERSION, entry["device_id"]))
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


def hub_url(value):
    """A feedback server URL from a setting: None for "local", "off" or empty; else https only."""
    text = (value or "").strip()
    if text.lower() in ("", "local", "off", "none"):
        return None
    if not text.startswith("https://") or any(ch.isspace() for ch in text) or len(text) > 300:
        raise ValueError(f"the feedback server must be an https:// URL (or local), not {text[:80]!r}")
    return text


def is_database(url):
    """True for a Supabase project URL (rows go to its REST API), False for an SSUST server."""
    host = (url or "").split("://", 1)[-1].split("/", 1)[0].lower()
    return host.endswith(".supabase.co")


def default_target(env=None):
    """(url, key) where feedback goes by default: the environment, else data/feedback_hub.json,
    else the hosted SSUST server. ("local" in the environment: (None, None), kept here.)"""
    import os
    env = os.environ if env is None else env
    if env.get(URL_ENV, "").strip():
        url = hub_url(env[URL_ENV])
        return url, (env.get(KEY_ENV, "").strip() or None) if url else None
    try:
        config = json.loads(HUB_CONFIG.read_text(encoding="utf-8"))
        url = hub_url(config.get("url", ""))
        if url:
            return url, (str(config.get("key", "")).strip() or None)
    except (OSError, ValueError, AttributeError):
        pass
    return DEFAULT_HUB, None


def payload_of(entry):
    """What goes to the central server: the feedback fields only, nothing about money or the budget."""
    body = {"rating": entry.get("rating"), "message": entry.get("message"), "screen": entry["screen"],
            "contextId": entry.get("context_id"), "deviceId": entry.get("device_id"),
            "appVersion": entry.get("app_version") or APP_VERSION}
    return {key: value for key, value in body.items() if value not in (None, "")}


# The receiver refused this entry itself (bad value, duplicate): dropped so it never blocks the rest.
# Any other answer (401/403/404: a setup problem, 408/429, 5xx, offline) keeps it for later.
_REFUSED = (400, 409, 422)
_COLUMNS = {"rating": "rating", "message": "message", "screen": "screen", "contextId": "context_id",
            "deviceId": "device_id", "appVersion": "app_version"}


class Relay:
    """Sends feedback to the central receiver (an SSUST server, or the online database) and keeps
    it in the outbox until the receiver confirms it. Nothing else ever leaves this computer.
    """

    def __init__(self, path, url, timeout=RELAY_TIMEOUT, key=None):
        FeedbackBox(path)  # makes the file and both tables
        self.path = Path(path)
        self.url = url
        self.key = key
        self.timeout = timeout
        self._lock = threading.Lock()

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def pending(self):
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]

    def deliver(self, entry):
        """Queue `entry` (checked fields), then try to send everything waiting.
        Returns (outbox id, True when it reached the central server)."""
        payload = json.dumps(payload_of(entry), ensure_ascii=False)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(self._connect()) as con, con:
            if con.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] >= MAX_OUTBOX:
                raise FeedbackError("Too much feedback is waiting to be sent. Try again when online.")
            entry_id = con.execute("INSERT INTO outbox (created_at, payload) VALUES (?, ?)",
                                   (created, payload)).lastrowid
        self.flush()
        with closing(self._connect()) as con:
            waiting = con.execute("SELECT 1 FROM outbox WHERE id = ?", (entry_id,)).fetchone()
        return entry_id, waiting is None

    def flush(self):
        """Send the waiting entries, oldest first; stop at the first one that must wait."""
        with self._lock:
            with closing(self._connect()) as con:
                rows = con.execute("SELECT id, payload FROM outbox ORDER BY id").fetchall()
            for entry_id, payload in rows:
                if self._post(payload) == "later":
                    return
                with closing(self._connect()) as con, con:
                    con.execute("DELETE FROM outbox WHERE id = ?", (entry_id,))

    def _request(self, payload):
        headers = {"Content-Type": "application/json", "User-Agent": f"SSUST-feedback/{APP_VERSION}"}
        if is_database(self.url):
            # One row in the feedback table; the public key may insert, never read (docs).
            row = {_COLUMNS[key]: value for key, value in json.loads(payload).items()}
            headers.update({"apikey": self.key or "", "Prefer": "return=minimal"})
            if (self.key or "").startswith("eyJ"):
                headers["Authorization"] = f"Bearer {self.key}"  # an older anon key (a JWT); a publishable key goes in apikey only
            url = f"{self.url.rstrip('/')}/rest/v1/{DATABASE_TABLE}"
            return urllib.request.Request(url, data=json.dumps(row).encode("utf-8"), method="POST", headers=headers)
        return urllib.request.Request(self.url, data=payload.encode("utf-8"), method="POST", headers=headers)

    def _post(self, payload):
        request = self._request(payload)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
            if is_database(self.url):
                return "sent"  # 2xx: the row is stored
            # An SSUST server must say {"ok": true}: an older server answers 200 but drops the words.
            try:
                return "sent" if json.loads(body.decode("utf-8")).get("ok") is True else "later"
            except (ValueError, AttributeError):
                return "later"
        except urllib.error.HTTPError as exc:
            return "refused" if exc.code in _REFUSED else "later"
        except (urllib.error.URLError, OSError, TimeoutError, ValueError):
            return "later"
