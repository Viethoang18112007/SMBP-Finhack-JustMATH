"""HTTP layer over the Service. Binds to this computer only.

    server = make_server(data_dir, clock, port=0)
    server.serve_forever()

Every route reads the request, checks its shape, calls one Service action and
writes JSON. Budget rules live in money.py, actions in service.py.

Errors: ServiceError and bad requests answer 400 with {"error": message}.
Anything unexpected answers 500 with a generic message (the traceback goes
to the server log only, never to the client).
"""

import json
import re
import socket
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import money, places, prices
from .service import Service, ServiceError
from .store import open_books
from .validate import parse_amount

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 4096
FRONTEND = Path(__file__).resolve().parent.parent.parent / "frontend"
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    # The OCR language data (vendor/tesseract/lang): gzip bytes the OCR worker unpacks itself,
    # so no Content-Encoding header (the browser must not unpack it first).
    ".gz": "application/octet-stream",
}
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Content-Security-Policy",
     "default-src 'self'; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; img-src 'self' https://tile.openstreetmap.org"),
    ("Cache-Control", "no-store"),
)
# The iOS app (Capacitor) loads its page from capacitor://localhost and calls the hosted API,
# so /api/ answers that one origin with CORS headers. No other origin, no credentials, no static files.
APP_ORIGINS = ("capacitor://localhost",)
# Each iPhone app sends a random id of its own and gets its own live book (data/devices/<id>/).
# Requests without it use the shared book, exactly as before. The app has no demo mode.
DEVICE_HEADER = "X-SSUST-Device"
DEVICE_ID = re.compile(r"[0-9a-f]{32}")
MAX_DEVICES = 200
CORS_PREFLIGHT = (
    ("Access-Control-Allow-Methods", "GET, POST"),
    ("Access-Control-Allow-Headers", f"Content-Type, {DEVICE_HEADER}"),
    ("Access-Control-Max-Age", "600"),
)
SERVER_ERROR = "Something went wrong on the server. Try again."
DRAIN_BYTES = 1_000_000  # unread request bytes discarded before closing a connection
DRAIN_SECONDS = 1.0


class BadRequest(ValueError):
    """The request itself is unusable (body, query or field types). Answered with a 400."""


class TooManyDevices(RuntimeError):
    """No room for another app device on this server. Answered with a 503."""


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service, places_fetcher, quiet, public_hosts=(), device_factory=None):
        self.service = service
        self.device_factory = device_factory  # device id -> Service, for the iPhone app
        self.devices = {}
        self.devices_lock = threading.Lock()
        self.places_fetcher = places_fetcher
        self.quiet = quiet
        super().__init__(address, Handler)
        port = self.server_address[1]
        # public_hosts: exact host names a hosting proxy sends (serve.py); empty when run locally.
        self.trusted_hosts = frozenset({f"{HOST}:{port}", f"localhost:{port}", *public_hosts})

    def device_service(self, device):
        """The Service for one app device (its own live book), created the first time."""
        with self.devices_lock:
            service = self.devices.get(device)
            if service is None:
                if self.device_factory is None or len(self.devices) >= MAX_DEVICES:
                    raise TooManyDevices("This server has no room for another phone right now.")
                service = self.devices[device] = self.device_factory(device)
            return service

    def shutdown_request(self, request):
        """Close gracefully: stop writing, then discard what the client still sends.

        A 400 can go out before the body is read. Closing a socket with unread
        bytes makes the OS send a reset, and the client would lose the answer.
        The drain is bounded in bytes and time.
        """
        try:
            request.shutdown(socket.SHUT_WR)
            request.settimeout(DRAIN_SECONDS)
            drained = 0
            while drained < DRAIN_BYTES:
                chunk = request.recv(65536)
                if not chunk:
                    break
                drained += len(chunk)
        except OSError:
            pass
        self.close_request(request)


def make_server(data_dir, clock, port=0, places_fetcher=None, quiet=False, host=HOST, public_hosts=()):
    """A server on `host`:`port` (0 picks a free port; read it from server_address).

    `host` is 127.0.0.1 unless a hosting platform runs it (serve.py). `public_hosts`
    are extra exact Host header values to trust (the public host name).

    `data_dir` holds the live and demo database files. `places_fetcher(kind,
    radius_km)` gives live places; it defaults to the Overpass fetch.
    """
    records, problems = prices.load_verified()
    if problems and not quiet:
        print(f"Verified prices: {len(problems)} record(s) rejected and not used:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
    chains, chain_problems = prices.load_chains()
    if chain_problems and not quiet:
        print(f"Chain prices: {len(chain_problems)} chain(s) rejected and not used:", file=sys.stderr)
        for problem in chain_problems:
            print(f"  {problem}", file=sys.stderr)
    service = Service(open_books(data_dir), clock, verified=records, chains=chains)
    fetcher = places.fetch_places if places_fetcher is None else places_fetcher
    devices = Path(data_dir) / "devices"

    def device_factory(device):
        return Service(open_books(devices / device), clock, verified=records, chains=chains)

    return AppServer((host, port), service, fetcher, quiet, tuple(public_hosts), device_factory)


def _text(value, what):
    if not isinstance(value, str):
        raise BadRequest(f"Unknown {what}.")
    return value


def _optional_text(value, what):
    return None if value is None else _text(value, what)


def _cents(value, message, allow_zero=False):
    cents = parse_amount(value, allow_zero=allow_zero)
    if cents is None:
        raise BadRequest(message)
    return cents


class Handler(BaseHTTPRequestHandler):
    timeout = 15  # seconds a client may stall before its connection is closed

    # plumbing
    def log_message(self, fmt, *args):
        if not self.server.quiet:
            print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def end_headers(self):
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        origin = self.app_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def app_origin(self):
        """The iOS app's origin when this is an API request from it and the host is trusted, else None."""
        headers = getattr(self, "headers", None)
        if headers is None or headers.get("Host", "") not in self.server.trusted_hosts:
            return None
        origin = headers.get("Origin", "")
        if origin not in APP_ORIGINS or not urlsplit(self.path).path.startswith("/api/"):
            return None
        return origin

    def send_body(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, code=200):
        self.send_body(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def send_error_json(self, code, message, details=None):
        self.send_json({**(details or {}), "error": message}, code)

    def run(self, action):
        """Call `action` and turn every failure into a JSON error response."""
        try:
            if self.headers.get("Host", "") not in self.server.trusted_hosts:
                self.send_error_json(400, "Untrusted host.")
                return
            action()
        except ServiceError as exc:
            self.send_error_json(400, str(exc), exc.details)
        except BadRequest as exc:
            self.send_error_json(400, str(exc))
        except TooManyDevices as exc:
            self.send_error_json(503, str(exc))
        except Exception:
            if not self.server.quiet:
                traceback.print_exc(file=sys.stderr)
            try:
                self.send_error_json(500, SERVER_ERROR)
            except OSError:
                pass  # the client is gone

    @property
    def device(self):
        """The app device id sent with this request, or None for the web app."""
        device = self.headers.get(DEVICE_HEADER)
        if device is not None and not DEVICE_ID.fullmatch(device):
            raise BadRequest("Unknown app device.")
        return device

    @property
    def service(self):
        """The shared Service (web), or the device's own one (iPhone app)."""
        device = self.device
        return self.server.service if device is None else self.server.device_service(device)

    def do_GET(self):
        self.run(self.route_get)

    def do_POST(self):
        self.run(self.route_post)

    def do_OPTIONS(self):
        self.run(self.preflight)

    def preflight(self):
        """CORS preflight for the iOS app's JSON POSTs. Anything else is refused."""
        if not self.app_origin():
            self.send_error_json(403, "Not allowed.")
            return
        self.send_response(204)
        for name, value in CORS_PREFLIGHT:
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise BadRequest("Send JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise BadRequest("Could not read the request.") from None
        if length <= 0 or length > MAX_BODY:
            raise BadRequest("Request is empty or too large.")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, RecursionError):
            raise BadRequest("Could not read the request.") from None
        if not isinstance(data, dict):
            raise BadRequest("JSON object required.")
        return data

    # routing
    def route_get(self):
        url = urlsplit(self.path)
        path = unquote(url.path)
        query = parse_qs(url.query, keep_blank_values=True)
        if path == "/api/state":
            week = query.get("week", [None])[0]
            self.send_json(self.service.get_state(week))
        elif path == "/api/places":
            self.get_places(query)
        elif path == "/api/insights":
            self.send_json(self.service.insights())
        elif path == "/api/feedback":
            self.send_json(self.service.feedback())
        elif path == "/api/shortcut/today":
            self.send_body(200, self.service.shortcut_today().encode("utf-8"), "text/plain; charset=utf-8")
        else:
            self.send_static(path)

    def route_post(self):
        path = unquote(urlsplit(self.path).path)
        routes = {
            "/api/mode": self.post_mode,
            "/api/settings": self.post_settings,
            "/api/payments": self.post_payment,
            "/api/payments/undo": self.post_undo,
            "/api/campus": self.post_campus,
            "/api/receipt/parse": self.post_receipt,
            "/api/inbox": self.post_inbox,
            "/api/inbox/confirm": self.post_inbox_confirm,
            "/api/inbox/dismiss": self.post_inbox_dismiss,
            "/api/connected": self.post_connected,
            "/api/assistant/parse": self.post_parse,
            "/api/feedback": self.post_feedback,
            "/api/shortcut/wallet": self.post_wallet,
        }
        route = routes.get(path)
        if route is None:
            self.send_error_json(404, "Not found.")
            return
        route(self.read_json())

    # static files
    def send_static(self, path):
        file_path = self.static_file(path)
        if file_path is None:
            self.send_error_json(404, "Not found.")
            return
        self.send_body(200, file_path.read_bytes(), TYPES[file_path.suffix])

    @staticmethod
    def static_file(path):
        """The file under frontend/ for a URL path, or None. No "..", no hidden names, known suffixes only."""
        if path == "/":
            path = "/index.html"
        if not path.startswith("/") or "\\" in path or "\x00" in path:
            return None
        parts = path[1:].split("/")
        if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
            return None
        root = FRONTEND.resolve()
        file_path = root.joinpath(*parts).resolve()
        if not file_path.is_relative_to(root) or file_path.suffix not in TYPES or not file_path.is_file():
            return None
        return file_path

    # actions
    def get_places(self, query):
        kind = query.get("kind", ["food"])[0]
        radius = query.get("radius", ["3"])[0]
        if kind not in places.KINDS or radius not in places.RADIUS_KM:
            raise BadRequest("Unknown map filter.")
        self.send_json(self.service.places(kind, float(radius), self.server.places_fetcher))

    # connected payments (simulated in this demo): an inbox the student reviews
    def post_inbox(self, data):
        amount = _cents(data.get("amount"), "Enter an amount greater than zero.")
        self.send_json(self.service.inbox_add(
            _text(data.get("source"), "source"), amount, _text(data.get("merchant"), "merchant"),
            _text(data.get("card"), "card"), _text(data.get("externalId"), "external id")))

    @staticmethod
    def _item_id(data):
        item_id = data.get("id")
        if type(item_id) is not int:
            raise BadRequest("Unknown item.")
        return item_id

    def post_inbox_confirm(self, data):
        self.send_json(self.service.inbox_confirm(
            self._item_id(data), _text(data.get("category"), "category"),
            _optional_text(data.get("choice"), "cover"), _optional_text(data.get("requestId"), "request id")))

    def post_inbox_dismiss(self, data):
        self.send_json(self.service.inbox_dismiss(self._item_id(data)))

    def post_connected(self, data):
        on = data.get("on")
        if not isinstance(on, bool):
            raise BadRequest("Send on: true or false.")
        self.send_json(self.service.set_connected(_text(data.get("source"), "source"), on))

    def post_receipt(self, data):
        """Find the total, merchant and fund in OCR text. Reads only: nothing is saved."""
        text = data.get("text")
        if not isinstance(text, str):
            raise BadRequest("Send the receipt text.")
        try:
            self.send_json(self.service.scan_receipt(text))
        except ValueError as exc:
            raise BadRequest(str(exc)) from None

    def post_campus(self, data):
        self.send_json(self.service.set_campus(_text(data.get("campus"), "campus")))

    def post_mode(self, data):
        mode = _text(data.get("mode"), "mode")
        scenario = _optional_text(data.get("scenario"), "demo week")
        if self.device is not None and mode != "live":
            raise BadRequest("The app has no demo mode: it always uses your own data.")
        self.send_json(self.service.set_mode(mode, scenario))

    def post_settings(self, data):
        amounts = {}
        for fund in money.FUNDS:
            amounts[fund] = parse_amount(data.get(fund), allow_zero=True)
            if amounts[fund] is None:
                raise ServiceError(f"{money.FUND_NAMES[fund]}: enter an amount of 0 or more, like 120 or 45.50.",
                                   field=fund)
        self.send_json(self.service.set_funds(amounts))

    def post_undo(self, data):
        payment_id = data.get("id")
        if type(payment_id) is not int:
            raise BadRequest("Unknown payment.")
        self.send_json(self.service.undo_payment(payment_id))

    def post_parse(self, data):
        self.send_json(self.service.parse_entry(_text(data.get("text"), "entry")))

    def post_payment(self, data):
        amount = _cents(data.get("amount"), "Enter an amount greater than zero.")
        category = _text(data.get("category"), "category")
        choice = _optional_text(data.get("choice"), "cover")
        request_id = _optional_text(data.get("requestId"), "request id")
        place = data.get("place")
        if place is not None and not isinstance(place, dict):
            raise BadRequest("Unknown place.")
        self.send_json(self.service.add_payment(amount, category, data.get("note", ""), choice, request_id, place))

    def post_wallet(self, data):
        merchant, card = data.get("merchant"), data.get("card")
        if not all(value is None or isinstance(value, str) for value in (merchant, card)):
            raise BadRequest("Merchant and card are text.")
        self.send_json(self.service.wallet_tap(data.get("amount"), merchant, card))

    def post_feedback(self, data):
        self.send_json(self.service.add_feedback(data.get("rating"), data.get("text", "")))
