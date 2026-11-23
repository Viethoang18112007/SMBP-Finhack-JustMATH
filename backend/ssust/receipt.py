"""Find the total in the text read from a receipt. Pure functions, integer cents, no I/O.

The text comes from OCR in the browser, so it can be wrong: the app only pre-fills the
amount and the student always checks it and confirms through the normal payment flow.

Rules:
- a line with a total word (TOTAL, AMOUNT DUE, GRAND TOTAL, 合計, 總數, 總計, 應付...) is a
  candidate; the last candidate wins. If a total word stands alone, a next line that holds
  only an amount is used.
- lines with SUBTOTAL/小計, CHANGE, CASH, TENDERED, TIP, a remaining Octopus value... never count.
- dates, times, percents, phone numbers and card numbers are removed before reading amounts;
  on a total line the last amount is the total.
- HK$, HKD, $ and plain numbers are accepted. The merchant guess is the first line with a few
  letters that is not a receipt header.
"""

import re

from .validate import MAX_CENTS

MAX_TEXT = 3500  # characters of OCR text accepted
MERCHANT_MAX = 40

TOTAL_WORDS = ("GRAND TOTAL", "AMOUNT DUE", "TOTAL DUE", "TOTAL", "合計", "合计", "總數", "總数", "總計",
               "总计", "應付", "应付", "總額", "总额")
IGNORE_WORDS = ("SUBTOTAL", "SUB TOTAL", "SUB-TOTAL", "小計", "小计", "CHANGE", "找續", "找赎", "找贖",
                "CASH", "TENDERED", "TIP", "GRATUITY", "REMAINING", "BALANCE", "餘額", "余额", "剩餘", "現金")
HEADER_WORDS = ("RECEIPT", "INVOICE", "收據", "收据", "發票", "WELCOME", "歡迎")

_CLEAN = (
    re.compile(r"\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}"),  # dates
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # times
    re.compile(r"\d+(?:\.\d+)?\s*%"),  # percents
    re.compile(r"[*xX•#]{3,}\s*\d{2,4}"),  # masked card numbers
    re.compile(r"\b\d{4}[ -]\d{4}\b"),  # Hong Kong phone numbers
    re.compile(r"\d{7,}"),  # long digit runs: card, phone, receipt numbers
)
_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d,]|\.\d)")
_CJK_GAP = re.compile("(?<=[㐀-鿿])\\s+(?=[㐀-鿿])")  # OCR puts spaces between Chinese characters
_ONLY_AMOUNT = re.compile(r"^\s*(?:HK\$|HKD|\$)?\s*[\d,]+(?:\.\d{1,2})?\s*$", re.IGNORECASE)


def _has(line, words):
    upper = line.upper()
    return any(word in upper for word in words)


def amounts_in(line):
    """Amounts on one line, in cents, after dates, times, phones and card numbers are removed."""
    text = line
    for pattern in _CLEAN:
        text = pattern.sub(" ", text)
    found = []
    for whole, decimals in _AMOUNT.findall(text):
        cents = int(whole.replace(",", "")) * 100 + int((decimals or "0").ljust(2, "0"))
        if 0 < cents <= MAX_CENTS:
            found.append(cents)
    return found


def _merchant(lines):
    for line in lines:
        letters = sum(1 for ch in line if ch.isalpha())
        if letters < 3 or _has(line, HEADER_WORDS) or _has(line, TOTAL_WORDS) or _has(line, IGNORE_WORDS):
            continue
        name = _CJK_GAP.sub("", " ".join(line.split()))
        if len(name) > MERCHANT_MAX:
            cut = name[:MERCHANT_MAX + 1]
            name = cut[:cut.rfind(" ")] if " " in cut else name[:MERCHANT_MAX]
        return name.strip()
    return None


def parse_receipt(text):
    """{"found", "amount" (cents or None), "line" (the line used or None), "merchant" (or None)}."""
    if not isinstance(text, str):
        raise ValueError("Send the receipt text.")
    if len(text) > MAX_TEXT:
        raise ValueError("The receipt text is too long.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    best = None
    for i, line in enumerate(lines):
        if not _has(line, TOTAL_WORDS) or _has(line, IGNORE_WORDS):
            continue
        amounts = amounts_in(line)
        if amounts:
            best = (amounts[-1], line)
        elif i + 1 < len(lines) and _ONLY_AMOUNT.match(lines[i + 1]):
            nxt = amounts_in(lines[i + 1])
            if nxt:
                best = (nxt[-1], f"{line} {lines[i + 1]}")
    merchant = _merchant(lines)
    if best is None:
        return {"found": False, "amount": None, "line": None, "merchant": merchant}
    return {"found": True, "amount": best[0], "line": best[1], "merchant": merchant}
