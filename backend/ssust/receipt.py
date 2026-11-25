"""Find the total in the text read from a receipt. Pure functions, integer cents, no I/O.

The text comes from OCR on a phone photo, so it can be wrong: the app only pre-fills the
amount and the student always checks it and confirms through the normal payment flow.

Rules, in priority order:
- strong total words (TOTAL, GRAND TOTAL, AMOUNT DUE, TOTAL DUE, 應付, 總計, 合計, 總額, 總數...):
  the last one wins. TOTAL is also found when the camera misreads it (T0TAL, TOTA1, TOTAI, T0TA L).
- medium words (AMOUNT, AMT, AM0UNT, 金額, Montant, PAYABLE): read the same way, but only when no
  strong line is found, so an "Amount" column header or an "Amount paid" line never beats a total.
- a payment line with an amount (MASTER, VISA, AMEX, UNIONPAY, OCTOPUS, 八達通, PAYME, ALIPAY,
  WECHAT, 信用卡, 扣賬卡, EPS) is evidence of the amount paid: among several labelled lines, the
  one the card paid wins.
- weak words (SUBTOTAL, 小計): never beat a strong or medium line. A subtotal equal to a payment
  line is sure (a shop that prints no TOTAL); alone it is a best guess. Subtotal + service charge
  is never added up (the printed total is rounded).
- if a label stands alone, an amount on one of the next two lines is used (OCR splits columns).
- never a candidate: cash tendered and change (CASH, 現金, TENDERED, CHANGE, 找續, 找贖, 收), TIP,
  a remaining Octopus value, a quantity (QTY, ITEMS), negative amounts (discounts) and zero.
- no label gives a total: a best guess ("guess": True, the app asks to check it): the amount paid
  by card if a payment line shows one, else the subtotal, else the price printed most often
  (ties and all-once: the larger one). Only prices count: an amount with decimals or a currency
  mark ($, HK$, HKD, $HK), never an ID, phone, date, time or card number.
- fewer than 2 prices in the whole text: no best guess, "reason": "no_amounts" (retake the photo).
  Prices but none usable: "reason": "no_total".
- formats: $1,032.0, 1.032,00, 48,00, 48 . 00, 93 . 8, HK$ 38, 38,00 $HK. The merchant guess is
  the first line with a few letters that is not a receipt header or a labelled line.
"""

import re
from collections import Counter

from .validate import MAX_CENTS

MAX_TEXT = 3500  # characters of OCR text accepted
MERCHANT_MAX = 40
MIN_PRICES = 2  # fewer prices than this in the text: the photo is retaken, nothing is guessed

STRONG_WORDS = ("GRAND TOTAL", "AMOUNT DUE", "TOTAL DUE", "TOTAL", "合計", "合计", "總數", "總数", "總計",
                "总计", "應付", "应付", "總額", "总额")
MEDIUM_WORDS = ("金額", "金额", "MONTANT", "PAYABLE")
WEAK_WORDS = ("SUBTOTAL", "SUB TOTAL", "SUB-TOTAL", "小計", "小计")
EXCLUDE_WORDS = ("CHANGE", "找續", "找续", "找贖", "找赎", "收", "CASH", "現金", "现金", "TENDERED", "TIP",
                 "GRATUITY", "REMAINING", "BALANCE", "餘額", "余额", "剩餘")
PAYMENT_WORDS = ("八達通", "八达通", "信用卡", "扣賬卡", "扣账卡", "銀聯", "银联")
QUANTITY_WORDS = ("QTY", "QUANTITY", "ITEMS", "ITEM(S)", "數量", "件數")
HEADER_WORDS = ("RECEIPT", "INVOICE", "收據", "收据", "發票", "WELCOME", "歡迎")

# TOTAL as a camera reads it: O as 0 or Q, L as 1, I or |, A as 4, and a stray space.
_TOTAL = re.compile(r"T ?[O0Q] ?T ?[A4] ?[L1I|]")
_SUBTOTAL = re.compile(r"SUB ?-? ?T ?[O0Q] ?T")
_AMOUNT_WORD = re.compile(r"\bAM ?[O0] ?UNT\b|\bAMT\b")
_PAYMENT = re.compile(r"\b(?:MASTER\w*|VISA|AMEX|UNION ?PAY|OCTOPUS|PAYME|ALIPAY|WECHAT\w*|EPS)\b")

_CLEAN = (
    re.compile(r"\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}"),  # dates
    re.compile(r"\d{1,2}:\d{2}(?::\d{2})?"),  # times
    re.compile(r"\d+(?:\.\d+)?\s*%"),  # percents
    re.compile(r"\d*[*xX•#]{3,}\s*\d{0,4}"),  # masked card numbers (535389******2423)
    re.compile(r"\b\d{4}[ -]\d{4}\b"),  # Hong Kong phone numbers
    re.compile(r"\d{7,}"),  # long digit runs: card, phone, receipt numbers
)
_EURO = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+),(\d{2})(?!\d)")  # 1.032,00 -> 1032.00
_DECIMAL = re.compile(r"(\d)(?:\s*\.\s*|,)(\d{2})(?!\d)")  # 48,00 / 48 . 00 -> 48.00
_DECIMAL_ONE = re.compile(r"(\d)\s*\.\s*(\d)(?![\d,])")  # 93 . 8 -> 93.8 (one decimal, as many HK receipts print)
_AMOUNT = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d,]|\.\d)")
_CURRENCY_BEFORE = re.compile(r"(?:HK ?\$|HKD|\$|港幣|港元)\s*-?\s*$", re.IGNORECASE)
_CURRENCY_AFTER = re.compile(r"^\s*(?:\$ ?HK|HKD|HK\$|港幣|港元|元)", re.IGNORECASE)
_MINUS_BEFORE = re.compile(r"(?:^|[\s(:=])-\s*(?:HK ?\$|HKD|\$)?\s*$|(?:HK ?\$|HKD|\$)\s*-\s*$", re.IGNORECASE)
_CJK_GAP = re.compile("(?<=[㐀-鿿])\\s+(?=[㐀-鿿])")  # OCR puts spaces between Chinese characters
_ONLY_AMOUNT = re.compile(r"^\s*-?\s*(?:HK\$|HKD|\$)?\s*-?\s*[\d,]+(?:\.\d{1,2})?\s*(?:\$HK|HKD)?\s*$", re.IGNORECASE)
_ONLY_CURRENCY = re.compile(r"^\s*(?:HK\$|HKD|HK|\$|港幣|港元)\s*:?\s*$", re.IGNORECASE)


def _has(line, words):
    upper = line.upper()
    return any(word in upper for word in words)


def _normal(line):
    """The line with IDs, dates, times, percents, phones and cards removed and decimals joined."""
    text = line
    for pattern in _CLEAN:
        text = pattern.sub(" ", text)
    text = _EURO.sub(lambda m: m.group(1).replace(".", "") + "." + m.group(2), text)
    return _DECIMAL_ONE.sub(r"\1.\2", _DECIMAL.sub(r"\1.\2", text))


def _tokens(line):
    """Amounts on one line: [(cents, price, negative)]. A price has decimals or a currency mark."""
    text = _normal(line)
    found = []
    for match in _AMOUNT.finditer(text):
        whole, decimals = match.groups()
        cents = int(whole.replace(",", "")) * 100 + int((decimals or "0").ljust(2, "0"))
        if cents > MAX_CENTS:
            continue
        before, after = text[:match.start()], text[match.end():]
        price = bool(decimals) or bool(_CURRENCY_BEFORE.search(before)) or bool(_CURRENCY_AFTER.match(after))
        found.append((cents, price, bool(_MINUS_BEFORE.search(before))))
    return found


def amounts_in(line):
    """Positive amounts on one line, in cents, after dates, times, phones and card numbers are removed."""
    return [cents for cents, _, negative in _tokens(line) if cents > 0 and not negative]


def _kind(line):
    upper = line.upper()
    if _has(line, EXCLUDE_WORDS) or _has(line, QUANTITY_WORDS):
        return "excluded"
    if _SUBTOTAL.search(upper) or _has(line, WEAK_WORDS):
        return "weak"
    if _TOTAL.search(upper) or _has(line, STRONG_WORDS):
        return "strong"
    if _AMOUNT_WORD.search(upper) or _has(line, MEDIUM_WORDS):
        return "medium"
    if _PAYMENT.search(upper) or _has(line, PAYMENT_WORDS):
        return "payment"
    return "plain"


def _merchant(lines, kinds):
    for line, kind in zip(lines, kinds):
        letters = sum(1 for ch in line if ch.isalpha())
        if letters < 3 or _has(line, HEADER_WORDS) or kind in ("excluded", "weak", "strong", "medium"):
            continue
        name = _CJK_GAP.sub("", " ".join(line.split()))
        if len(name) > MERCHANT_MAX:
            cut = name[:MERCHANT_MAX + 1]
            name = cut[:cut.rfind(" ")] if " " in cut else name[:MERCHANT_MAX]
        return name.strip()
    return None


def _usable(token):
    """A token as a candidate total: positive, not a discount. Else None."""
    cents, _, negative = token
    return cents if cents > 0 and not negative else None


def _next_amount(lines, i):
    """(cents or None, line) for an amount alone on one of the two lines after a lone label, skipping
    a lone "HKD". None when there is none."""
    for j in range(i + 1, min(i + 3, len(lines))):
        if _ONLY_AMOUNT.match(_normal(lines[j])):
            found = _tokens(lines[j])
            return (_usable(found[-1]), lines[j]) if found else None
        if not _ONLY_CURRENCY.match(lines[j]):
            return None
    return None


def _line_amount(lines, i):
    """(cents, line) for the amount on labelled line i (its last amount), else on one of the two lines
    after it. None when there is none or it is zero or negative."""
    found = _tokens(lines[i])
    if found:
        cents = _usable(found[-1])
        return (cents, lines[i]) if cents else None
    nxt = _next_amount(lines, i)
    return (nxt[0], f"{lines[i]} {nxt[1]}") if nxt and nxt[0] else None


def _pick(candidates, paid):
    """The last candidate a payment line confirms, else the last one."""
    confirmed = [c for c in candidates if c[0] in paid]
    return (confirmed or candidates)[-1]


def _most_frequent(pairs):
    """(cents, line) printed most often; ties go to the larger amount; the line is its last one."""
    counts = Counter(cents for cents, _ in pairs)
    best = max(counts, key=lambda cents: (counts[cents], cents))
    return best, [line for cents, line in pairs if cents == best][-1]


def _answer(found, amount=None, line=None, merchant=None, guess=False, reason=None):
    result = {"found": found, "amount": amount, "line": line, "merchant": merchant, "guess": guess}
    if not found:
        result["reason"] = reason
    return result


def parse_receipt(text):
    """{"found", "amount" (cents or None), "line" (the line used or None), "merchant" (or None),
    "guess" (True when no label gives the total and a best guess is offered)}, plus "reason"
    ("no_amounts" or "no_total") when nothing is found."""
    if not isinstance(text, str):
        raise ValueError("Send the receipt text.")
    if len(text) > MAX_TEXT:
        raise ValueError("The receipt text is too long.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    kinds = [_kind(line) for line in lines]
    merchant = _merchant(lines, kinds)
    labelled = {"strong": [], "medium": [], "weak": []}
    paid = []  # (cents, line) read on payment lines
    for i, (line, kind) in enumerate(zip(lines, kinds)):
        if kind in labelled:
            found = _line_amount(lines, i)
            if found:
                labelled[kind].append(found)
        elif kind == "payment":
            paid += [(cents, line) for cents, price, negative in _tokens(line) if price and cents > 0 and not negative]
    paid_cents = {cents for cents, _ in paid}
    for kind in ("strong", "medium"):
        if labelled[kind]:
            cents, line = _pick(labelled[kind], paid_cents)
            return _answer(True, cents, line, merchant)
    weak = [c for c in labelled["weak"] if c[0] in paid_cents]
    if weak:
        return _answer(True, weak[-1][0], weak[-1][1], merchant)

    # No label gives the total: a best guess, only from a text with enough prices in it.
    if sum(1 for line in lines for _, price, _ in _tokens(line) if price) < MIN_PRICES:
        return _answer(False, merchant=merchant, reason="no_amounts")
    if paid:
        cents, line = _most_frequent(paid)
    elif labelled["weak"]:
        cents, line = labelled["weak"][-1]
    else:
        prices = [(cents, line) for line, kind in zip(lines, kinds) if kind != "excluded"
                  for cents, price, negative in _tokens(line) if price and cents > 0 and not negative]
        if not prices:
            return _answer(False, merchant=merchant, reason="no_total")
        cents, line = _most_frequent(prices)
    return _answer(True, cents, line, merchant, guess=True)
