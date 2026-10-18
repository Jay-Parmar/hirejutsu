"""Reading the resume and building a profile from it."""

from pathlib import Path

from .config import Config
from .errors import HirejutsuError
from .models import Profile

PROFILE_DEFAULTS = {"titles": [], "skills": [], "locations": ["remote"], "years": None}


def read_text(path: Path) -> str:
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise HirejutsuError(f"Can't read {path.suffix} resumes. Use a .txt or .md file.")


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
