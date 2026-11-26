"""Fresh clone smoke test: start SSUST on an empty, temporary data folder and check that
everything the home screen widgets need answers with valid data.

    python scripts/smoke_fresh_clone.py            # this folder, as it is on disk
    python scripts/smoke_fresh_clone.py --clone    # a `git clone` of this folder's last commit
                                                    # (catches files that exist only on your computer)

Standard library only. Your own data/ folder is never touched: the server gets a temporary
data folder and a free port. It checks:
  - every file the page loads (index.html, every JS module, vendored Leaflet and tesseract.js,
    the icons and the sample receipts) is served with the right type;
  - the Host check accepts both 127.0.0.1 and localhost;
  - /api/state on an empty live database has every field the widgets read;
  - quick add (POST /api/assistant/parse), the receipt reader (POST /api/receipt/parse),
    saving a budget and a payment, the insights, and demo mode with its places.
Exit code 0 when everything passes, 1 otherwise.
"""

import argparse
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent

_ATTR = re.compile(r"""\b(?:src|href)="([^"#?:]+)\"""")
_IMPORT = re.compile(r"""^\s*(?:import|export)\b[^'"]*?\bfrom\s*['"]([^'"]+)['"]|^\s*import\s*['"]([^'"]+)['"]""",
                     re.MULTILINE)
_ASSET = re.compile(r"""["'`]((?:img|vendor)/[A-Za-z0-9_./-]+\.(?:png|svg|js|css|gz))["'`]""")
_SAMPLE = re.compile(r"""["'](receipt-[A-Za-z0-9_-]+\.png)["']""")
_TESSERACT = ("tesseract.min.js", "worker.min.js", "core/tesseract-core-simd-lstm.wasm.js",
              "lang/eng.traineddata.gz", "lang/chi_tra.traineddata.gz")

TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".png": "image/png",
         ".svg": "image/svg+xml", ".gz": "application/octet-stream"}


def referenced_files(frontend):
    """Every file under `frontend` that the page loads: index.html links, the module graph,
    asset paths written in the modules, the sample receipts and the OCR files (ocr.js builds
    those URLs at run time)."""
    frontend = Path(frontend)
    found = {frontend / "index.html"}
    index = (frontend / "index.html").read_text(encoding="utf-8")
    todo = []
    for link in _ATTR.findall(index):
        path = (frontend / link).resolve()
        found.add(path)
        if path.suffix == ".js" and "/js/" in path.as_posix():
            todo.append(path)
    seen = set()
    while todo:
        module = todo.pop()
        if module in seen or not module.is_file():
            continue
        seen.add(module)
        found.add(module)
        text = module.read_text(encoding="utf-8")
        for a, b in _IMPORT.findall(text):
            spec = a or b
            if spec.startswith("."):
                todo.append((module.parent / spec).resolve())
        for asset in _ASSET.findall(text):
            found.add((frontend / asset).resolve())
        for sample in _SAMPLE.findall(text):
            found.add((frontend / "img" / "samples" / sample).resolve())
        if module.name == "ocr.js":
            found.update((frontend / "vendor" / "tesseract" / name).resolve() for name in _TESSERACT)
    return {path.resolve() for path in found}


class Client:
    def __init__(self, base):
        parts = urlsplit(base)
        self.host, self.port = parts.hostname, parts.port

    def request(self, method, path, body=None, host=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=20)
        try:
            headers = {"Host": host or f"{self.host}:{self.port}"}
            data = None
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=data, headers=headers)
            res = conn.getresponse()
            raw = res.read()
            return res.status, res.getheader("Content-Type", ""), raw
        finally:
            conn.close()

    def json(self, method, path, body=None, host=None):
        status, _, raw = self.request(method, path, body, host)
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError:
            return status, None


def check_widget_state(data):
    """Problems with the fields the home screen widgets and quick add read, or []."""
    problems = []
    if not isinstance(data, dict):
        return ["/api/state did not answer a JSON object"]
    for key, kind in (("mode", str), ("today", str), ("view", dict), ("tanks", list), ("inbox", list),
                      ("payments", list), ("weeks", list), ("opening", dict)):
        if not isinstance(data.get(key), kind):
            problems.append(f"state.{key} is missing or not a {kind.__name__}")
    view = data.get("view") if isinstance(data.get("view"), dict) else {}
    if not isinstance(view.get("ready"), bool):
        problems.append("state.view.ready is missing")
    if view.get("ready"):
        for key in ("todayRemaining", "allowance", "spentToday", "daysLeft"):
            if not isinstance(view.get(key), int):
                problems.append(f"state.view.{key} is missing (needed by the 'Left today' widget)")
        funds = view.get("fundsNow")
        if not isinstance(funds, dict) or any(not isinstance(funds.get(f), int) for f in
                                              ("main", "snack", "fixed", "experience", "development", "savings")):
            problems.append("state.view.fundsNow is missing a fund (needed by the funds widget)")
        if "projection" not in data:
            problems.append("state.projection is missing (needed by the status pill)")
    return problems


def check_files(client, frontend):
    problems = []
    files = sorted(referenced_files(frontend))
    for path in files:
        if not path.is_file():
            problems.append(f"missing on disk: {path.relative_to(frontend).as_posix()}")
            continue
        url = "/" + path.relative_to(frontend).as_posix()
        status, ctype, _ = client.request("GET", url)
        want = TYPES.get(path.suffix, "")
        if status != 200 or not ctype.startswith(want):
            problems.append(f"GET {url}: {status} {ctype}")
    print(f"  files: {len(files)} checked")
    return problems


def check_server(base, frontend):
    """Run every check against a running server. Returns the list of problems ([] = pass).

    It writes to the server's live data (a budget and one payment) and switches it to demo
    mode at the end: only run it on a temporary data folder.
    """
    client = Client(base)
    problems = check_files(client, Path(frontend))

    for host in (f"127.0.0.1:{client.port}", f"localhost:{client.port}"):
        status, _ = client.json("GET", "/api/state", host=host)
        if status != 200:
            problems.append(f"Host {host} refused ({status})")

    status, state = client.json("GET", "/api/state")
    if status != 200:
        return problems + [f"GET /api/state: {status}"]
    problems += check_widget_state(state)
    if state.get("mode") != "live":
        problems.append(f"a fresh data folder should start in live mode, not {state.get('mode')}")
    print(f"  widgets (empty live week): ready={state.get('view', {}).get('ready')}")

    status, entry = client.json("POST", "/api/assistant/parse", {"text": "$50 KFC dinner"})
    if status != 200 or not entry or entry.get("amount") != 5000 or entry.get("category") != "main":
        problems.append(f"quick add parse: {status} {entry}")

    receipt = "SAMPLE NOODLE BAR\nBeef noodles 42.00\nMilk tea 18.00\nTOTAL 60.00\nVISA 60.00"
    status, scan = client.json("POST", "/api/receipt/parse", {"text": receipt})
    if status != 200 or not scan or scan.get("amount") != 6000:
        problems.append(f"receipt parse: {status} {scan}")

    budget = {"main": "560", "snack": "70", "fixed": "210", "experience": "140", "development": "140", "savings": "280"}
    status, state = client.json("POST", "/api/settings", budget)
    if status != 200:
        problems.append(f"save a budget: {status} {state}")
    else:
        problems += check_widget_state(state)
        print(f"  widgets (budget saved): left today {state['view'].get('todayRemaining')} cents")

    status, saved = client.json("POST", "/api/payments", {"amount": "12", "category": "snack", "note": "smoke test"})
    if status != 200 or not saved:
        problems.append(f"save a payment: {status} {saved}")

    status, insights = client.json("GET", "/api/insights")
    if status != 200 or not isinstance(insights, dict):
        problems.append(f"GET /api/insights: {status}")

    status, demo = client.json("POST", "/api/mode", {"mode": "demo"})
    if status != 200 or not demo or demo.get("mode") != "demo":
        problems.append(f"switch to demo: {status}")
    else:
        problems += check_widget_state(demo)
        if not demo["view"].get("ready"):
            problems.append("the demo week has no budget")
        print(f"  widgets (demo week): left today {demo['view'].get('todayRemaining')} cents")
        status, found = client.json("GET", "/api/places?kind=food&radius=1")
        if status != 200 or not found or not found.get("places"):
            problems.append(f"demo places: {status}")
    return problems


def start(folder, data, python):
    """Start run.py from `folder` on a free port; return (process, base URL)."""
    proc = subprocess.Popen([python, "run.py", "--port", "0", "--data", str(data), "--no-browser"], cwd=folder,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace")
    deadline = time.time() + 30
    lines = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        lines.append(line)
        found = re.search(r"(http://127\.0\.0\.1:\d+)/", line)
        if found:
            return proc, found.group(1)
    proc.kill()
    raise RuntimeError("the server did not start:\n" + "".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--clone", action="store_true",
                        help="test a fresh `git clone` of the last commit instead of this folder")
    parser.add_argument("--python", default=sys.executable, help="the Python that runs run.py (default: this one)")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="ssust-smoke-") as tmp:
        folder = ROOT
        if args.clone:
            if shutil.which("git") is None:
                print("git is not installed: run without --clone.")
                return 1
            folder = Path(tmp) / "clone"
            subprocess.run(["git", "clone", "--quiet", str(ROOT), str(folder)], check=True)
            print(f"Cloned the last commit into {folder}")
        data = Path(tmp) / "data"
        print(f"Python: {args.python}")
        try:
            proc, base = start(folder, data, args.python)
        except RuntimeError as exc:
            print(f"FAIL: {exc}")
            return 1
        print(f"Server: {base} (temporary data folder)")
        try:
            problems = check_server(base, folder / "frontend")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            proc.stdout.close()
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("PASS: a fresh copy serves every file and the widgets get valid data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
