"""Reading salaries written as free text, like "$170k - $200k" or "60-100k EUR"."""

import re

SYMBOLS = {"$": "USD", "\N{EURO SIGN}": "EUR", "\N{POUND SIGN}": "GBP", "\N{INDIAN RUPEE SIGN}": "INR"}
CODE = re.compile(r"\b(USD|EUR|GBP|CAD|AUD|NZD|CHF|INR|PLN|SEK|NOK|DKK|SGD|JPY)\b", re.I)
NUMBER = r"(?<![\w.,])(\d+(?:[.,]\d+)*)\s*(k\b)?"
DASH = r"(?:-|\N{EN DASH}|\N{EM DASH}|to)"
SIGN = r"[$\N{EURO SIGN}\N{POUND SIGN}\N{INDIAN RUPEE SIGN}]"
AMOUNT = re.compile(rf"{NUMBER}\s*{DASH}\s*{SIGN}?\s*{NUMBER}|{NUMBER}", re.I)
PERIOD = re.compile(
    r"(?P<hour>\b(?:hour|hourly|hr)\b|/\s*h\b)"
    r"|(?P<day>\b(?:day|daily)\b)"
    r"|(?P<week>\b(?:week|weekly|wk)\b)"
    r"|(?P<fortnight>\bfortnight(?:ly)?\b)"
    r"|(?P<month>\b(?:month|monthly|mo)\b)"
    r"|(?P<year>\b(?:year|yearly|yr|annual|annually|annum)\b)",
    re.I,
)


def parse_salary(text: str) -> dict:
    """Salary fields for a Job, or an empty dict when the text has no amount."""
    found = AMOUNT.search(text)
    if not found:
        return {}
    if found[3]:
        low, high = _amount(found[1], found[2] or found[4]), _amount(found[3], found[4])
    else:
        low = high = _amount(found[5], found[6])
    return {
        "salary_min": low,
        "salary_max": high,
        "salary_currency": _currency(text),
        "salary_period": salary_period(text) or ("hour" if high < 1000 else "year"),
    }


def salary_period(text: str) -> str:
    """year, month, fortnight, week, day or hour for words like "annual" or "/hr"."""
    found = PERIOD.search(text)
    return found.lastgroup if found else ""


def _amount(digits: str, thousands: str | None) -> float:
    groups = re.split(r"[.,]", digits)
    if len(groups) > 1 and len(groups[-1]) != 3:
        value = float("".join(groups[:-1]) + "." + groups[-1])
    else:
        value = float("".join(groups))
    return value * 1000 if thousands else value


def _currency(text: str) -> str:
    code = CODE.search(text)
    if code:
        return code[1].upper()
    return next((name for symbol, name in SYMBOLS.items() if symbol in text), "")
