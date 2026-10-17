"""Companies whose career pages are fetched, and spotting their job board in a URL."""

import re
from urllib.parse import parse_qs, unquote, urlparse

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
