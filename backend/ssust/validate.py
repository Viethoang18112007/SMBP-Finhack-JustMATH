"""Input checks for amounts and notes."""

import re

# Commas may only group thousands ("1,234.50"); "12,50" is refused, never read as 1250.
_GROUPED = re.compile(r"[0-9]{1,3}(,[0-9]{3})+(\.[0-9]*)?")

MAX_CENTS = 100_000_000
ASCII_DIGITS = frozenset("0123456789")


def _digits(text):
    return bool(text) and all(ch in ASCII_DIGITS for ch in text)


def parse_amount(raw, allow_zero=False):
    """Integer cents for text like "48", "48.5", "HK$1,234.50", or None.

    Payments are strictly positive; funds pass allow_zero=True to accept 0.
    At most two decimals, a dot as the decimal mark, at most MAX_CENTS.
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.replace("HK$", "").replace("hk$", "").strip()
    if "," in cleaned:
        if not _GROUPED.fullmatch(cleaned):
            return None
        cleaned = cleaned.replace(",", "")
    if not cleaned or cleaned.count(".") > 1:
        return None
    whole, _, frac = cleaned.partition(".")
    if not _digits(whole) or (frac and (not _digits(frac) or len(frac) > 2)):
        return None
    cents = int(whole) * 100 + int(frac.ljust(2, "0") or "0")
    if cents < (0 if allow_zero else 1) or cents > MAX_CENTS:
        return None
    return cents


def clean_note(raw):
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raise ValueError("Note must be text.")
    note = "".join(ch for ch in raw if ch.isprintable() and ch not in "<>")
    return note.strip()[:40].rstrip()
