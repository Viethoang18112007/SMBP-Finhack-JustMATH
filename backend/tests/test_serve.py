"""Tests for the hosted launcher, serve.py at the repo root (Render and similar hosts).

serve.py reads its settings from environment variables, listens on every
interface and adds the public host name to the trusted hosts. Every test uses a
temporary data folder and never reaches the network.
"""

import contextlib
import http.client
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from ssust.dates import FixedClock
from ssust.server import make_server

ROOT = Path(__file__).resolve().parent.parent.parent
SERVE_PY = ROOT / "serve.py"


def load_serve():
    spec = importlib.util.spec_from_file_location("ssust_serve", SERVE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get(port, path, host):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.putrequest("GET", path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()


class PublicHosts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = make_server(Path(tmp.name), FixedClock("2026-11-11"), port=0, quiet=True,
                                  public_hosts=("ssust.onrender.com",))
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        thread.start()
        self.port = self.server.server_address[1]

        def stop():
            self.server.shutdown()
            thread.join(5)
            self.server.server_close()
        self.addCleanup(stop)

    def test_public_host_is_trusted(self):
        status, _ = get(self.port, "/api/state", "ssust.onrender.com")
        self.assertEqual(status, 200)

    def test_local_hosts_still_trusted(self):
        status, _ = get(self.port, "/api/state", f"127.0.0.1:{self.port}")
        self.assertEqual(status, 200)

    def test_other_hosts_still_refused(self):
        for host in ("evil.example", "ssust.onrender.com.evil.example", "x.ssust.onrender.com"):
            with self.subTest(host=host):
                status, body = get(self.port, "/api/state", host)
                self.assertEqual((status, body["error"]), (400, "Untrusted host."))

    def test_default_has_no_public_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(Path(tmp), FixedClock("2026-11-11"), port=0, quiet=True)
            try:
                port = server.server_address[1]
                self.assertEqual(server.server_address[0], "127.0.0.1")
                self.assertEqual(server.trusted_hosts, frozenset({f"127.0.0.1:{port}", f"localhost:{port}"}))
            finally:
                server.server_close()


class Config(unittest.TestCase):
    def setUp(self):
        self.serve = load_serve()

    def test_defaults(self):
        config = self.serve.config({})
        self.assertEqual(config["port"], 10000)
        self.assertEqual(config["hosts"], ())
        self.assertEqual(config["data"], ROOT / "data")
        self.assertEqual(config["mode"], "demo")

    def test_reads_the_environment(self):
        config = self.serve.config({
            "PORT": "8080",
            "RENDER_EXTERNAL_HOSTNAME": "ssust.onrender.com",
            "SSUST_PUBLIC_HOSTS": "Budget.Example.org, other.example.org",
            "SSUST_DATA": "somewhere",
            "SSUST_MODE": "live",
        })
        self.assertEqual(config["port"], 8080)
        self.assertEqual(config["hosts"], ("ssust.onrender.com", "budget.example.org", "other.example.org"))
        self.assertEqual(config["data"], Path("somewhere").resolve())
        self.assertEqual(config["mode"], "live")

    def test_bad_values_are_refused(self):
        bad = (
            {"PORT": "abc"}, {"PORT": "70000"}, {"PORT": "-1"},
            {"SSUST_PUBLIC_HOSTS": "evil.example/path"}, {"SSUST_PUBLIC_HOSTS": "a b"},
            {"RENDER_EXTERNAL_HOSTNAME": "x" * 300}, {"SSUST_MODE": "nope"},
        )
        for env in bad:
            with self.subTest(env=env):
                with self.assertRaises(ValueError):
                    self.serve.config(env)


class Main(unittest.TestCase):
    def test_starts_in_demo_on_every_interface(self):
        serve = load_serve()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        ready = threading.Event()
        holder = {}

        def on_ready(server):
            holder["server"] = server
            ready.set()

        env = {"PORT": "0", "SSUST_DATA": tmp.name, "RENDER_EXTERNAL_HOSTNAME": "ssust.onrender.com"}

        def target():
            with contextlib.redirect_stdout(io.StringIO()):
                holder["code"] = serve.main(env, on_ready=on_ready)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        self.assertTrue(ready.wait(10), "the server did not start")
        server = holder["server"]
        self.assertEqual(server.server_address[0], "0.0.0.0")
        status, state = get(server.server_address[1], "/api/state", "ssust.onrender.com")
        self.assertEqual((status, state["mode"]), (200, "demo"))
        server.shutdown()
        thread.join(10)
        self.assertEqual(holder["code"], 0)

    def test_bad_config_exits_with_1(self):
        serve = load_serve()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(serve.main({"PORT": "nope"}), 1)
        self.assertIn("PORT", err.getvalue())


if __name__ == "__main__":
    unittest.main()
