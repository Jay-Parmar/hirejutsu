"""Reading the resume and building a profile from it."""

import re
import unicodedata
from datetime import date
from functools import cache
from importlib import resources
from pathlib import Path

from .config import Config
from .errors import HirejutsuError
from .models import Profile

PROFILE_DEFAULTS = {"titles": [], "skills": [], "locations": ["remote"], "years": None}

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
MONTH = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
DATE = rf"(?:\b(?:{MONTH})\.?,?\s*|\b(?:\d{{1,2}}[/.-])?(?:0?[1-9]|1[0-2])[/.-])?(?<!\d)(?:19|20)\d\d(?!\d)"
UNTIL_NOW = r"(?:till\s+|to\s+)?(?:present|current(?:ly)?|now|today|date|ongoing)\b"
DATE_RANGE = re.compile(rf"({DATE})\s*(?:[-\u2010-\u2015]+|to|till|until)\s*({DATE}|{UNTIL_NOW})", re.IGNORECASE)
YEARS = r"(\d{1,2}(?:\.\d{1,2})?)\s*\+?\s*(?:years?|yrs?)\b"
STATED_YEARS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        rf"\b{YEARS}['\u2019]?\s+(?:of\s+)?(?:[\w-]+\s+){{0,3}}?exp(?:erience)?\b",
        rf"\b(?:over|more than|nearly|almost|around|about)\s+{YEARS}",
        rf"\bexperience\s*(?:of|:|-)?\s*{YEARS}",
    )
]
EDUCATION = re.compile(
    r"\b(?:education|university|college|school|institute|academy|degree|diploma|bachelor\w*"
    r"|master(?:'|\u2019)?s|master of|b\.?\s?tech|m\.?\s?tech|b\.?\s?sc|m\.?\s?sc|b\.?\s?com|m\.?\s?com"
    r"|b\.e|m\.e|bba|bca|mca|mba|ph\.?d|llb|cgpa|gpa|hsc|ssc|cbse|icse)\b",
    re.IGNORECASE,
)


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix == ".docx":
        return read_docx(path)
    raise HirejutsuError(f"Can't read {path.suffix} resumes. Use a .pdf, .docx, .txt or .md file.")


def read_pdf(path: Path) -> str:
    # pypdf and python-docx are imported in the readers so that commands
    # which never read the resume start faster.
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
    except PyPdfError as exc:
        raise HirejutsuError(f"Cannot read {path}: {exc}") from exc
    if not text.strip():
        raise HirejutsuError(
            f"No text found in {path}, it looks like a scanned PDF. "
            "Export your resume as a text PDF, or use a .docx or .txt file."
        )
    # Ligatures such as "fl" would otherwise hide words like Airflow.
    return unicodedata.normalize("NFKC", text)


def read_docx(path: Path) -> str:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError
    from docx.table import Table

    try:
        document = Document(str(path))
    except PackageNotFoundError as exc:
        raise HirejutsuError(f"Cannot read {path}: it is not a valid .docx file.") from exc
    lines = []
    for block in document.iter_inner_content():
        if isinstance(block, Table):
            # A merged cell is listed once for every column it spans.
            lines += [" | ".join(cell.text for cell in dict.fromkeys(row.cells)) for row in block.rows]
        else:
            lines.append(block.text)
    return "\n".join(lines)


@cache
def skill_terms() -> list[tuple[str, str, bool]]:
    """Every spelling of every known skill as (spelling, main name, exact case only)."""
    text = resources.files("hirejutsu").joinpath("data", "skills.txt").read_text(encoding="utf-8")
    terms = []
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            names = [name.strip() for name in line.split("|")]
            main = names[0].lstrip("!")
            terms += [(name.lstrip("!"), main, name.startswith("!")) for name in names]
    return terms


def find_skills(text: str) -> list[str]:
    """Known skills in text by main name, in the order they are first mentioned."""
    lowered = text.lower()
    first: dict[str, int] = {}
    for term, name, exact in skill_terms():
        # A plain substring test skips most terms without running a regex.
        if term.lower() not in lowered:
            continue
        match = _term_pattern(term, exact).search(text)
        if match and match.start() < first.get(name, len(text)):
            first[name] = match.start()
    return sorted(first, key=first.get)


def _term_pattern(term: str, exact: bool) -> re.Pattern:
    if exact:
        # These names are short or plain words, so they must not touch - & . + or #
        # either: that rules out C-suite, R&D, Go-live, C++ and initials like R.
        return re.compile(rf"(?<![\w&.+#-]){re.escape(term)}(?![\w&.+#-])")
    return re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", re.IGNORECASE)


def find_years(text: str, today: date) -> float | None:
    """Years of experience: the larger of what the resume states and what its job dates cover."""
    found = [float(match.group(1)) for pattern in STATED_YEARS for match in pattern.finditer(text)]
    months = _work_months(text, today)
    if months:
        found.append(months / 12)
    return round(max(found), 1) if found else None


def _work_months(text: str, today: date) -> int:
    """Months covered by date ranges outside education, counting overlapping jobs once."""
    now = today.year * 12 + today.month
    lines = [line for line in text.splitlines() if line.strip()]
    spans = []
    for index, line in enumerate(lines):
        for match in DATE_RANGE.finditer(line):
            start = _month_count(match.group(1), today, end=False)
            end = min(_month_count(match.group(2), today, end=True), now)
            if start < end and not _is_education(lines, index):
                spans.append((start, end))
    total = reach = 0
    for start, end in sorted(spans):
        if end > reach:
            total += end - max(start, reach)
            reach = end
    return total


def _month_count(value: str, today: date, end: bool) -> int:
    """Months from year 0 to where a date starts, or to where it ends for an end date."""
    year = re.search(r"(?:19|20)\d\d", value)
    if not year:
        return today.year * 12 + today.month
    named = re.match(r"[a-z]{3}", value, re.IGNORECASE)
    numbered = re.search(r"(\d{1,2})[/.-](?:19|20)\d\d", value)
    if named:
        month = MONTHS.index(named.group().lower()) + 1
    elif numbered:
        month = int(numbered.group(1))
    else:
        # A bare year counts from January, so 2018 - 2021 is three years.
        return int(year.group()) * 12
    return int(year.group()) * 12 + month - (0 if end else 1)


def _is_education(lines: list[str], index: int) -> bool:
    """True if the date range on this line belongs to a degree or a school."""
    nearby = lines[index]
    # The line above often names the school, unless it has dates of its own.
    if index and not DATE_RANGE.search(lines[index - 1]):
        nearby += "\n" + lines[index - 1]
    return EDUCATION.search(nearby) is not None


def load_profile(config: Config) -> Profile:
    settings = config.section("profile", PROFILE_DEFAULTS)
    path = config.path(config.get("resume", "resume.pdf"))
    if not path.exists():
        raise HirejutsuError(f"Resume not found at {path}. Set 'resume' in the config.")
    return Profile(
        text=read_text(path),
        skills=list(settings["skills"]),
        titles=list(settings["titles"]),
        years=settings["years"],
        locations=list(settings["locations"]),
    )
