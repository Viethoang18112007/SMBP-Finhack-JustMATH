"""Start SSUST on a hosting platform (Render or similar). Local use: run.py.

    python serve.py

Standard library only. Settings come from environment variables:
    PORT                       port to listen on (the platform sets it; default 10000)
    RENDER_EXTERNAL_HOSTNAME   public host name (Render sets it), trusted in the Host check
    SSUST_PUBLIC_HOSTS         more public host names, comma separated (optional)
    SSUST_DATA                 folder for the database files (default: data/ next to this file)
    SSUST_MODE                 "demo" (default, the sample week) or "live"
    SSUST_FEEDBACK_URL         send feedback on (optional): the online feedback database, also read
    SSUST_FEEDBACK_KEY         from backend/ssust/data/feedback_hub.json. Without either, this server
                               is the central feedback server and keeps it, team-only
    SSUST_ADMIN_TOKEN          opens the team-only feedback view (/admin/feedback)

It listens on every interface (0.0.0.0) because the platform's proxy forwards
requests to it. The database lives on the platform's disk, which free plans
wipe on every restart: this is for showing the demo, not for keeping real data.
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from ssust import feedback  # noqa: E402
from ssust.dates import LiveClock  # noqa: E402
from ssust.server import make_server  # noqa: E402

BIND = "0.0.0.0"
DEFAULT_PORT = 10000
HOST_NAME = re.compile(r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")
MODES = ("demo", "live")


def config(env):
    """Read and check the settings. Raises ValueError with a readable message."""
    text = env.get("PORT", "").strip() or str(DEFAULT_PORT)
    if not text.isdigit() or not 0 <= int(text) <= 65535:
        raise ValueError(f"PORT must be a whole number from 0 to 65535, not {text!r}")
    hosts = []
    raw = [env.get("RENDER_EXTERNAL_HOSTNAME", "")] + env.get("SSUST_PUBLIC_HOSTS", "").split(",")
    for name in (item.strip().lower() for item in raw):
        if not name:
            continue
        if not HOST_NAME.match(name):
            raise ValueError(f"not a host name: {name[:80]!r}")
        if name not in hosts:
            hosts.append(name)
    mode = env.get("SSUST_MODE", "").strip().lower() or "demo"
    if mode not in MODES:
        raise ValueError(f"SSUST_MODE must be demo or live, not {mode!r}")
    data = env.get("SSUST_DATA", "").strip()
    feedback_url, feedback_key = feedback.default_target(env)
    if feedback_url == feedback.DEFAULT_HUB:
        feedback_url = feedback_key = None  # this server is the hosted SSUST server itself: it keeps it
    return {
        "feedbackUrl": feedback_url,
        "feedbackKey": feedback_key,
        "port": int(text),
        "hosts": tuple(hosts),
        "data": Path(data).resolve() if data else ROOT / "data",
        "mode": mode,
    }


def main(env=None, on_ready=None):
    """Run until stopped. Returns the exit code. `on_ready(server)` runs once the port is bound."""
    try:
        settings = config(os.environ if env is None else env)
    except ValueError as error:
        print(f"Bad setting: {error}", file=sys.stderr)
        return 1
    try:
        server = make_server(settings["data"], LiveClock(), port=settings["port"],
                             host=BIND, public_hosts=settings["hosts"], feedback_url=settings["feedbackUrl"],
                             feedback_key=settings["feedbackKey"])
    except OSError as error:
        print(f"Could not start on port {settings['port']}: {error}", file=sys.stderr)
        return 1
    try:
        if settings["mode"] == "demo":
            server.service.set_mode("demo")
        print(f"SSUST is listening on {BIND}:{server.server_address[1]} ({settings['mode']} mode)", flush=True)
        for name in settings["hosts"]:
            print(f"Public address: https://{name}/", flush=True)
        if on_ready is not None:
            on_ready(server)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
