"""Tests for the one-command launcher, run.py at the repo root.

run.py is loaded from its file path (it is not inside backend/). Every test
uses a temporary data folder and --no-browser, so nothing touches data/, opens
a browser or reaches the network (/api/state never fetches places).
"""

import contextlib
import http.client
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
RUN_PY = ROOT / "run.py"


def load_run():
    spec = importlib.util.spec_from_file_location("ssust_run", RUN_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_json(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


class Arguments(unittest.TestCase):
    def setUp(self):
        self.run = load_run()

    def test_defaults(self):
        args = self.run.parse_args([])
        self.assertEqual(args.port, 8765)
        self.assertEqual(args.data, ROOT / "data")
        self.assertFalse(args.demo)
        self.assertFalse(args.no_browser)

    def test_all_options(self):
        args = self.run.parse_args(["--port", "0", "--data", "somewhere", "--demo", "--no-browser"])
        self.assertEqual(args.port, 0)
        self.assertEqual(args.data, Path("somewhere").resolve())
        self.assertTrue(args.demo)
        self.assertTrue(args.no_browser)

    def test_bad_ports_are_refused(self):
        for bad in ("-1", "65536", "abc", "80.5"):
            with self.subTest(port=bad), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    self.run.parse_args(["--port", bad])


class Main(unittest.TestCase):
    def setUp(self):
        self.run = load_run()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / "data"

    def start(self, *extra):
        """Run main() in a thread; return (port, thread, printed text, result holder)."""
        ready = threading.Event()
        holder = {}
        out = io.StringIO()

        def on_ready(server):
            holder["server"] = server
            ready.set()

        def target():
            with contextlib.redirect_stdout(out):
                holder["code"] = self.run.main(
                    ["--no-browser", "--port", "0", "--data", str(self.data), *extra], on_ready=on_ready)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(10), "the server did not start")
        return holder["server"].server_address[1], thread, out, holder

    def stop(self, thread, holder):
        holder["server"].shutdown()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(holder["code"], 0)

    def test_starts_serves_and_stops(self):
        port, thread, out, holder = self.start()
        status, state = get_json(port, "/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["mode"], "live")
        self.stop(thread, holder)
        self.assertIn(f"http://127.0.0.1:{port}", out.getvalue())
        self.assertTrue((self.data / "ssust.db").exists())

    def test_demo_flag_starts_in_demo(self):
        port, thread, _, holder = self.start("--demo")
        status, state = get_json(port, "/api/state")
        self.assertEqual((status, state["mode"], state["scenario"]), (200, "demo", "sample"))
        self.stop(thread, holder)

    def test_no_browser_means_no_browser(self):
        with mock.patch("webbrowser.open") as opened:
            _, thread, _, holder = self.start()
            self.stop(thread, holder)
        opened.assert_not_called()

    def test_opens_the_browser_by_default(self):
        with mock.patch("webbrowser.open") as opened, contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(self.run.AppServer, "serve_forever", side_effect=KeyboardInterrupt):
                code = self.run.main(["--port", "0", "--data", str(self.data)])
        self.assertEqual(code, 0)
        opened.assert_called_once()
        self.assertTrue(opened.call_args[0][0].startswith("http://127.0.0.1:"))

    def test_ctrl_c_closes_the_server_cleanly(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(self.run.AppServer, "serve_forever", side_effect=KeyboardInterrupt), \
                mock.patch.object(self.run.AppServer, "server_close", autospec=True,
                                  side_effect=self.run.AppServer.server_close) as closed:
            code = self.run.main(["--no-browser", "--port", "0", "--data", str(self.data)])
        self.assertEqual(code, 0)
        closed.assert_called_once()
        self.assertIn("Stopped", out.getvalue())

    def test_port_in_use_is_a_clear_error(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            port = taken.getsockname()[1]
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = self.run.main(["--no-browser", "--port", str(port), "--data", str(self.data)])
        self.assertEqual(code, 1)
        self.assertIn(str(port), err.getvalue())
        self.assertIn("--port", err.getvalue())


class FromAnotherFolder(unittest.TestCase):
    """`python <abs path>/run.py` from an unrelated working directory, as a real process."""

    def test_runs_whatever_the_current_directory(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            env = dict(os.environ, PYTHONUNBUFFERED="1")
            proc = subprocess.Popen(
                [sys.executable, str(RUN_PY), "--no-browser", "--port", "0", "--data", "here"],
                cwd=elsewhere, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                first = {}
                reader = threading.Thread(target=lambda: first.update(line=proc.stdout.readline()), daemon=True)
                reader.start()
                reader.join(15)
                line = first.get("line", "")
                self.assertIn("http://127.0.0.1:", line)
                port = int(line.split("http://127.0.0.1:")[1].split()[0].rstrip("/"))
                status, state = get_json(port, "/api/state")
                self.assertEqual(status, 200)
                self.assertIn("view", state)
                self.assertTrue((Path(elsewhere) / "here" / "ssust.db").exists())
            finally:
                proc.kill()
                proc.wait(10)
                proc.stdout.close()


if __name__ == "__main__":
    unittest.main()
