"""Check the three price data files and list every rejected record.

    python tools/check_prices.py

Checks backend/ssust/data/verified_prices.json (verified dish prices),
backend/ssust/data/price_ranges.json (per person ranges read on a place's own menu) and
backend/ssust/data/chain_prices.json (one published meal range per chain).
Exit code 0 when every record in the three files is valid, 1 otherwise. Standard library only.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from ssust.prices import CHAIN_FILE, VERIFIED_FILE, load_chains, load_verified  # noqa: E402
from ssust.ranges import RANGES_FILE, counts_by_campus, load_ranges  # noqa: E402


def main():
    bad = 0
    for path, loader in ((VERIFIED_FILE, load_verified), (RANGES_FILE, load_ranges)):
        records, problems = loader(path)
        print(f"{path}: {len(records)} valid record(s), {len(problems)} rejected.")
        for problem in problems:
            print(f"  rejected {problem}")
        if path == RANGES_FILE:
            counts = counts_by_campus(records)
            print("  per campus: " + ", ".join(f"{campus} {n}" for campus, n in counts.items()))
        bad += len(problems)
    chains, chain_problems = load_chains(CHAIN_FILE)
    unchecked = sum(1 for chain in chains if chain["needs_check"])
    print(f"{CHAIN_FILE}: {len(chains)} valid chain(s), {len(chain_problems)} rejected, {unchecked} not yet checked in a shop.")
    for problem in chain_problems:
        print(f"  rejected {problem}")
    bad += len(chain_problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
