"""Reading the resume and building a profile from it."""

import re
import unicodedata
from functools import cache
from importlib import resources
from pathlib import Path

from .config import Config
from .errors import HirejutsuError
from .models import Profile

PROFILE_DEFAULTS = {"titles": [], "skills": [], "locations": ["remote"], "years": None}


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
def skill_terms() -> list[tuple[str, str]]:
    """Every spelling of every known skill, paired with the skill's main name."""
    text = resources.files("hirejutsu").joinpath("data", "skills.txt").read_text(encoding="utf-8")
    terms = []
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            names = [name.strip() for name in line.split("|")]
            terms += [(name, names[0]) for name in names]
    return terms


def find_skills(text: str) -> list[str]:
    """Known skills in text by main name, in the order they are first mentioned."""
    lowered = text.lower()
    first: dict[str, int] = {}
    for term, name in skill_terms():
        # A plain substring test skips most terms without running a regex.
        if term.lower() not in lowered:
            continue
        match = re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text, re.IGNORECASE)
        if match and match.start() < first.get(name, len(text)):
            first[name] = match.start()
    return sorted(first, key=first.get)


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
