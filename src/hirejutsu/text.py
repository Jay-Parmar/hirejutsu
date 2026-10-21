"""Text helpers for job descriptions and dates."""

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr",
}
SKIP_TAGS = {"script", "style", "noscript", "head"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skipping += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skipping = max(0, self.skipping - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def html_to_text(value: str | None) -> str:
    """Turn an HTML fragment into plain text with one block per line."""
    if not value:
        return ""
    if "&lt;" in value and "<" not in value:
        value = html.unescape(value)
    parser = _TextParser()
    parser.feed(value)
    parser.close()
    lines = []
    bullet = False
    for line in (clean(part) for part in "".join(parser.parts).split("\n")):
        if line == "-":
            bullet = True
        elif line:
            lines.append(f"- {line}" if bullet and not line.startswith("- ") else line)
            bullet = False
    return "\n".join(lines)


def parse_date(value) -> datetime | None:
    """Parse ISO, RFC 2822 or epoch values into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, (int, float)) or str(value).strip().isdigit():
        result = _from_epoch(float(value))
    else:
        result = _from_text(str(value).strip())
    if result is None:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _from_epoch(number: float) -> datetime | None:
    if number > 1e11:
        number /= 1000
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _from_text(text: str) -> datetime | None:
    iso = text[:-1] + "+00:00" if text[-1:] in ("Z", "z") else text
    iso = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d+)", lambda m: f"{m.group(1)}.{(m.group(2) + '000000')[:6]}", iso)
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
