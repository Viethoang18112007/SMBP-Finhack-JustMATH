"""Start SSUST with one command, from any folder, on Windows, macOS or Linux.

    python run.py [--port 8765] [--data DIR] [--demo] [--no-browser]
    python run.py --export-feedback feedback.csv   (team: every feedback entry as CSV, then exit)

Standard library only. The app listens on 127.0.0.1 (this computer only).
Press Ctrl+C to stop it.
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from ssust import feedback  # noqa: E402
from ssust.dates import LiveClock  # noqa: E402
from ssust.server import HOST, PORT, AppServer, make_server  # noqa: E402

DEFAULT_DATA = ROOT / "data"


def _port(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text!r}") from None
    if not 0 <= value <= 65535:
        raise argparse.ArgumentTypeError("must be between 0 and 65535 (0 picks a free port)")
    return value


def _feedback_url(text):
    try:
        return feedback.hub_url(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="run.py", description="Start the SSUST budget app.")
    parser.add_argument("--port", type=_port, default=PORT,
                        help=f"port on 127.0.0.1 (default {PORT}; 0 picks a free one)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="folder for the live and demo database files (default: data/ next to run.py)")
    parser.add_argument("--demo", action="store_true", help="start in demo mode on the sample week")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    url, key = feedback.default_target()
    parser.add_argument("--feedback-url", type=_feedback_url, metavar="URL", default=url,
                        help="where feedback goes (default: the online feedback database in "
                             "backend/ssust/data/feedback_hub.json, else the hosted SSUST server; 'local' keeps it "
                             "here). Only feedback leaves this computer")
    parser.add_argument("--export-feedback", type=Path, metavar="FILE",
                        help="write every feedback entry in the data folder to FILE (CSV) and exit")
    args = parser.parse_args(argv)
    args.data = args.data.resolve()
    # The key goes with the default receiver only (never to a URL typed on the command line).
    args.feedback_key = key if args.feedback_url == url else os.environ.get(feedback.KEY_ENV, "").strip() or None
    return args


def main(argv=None, on_ready=None):
    """Run until Ctrl+C (or server.shutdown()). Returns the exit code.

    `on_ready(server)` is called once the port is bound, before serving.
    """
    args = parse_args(argv)
    if args.export_feedback:
        count = feedback.export_csv(args.data / feedback.FEEDBACK_FILE, args.export_feedback)
        print(f"Wrote {count} feedback {'entry' if count == 1 else 'entries'} to {args.export_feedback.resolve()}")
        return 0
    try:
        server = make_server(args.data, LiveClock(), port=args.port, feedback_url=args.feedback_url,
                             feedback_key=args.feedback_key)
    except OSError as error:
        print(f"Could not start on port {args.port}: {error}\n"
              f"Is SSUST already running? Try another port, e.g. python run.py --port 8766 (or --port 0 for any free port)",
              file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as error:
        # A data folder from a newer version of the app (another branch) or a swapped file: no traceback.
        print(f"Could not open the data folder {args.data}: {error}\n"
              f"If it was written by a newer version of SSUST, start with another folder:\n"
              f"  python run.py --data data-new",
              file=sys.stderr)
        return 1

    try:
        if args.demo:
            server.service.set_mode("demo")
        url = f"http://{HOST}:{server.server_address[1]}/"
        print(f"SSUST is running at {url}", flush=True)
        print(f"Data folder: {args.data} (your budget and payments stay on this computer)")
        print(f"Feedback goes to: {args.feedback_url or 'this data folder'}")
        print("Only this computer can connect. Press Ctrl+C to stop.", flush=True)
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                print("Could not open a browser. Open the address above yourself.")
        if on_ready is not None:
            on_ready(server)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
