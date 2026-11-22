"""Local SSUST server. Binds to this computer only."""

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote

from money import CATEGORIES, FUNDS, clean_note, make_state, parse_amount, plan, snapshot
from places import KINDS, RADIUS_KM, fetch_places

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 4096
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ALLOWED_FILES = {
    "/": FRONTEND / "index.html",
    "/index.html": FRONTEND / "index.html",
    "/styles.css": FRONTEND / "styles.css",
    "/app.js": FRONTEND / "app.js",
    "/vendor/leaflet/leaflet.js": FRONTEND / "vendor" / "leaflet" / "leaflet.js",
    "/vendor/leaflet/leaflet.css": FRONTEND / "vendor" / "leaflet" / "leaflet.css",
}
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}

STATE = make_state("sample")
NEXT_ID = 1
LOCK = threading.Lock()


def public_state():
    return {**STATE, "payments": list(STATE["payments"]), "view": snapshot(STATE)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' https://tile.openstreetmap.org")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def reject(self, code, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload, code=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def trusted_host(self):
        host = self.headers.get("Host", "")
        return host in (f"{HOST}:{PORT}", f"localhost:{PORT}")

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Send JSON.")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request is empty or too large.")
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON object required.")
        return data

    def do_GET(self):
        if not self.trusted_host():
            self.reject(400, "Untrusted host.")
            return
        path, _, query = unquote(self.path).partition("?")
        if path == "/api/state":
            self.send_json(public_state())
            return
        if path == "/api/places":
            self.get_places(query)
            return
        file_path = ALLOWED_FILES.get(path)
        if file_path is None or not file_path.is_file():
            self.reject(404, "Not found.")
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES[file_path.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.trusted_host():
            self.reject(400, "Untrusted host.")
            return
        path = unquote(self.path.split("?", 1)[0])
        try:
            data = self.read_json()
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self.reject(400, "Could not read the request.")
            return
        if path == "/api/mode":
            self.post_mode(data)
        elif path == "/api/settings":
            self.post_settings(data)
        elif path == "/api/payments":
            self.post_payment(data)
        else:
            self.reject(404, "Not found.")

    def get_places(self, query):
        params = parse_qs(query)
        kind = (params.get("kind") or ["food"])[0]
        radius = (params.get("radius") or ["3"])[0]
        if kind not in KINDS or radius not in RADIUS_KM:
            self.reject(400, "Unknown map filter.")
            return
        try:
            payload = fetch_places(kind, float(radius))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            self.reject(503, "The live map could not be loaded. Check the internet connection and try again.")
            return
        self.send_json(payload)

    def post_mode(self, data):
        mode = data.get("mode")
        if mode not in ("sample", "empty", "over"):
            self.reject(400, "Unknown week.")
            return
        global STATE
        with LOCK:
            STATE = make_state(mode)
            payload = public_state()
        self.send_json(payload)

    def post_settings(self, data):
        opening = {}
        for fund in FUNDS:
            opening[fund] = parse_amount(data.get(fund) if isinstance(data.get(fund), str) else None)
            if opening[fund] is None:
                self.reject(400, "Each fund needs a number greater than zero.")
                return
        with LOCK:
            STATE["opening"] = opening
            STATE["payments"] = []
            STATE["mode"] = "custom"
            payload = public_state()
        self.send_json(payload)

    def post_payment(self, data):
        category = data.get("category")
        if category not in CATEGORIES:
            self.reject(400, "Unknown category.")
            return
        amount = parse_amount(data.get("amount"))
        if amount is None:
            self.reject(400, "Enter an amount greater than zero.")
            return
        try:
            note = clean_note(data.get("note", ""))
        except ValueError as exc:
            self.reject(400, str(exc))
            return
        choice = data.get("choice")
        if choice is not None and choice not in ("snack", "borrow", "savings"):
            self.reject(400, "Unknown cover.")
            return
        global NEXT_ID
        with LOCK:
            if not snapshot(STATE)["ready"]:
                self.reject(400, "Set the five funds first.")
                return
            result = plan(STATE, amount, category)
            if result.get("error"):
                self.reject(400, result["error"])
                return
            if result["saveNow"]:
                taken = result["from"]
                level = result["level"]
            else:
                match = next((item for item in result["options"] if item["choice"] == choice), None)
                if match is None:
                    payload = {
                        "needsConfirm": True,
                        "level": result["level"],
                        "options": result["options"],
                        "state": public_state(),
                    }
                    self.send_json(payload)
                    return
                taken = match["from"]
                level = match["hole"]
            STATE["payments"].append({
                "id": f"p{NEXT_ID}",
                "date": STATE["today"],
                "amount": amount,
                "category": category,
                "note": note,
                "from": taken,
                "uncovered": result.get("uncovered", 0) if result["saveNow"] else 0,
            })
            NEXT_ID += 1
            payload = {"needsConfirm": False, "level": level, "state": public_state()}
        self.send_json(payload)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SSUST is running at http://{HOST}:{PORT}")
    print("This server accepts connections from this computer only. Close the window to stop it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
