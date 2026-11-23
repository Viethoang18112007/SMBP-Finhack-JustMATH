"""Find the total in the text read from a receipt. Pure functions, integer cents, no I/O.

The text comes from OCR on a phone photo, so it can be wrong: the app only pre-fills the
amount and the student always checks it and confirms through the normal payment flow.

Rules:
- a line with a total word (TOTAL, AMOUNT DUE, GRAND TOTAL, 合計, 總數, 總計, 應付...) is a
  candidate; the last candidate wins. Receipts that print AMOUNT instead (AMT, AM0UNT, 金額,
  Montant, Amount payable) are read the same way, but only when no TOTAL line is found, so an
  "Amount" column header or an "Amount paid" line never beats a real total. TOTAL is also found when the camera misreads it
  (T0TAL, TOTA1, TOTAI, T0TA L). If a total word stands alone, an amount on one of the next two
  lines is used (OCR often splits the two columns).
- lines with SUBTOTAL/小計 (misread too), CHANGE, CASH, TENDERED, TIP, a remaining Octopus value,
  or a total quantity (QTY, ITEMS) never count.
- dates, times, percents, phone numbers and card numbers are removed before reading amounts;
  a decimal misread as "48,00" or "48 . 00" is read as 48.00; on a total line the last amount
  is the total.
- with no total line, the largest price on the receipt (an amount with two decimals, not on an
  ignored line) is returned as a best guess, marked "guess": the app asks to check it.
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
AMOUNT_WORDS = ("金額", "金额", "MONTANT", "PAYABLE")
QUANTITY_WORDS = ("QTY", "QUANTITY", "ITEMS", "ITEM(S)", "數量", "件數")
HEADER_WORDS = ("RECEIPT", "INVOICE", "收據", "收据", "發票", "WELCOME", "歡迎")

# TOTAL as a camera reads it: O as 0 or Q, L as 1, I or |, A as 4, and a stray space.
_TOTAL = re.compile(r"T ?[O0Q] ?T ?[A4] ?[L1I|]")
_SUBTOTAL = re.compile(r"SUB ?-? ?T ?[O0Q] ?T")
_AMOUNT_WORD = re.compile(r"\bAM ?[O0] ?UNT\b|\bAMT\b")

_CLEAN = (
    re.compile(r"\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}"),  # dates
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # times
    re.compile(r"\d+(?:\.\d+)?\s*%"),  # percents
    re.compile(r"[*xX•#]{3,}\s*\d{2,4}"),  # masked card numbers
    re.compile(r"\b\d{4}[ -]\d{4}\b"),  # Hong Kong phone numbers
    re.compile(r"\d{7,}"),  # long digit runs: card, phone, receipt numbers
)
_DECIMAL = re.compile(r"(\d)(?:\s*\.\s*|,)(\d{2})(?!\d)")  # 48,00 / 48 . 00 -> 48.00
_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d,]|\.\d)")
_CJK_GAP = re.compile("(?<=[㐀-鿿])\\s+(?=[㐀-鿿])")  # OCR puts spaces between Chinese characters
_ONLY_AMOUNT = re.compile(r"^\s*(?:HK\$|HKD|\$)?\s*[\d,]+(?:\.\d{1,2})?\s*$", re.IGNORECASE)
_ONLY_CURRENCY = re.compile(r"^\s*(?:HK\$|HKD|HK|\$|港幣|港元)\s*:?\s*$", re.IGNORECASE)


def _has(line, words):
    upper = line.upper()
    return any(word in upper for word in words)


def _ignored(line):
    upper = line.upper()
    return _has(line, IGNORE_WORDS) or _has(line, QUANTITY_WORDS) or bool(_SUBTOTAL.search(upper))


def _is_total(line):
    upper = line.upper()
    return (bool(_TOTAL.search(upper)) or _has(line, TOTAL_WORDS)) and not _ignored(line)


def _is_amount(line):
    """AMOUNT where other receipts print TOTAL (a weaker word: used only without a TOTAL line)."""
    return (bool(_AMOUNT_WORD.search(line.upper())) or _has(line, AMOUNT_WORDS)) and not _ignored(line)


def _amounts(line, priced_only=False):
    text = line
    for pattern in _CLEAN:
        text = pattern.sub(" ", text)
    text = _DECIMAL.sub(r"\1.\2", text)
    found = []
    for whole, decimals in _AMOUNT.findall(text):
        if priced_only and len(decimals) != 2:
            continue
        cents = int(whole.replace(",", "")) * 100 + int((decimals or "0").ljust(2, "0"))
        if 0 < cents <= MAX_CENTS:
            found.append(cents)
    return found


def amounts_in(line):
    """Amounts on one line, in cents, after dates, times, phones and card numbers are removed."""
    return _amounts(line)


def _merchant(lines):
    for line in lines:
        letters = sum(1 for ch in line if ch.isalpha())
        if (letters < 3 or _has(line, HEADER_WORDS) or _is_total(line) or _is_amount(line)
                or _has(line, TOTAL_WORDS) or _ignored(line)):
            continue
        name = _CJK_GAP.sub("", " ".join(line.split()))
        if len(name) > MERCHANT_MAX:
            cut = name[:MERCHANT_MAX + 1]
            name = cut[:cut.rfind(" ")] if " " in cut else name[:MERCHANT_MAX]
        return name.strip()
    return None


def _next_amount(lines, i):
    """The amount on one of the two lines after a lone total word, skipping a lone "HKD"."""
    for j in range(i + 1, min(i + 3, len(lines))):
        line = _DECIMAL.sub(r"\1.\2", lines[j])
        if _ONLY_AMOUNT.match(line):
            found = amounts_in(line)
            return (found[-1], lines[j]) if found else None
        if not _ONLY_CURRENCY.match(line):
            return None
    return None


def parse_receipt(text):
    """{"found", "amount" (cents or None), "line" (the line used or None), "merchant" (or None),
    "guess" (True when no total line was found and the largest price is offered instead)}."""
    if not isinstance(text, str):
        raise ValueError("Send the receipt text.")
    if len(text) > MAX_TEXT:
        raise ValueError("The receipt text is too long.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total = amount = None
    for i, line in enumerate(lines):
        strong = _is_total(line)
        if not strong and not _is_amount(line):
            continue
        found = None
        amounts = amounts_in(line)
        if amounts:
            found = (amounts[-1], line)
        else:
            nxt = _next_amount(lines, i)
            if nxt:
                found = (nxt[0], f"{line} {nxt[1]}")
        if found and strong:
            total = found
        elif found:
            amount = found
    best = total or amount
    merchant = _merchant(lines)
    if best is not None:
        return {"found": True, "amount": best[0], "line": best[1], "merchant": merchant, "guess": False}
    guess = None
    for line in lines:
        if _ignored(line):
            continue
        for cents in _amounts(line, priced_only=True):
            if guess is None or cents >= guess[0]:
                guess = (cents, line)
    if guess is None:
        return {"found": False, "amount": None, "line": None, "merchant": merchant, "guess": False}
    return {"found": True, "amount": guess[0], "line": guess[1], "merchant": merchant, "guess": True}
