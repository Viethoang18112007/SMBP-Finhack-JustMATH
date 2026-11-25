"""Reads a JSON list of receipt texts on stdin, prints a JSON list of parse_receipt results.

Used by tools/simulate_vision.mjs:
    python tools/parse_receipt_text.py < texts.json
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from ssust.receipt import parse_receipt  # noqa: E402


def main():
    texts = json.loads(sys.stdin.buffer.read().decode("utf-8"))  # UTF-8 whatever the console says
    sys.stdout.write(json.dumps([parse_receipt(text) for text in texts]))


if __name__ == "__main__":
    main()
