"""Reading the resume and building a profile from it."""

from pathlib import Path

from .config import Config
from .errors import HirejutsuError
from .models import Profile

PROFILE_DEFAULTS = {"titles": [], "skills": [], "locations": ["remote"], "years": None}


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".docx":
        return read_docx(path)
    raise HirejutsuError(f"Can't read {path.suffix} resumes. Use a .docx, .txt or .md file.")


def read_docx(path: Path) -> str:
    # Imported here so that commands which never read the resume start faster.
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
