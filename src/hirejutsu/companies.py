"""Companies whose career pages are fetched, and spotting their job board in a URL."""

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml

from .config import Config
from .errors import HirejutsuError

FILE_NAME = "companies.yaml"
COMPANIES_DEFAULTS = {"builtin": True}
USER_HEADER = (
    "# Your own companies for the career page sources, in the same shape as the built-in list.\n"
    "# Boards under removed are never fetched. The hirejutsu companies command rewrites this file.\n"
)
ATSES = (
    "greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable",
    "workday", "personio", "breezy", "bamboohr", "teamtailor",
)
GREENHOUSE_HOSTS = {
    "boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io",
}
# Boards that live on their own subdomain, by the domain after it.
SUBDOMAINS = {
    "recruitee.com": "recruitee",
    "jobs.personio.de": "personio",
    "jobs.personio.com": "personio",
    "breezy.hr": "breezy",
    "bamboohr.com": "bamboohr",
    "teamtailor.com": "teamtailor",
    "workable.com": "workable",
}
RESERVED = {"www", "app", "api", "apply", "jobs"}
LOCALE = re.compile(r"[a-z]{2}-[a-z]{2}", re.I)
URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.I)


@dataclass(frozen=True)
class Company:
    ats: str
    slug: str
    name: str = ""

    @property
    def key(self) -> str:
        """ats:slug in lower case, since board names are not case sensitive."""
        return f"{self.ats}:{self.slug}".lower()


def load_companies(config: Config) -> list[Company]:
    """The built-in companies, unless turned off, and the user's own, minus the removed boards."""
    added, removed = read_user(config.home)
    found = {}
    if config.section("companies", COMPANIES_DEFAULTS)["builtin"]:
        found = {company.key: company for company in builtin()}
    found.update((company.key, company) for company in added)
    skipped = set(removed)
    return [company for key, company in found.items() if key not in skipped]


def companies_for(config: Config, ats: str) -> list[Company]:
    return [company for company in load_companies(config) if company.ats == ats]


@cache
def builtin() -> tuple[Company, ...]:
    text = resources.files("hirejutsu").joinpath("data", FILE_NAME).read_text(encoding="utf-8")
    return tuple(parse(yaml.safe_load(text), "the built-in company list"))


def read_user(home: Path) -> tuple[list[Company], list[str]]:
    """The companies in the user's own file and the keys of the boards it removes."""
    path = home / FILE_NAME
    if not path.exists():
        return [], []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise HirejutsuError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HirejutsuError(f"{path} must contain a mapping at the top level")
    return parse(data, str(path)), [str(key).lower() for key in data.get("removed") or []]


def write_user(home: Path, companies: list[Company], removed: list[str]) -> Path:
    data: dict = {}
    for company in sorted(companies, key=lambda company: (ATSES.index(company.ats), company.key)):
        if company.ats == "workday":
            data.setdefault("workday", []).append({"name": company.name, "url": workday_url(company.slug)})
        else:
            data.setdefault(company.ats, {})[company.slug] = company.name
    if removed:
        data["removed"] = sorted(set(removed))
    home.mkdir(parents=True, exist_ok=True)
    path = home / FILE_NAME
    path.write_text(USER_HEADER + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def save_companies(home: Path, companies: list[Company]) -> Path:
    """Add or rename companies in the user's file and take them off its removed list."""
    added, removed = read_user(home)
    keys = {company.key for company in companies}
    kept = [company for company in added if company.key not in keys]
    return write_user(home, kept + companies, [key for key in removed if key not in keys])


def drop_companies(home: Path, companies: list[Company]) -> Path:
    """Take companies out of the user's file and list them as removed, so built-in ones stay out too."""
    added, removed = read_user(home)
    keys = {company.key for company in companies}
    return write_user(home, [company for company in added if company.key not in keys], removed + list(keys))


def parse(data: dict, where: str) -> list[Company]:
    """Companies from {ats: {board: name}}, where Workday is a list of names and careers page URLs."""
    unknown = sorted(set(data) - set(ATSES) - {"removed"})
    if unknown:
        raise HirejutsuError(f"Unknown ATS in {where}: {', '.join(unknown)}. Use one of: {', '.join(ATSES)}")
    companies = []
    for ats in ATSES:
        if ats == "workday":
            entries = [(_workday_board(entry.get("url"), where), entry.get("name")) for entry in data.get(ats) or []]
        else:
            entries = (data.get(ats) or {}).items()
        companies += [Company(ats, str(slug), str(name or slug)) for slug, name in entries]
    return companies


def _workday_board(url, where: str) -> str:
    found = detect(str(url or ""))
    if not found or found[0] != "workday":
        raise HirejutsuError(f"Not a Workday careers page in {where}: {url}")
    return found[1]


def workday_url(slug: str) -> str:
    """The careers page of a Workday board written as tenant.wdN/site."""
    host, _, site = slug.partition("/")
    return f"https://{host}.myworkdayjobs.com/{site}"


def detect(text: str) -> tuple[str, str] | None:
    """(ats, board) for a careers page or job URL, or for text like greenhouse:stripe."""
    text = text.strip()
    ats, colon, board = text.partition(":")
    if colon and ats.lower() in ATSES and not board.startswith("//"):
        return (ats.lower(), board.strip()) if board.strip() else None
    url = urlparse(text if "://" in text else f"https://{text}")
    host = (url.hostname or "").lower()
    path = [unquote(part) for part in url.path.split("/") if part]
    first = path[0] if path else ""
    sub, _, domain = host.partition(".")
    if host in GREENHOUSE_HOSTS:
        # Embedded boards name the board in the query, as in /embed/job_board?for=stripe.
        board = parse_qs(url.query).get("for", [""])[0] if first == "embed" else first
        found = "greenhouse", board
    elif host == "boards-api.greenhouse.io":
        found = "greenhouse", _after(path, "boards")
    elif host in ("jobs.lever.co", "jobs.eu.lever.co"):
        found = "lever", first
    elif host in ("api.lever.co", "api.eu.lever.co"):
        found = "lever", _after(path, "postings")
    elif host == "jobs.ashbyhq.com":
        found = "ashby", first
    elif host == "api.ashbyhq.com":
        found = "ashby", _after(path, "job-board")
    elif host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com"):
        found = "smartrecruiters", first
    elif host == "api.smartrecruiters.com":
        found = "smartrecruiters", _after(path, "companies")
    elif host == "apply.workable.com":
        board = _after(path, "accounts") if first == "api" else first
        # Short links like /j/{code} do not name the account.
        found = "workable", "" if board == "j" else board
    elif domain.endswith(".myworkdayjobs.com") or domain == "myworkdaysite.com":
        found = "workday", _workday(host, [part for part in path if not LOCALE.fullmatch(part)])
    elif domain in SUBDOMAINS and sub not in RESERVED:
        found = SUBDOMAINS[domain], sub
    else:
        return None
    return found if found[1] else None


def _after(path: list[str], name: str) -> str:
    """The path segment that follows name, as in /v1/boards/{board}."""
    return path[path.index(name) + 1] if name in path[:-1] else ""


def _workday(host: str, path: list[str]) -> str:
    """tenant.wdN/site, the board of a myworkdayjobs.com or myworkdaysite.com URL."""
    labels = host.split(".")
    if labels[1:] == ["myworkdaysite", "com"]:
        return f"{path[1]}.{labels[0]}/{path[2]}" if len(path) > 2 and path[0] == "recruiting" else ""
    if len(labels) != 4 or not path:
        return ""
    if path[0] == "wday":
        return f"{path[2]}.{labels[1]}/{path[3]}" if len(path) > 3 else ""
    return f"{labels[0]}.{labels[1]}/{path[0]}"


def find_boards(text: str) -> set[tuple[str, str]]:
    """Every (ats, board) linked from a piece of text."""
    found = (detect(url.rstrip(".,;:!?")) for url in URL_IN_TEXT.findall(text or ""))
    return {board for board in found if board}
