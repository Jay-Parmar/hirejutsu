"""companies command: the company career pages that the ATS sources read."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree

import requests
from rich.table import Table
from rich.text import Text

from ..companies import ATSES, Company, detect, drop_companies, load_companies, save_companies
from ..errors import HirejutsuError
from ..sources import available

# HTTP errors that mean the board is gone. Workday answers 422 for closed sites.
GONE = {400, 404, 410, 422}
CHECK_WORKERS = 8


def register(sub) -> None:
    parser = sub.add_parser("companies", help="list, add, remove and check company career pages")
    parser.set_defaults(func=list_companies, ats=None, search=None)
    actions = parser.add_subparsers(dest="action", metavar="action")

    action = actions.add_parser("list", help="count the companies of each ATS and list them (the default)")
    action.add_argument("--ats", choices=ATSES, help="only companies on this ATS")
    action.add_argument("--search", metavar="TEXT", help="only companies whose name or board contains TEXT")
    action.set_defaults(func=list_companies)

    action = actions.add_parser("add", help="add a company from its careers page URL")
    action.add_argument("board", help="careers page or job URL, or ats:board like greenhouse:stripe")
    action.add_argument("--name", help="company name to show (default: the name the board gives)")
    action.set_defaults(func=add)

    action = actions.add_parser("remove", help="stop fetching a company, built-in ones too")
    action.add_argument("board", help="careers page URL or ats:board like greenhouse:stripe")
    action.set_defaults(func=remove)

    action = actions.add_parser("check", help="check that every board is live and list the dead ones")
    action.add_argument("--ats", choices=ATSES, help="only boards on this ATS")
    action.add_argument("--prune", action="store_true", help="stop fetching the dead boards")
    action.set_defaults(func=check)


def companies_text(count: int) -> str:
    return f"{count} company" if count == 1 else f"{count} companies"


def list_companies(app, args) -> int:
    companies = load_companies(app.config)
    counts = Counter(company.ats for company in companies)
    table = Table("ATS", "Companies", title=companies_text(len(companies)))
    for ats in ATSES:
        table.add_row(ats, str(counts[ats]))
    app.console.print(table)
    text = (args.search or "").lower()
    shown = [
        company for company in companies
        if (not args.ats or company.ats == args.ats) and (text in company.name.lower() or text in company.slug.lower())
    ]
    table = Table("Company", "ATS", "Board")
    for company in sorted(shown, key=lambda company: company.name.lower()):
        table.add_row(Text(company.name), company.ats, Text(company.slug))
    app.console.print(table)
    return 0


def add(app, args) -> int:
    company = board_from(args.board)
    state, jobs, note = board_state(source_for(app, company.ats), company)
    if state != "live":
        problem = "could not be checked" if state == "unknown" else "is not a live job board"
        raise HirejutsuError(f"{company.key} {problem}: {note}")
    company = Company(company.ats, company.slug, args.name or note or plain_name(company))
    path = save_companies(app.home, [company])
    app.console.print(Text(f"Added {company.name} ({company.key}) with {jobs} open jobs to {path}"))
    return 0


def remove(app, args) -> int:
    wanted = board_from(args.board)
    found = next((company for company in load_companies(app.config) if company.key == wanted.key), None)
    if not found:
        raise HirejutsuError(f"{wanted.key} is not in the list. See 'hirejutsu companies list'.")
    path = drop_companies(app.home, [found])
    app.console.print(Text(f"Removed {found.name} ({found.key}). It is listed under removed in {path}."))
    return 0


def check(app, args) -> int:
    companies = [company for company in load_companies(app.config) if not args.ats or company.ats == args.ats]
    with app.console.status(f"Checking {companies_text(len(companies))}..."):
        states = check_boards(app, companies)
    counts = Counter(state for state, _, _ in states)
    if counts["dead"] or counts["unknown"]:
        table = Table("Company", "Board", "State", "Why")
        for company, (state, _, note) in zip(companies, states):
            if state != "live":
                table.add_row(Text(company.name), Text(company.key), state, Text(note))
        app.console.print(table)
    app.console.print(f"{counts['live']} live, {counts['dead']} dead, {counts['unknown']} could not be checked")
    dead = [company for company, (state, _, _) in zip(companies, states) if state == "dead"]
    if dead and args.prune:
        path = drop_companies(app.home, dead)
        boards = "board" if len(dead) == 1 else "boards"
        app.console.print(Text(f"Stopped fetching {len(dead)} dead {boards}. They are listed under removed in {path}."))
    elif dead:
        app.console.print("Run 'hirejutsu companies check --prune' to stop fetching the dead ones.")
        return 1
    return 0


def check_boards(app, companies: list[Company]) -> list[tuple[str, int, str]]:
    sources = {ats: source_for(app, ats) for ats in {company.ats for company in companies}}
    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as pool:
        return list(pool.map(lambda company: board_state(sources[company.ats], company), companies))


def board_from(text: str) -> Company:
    found = detect(text)
    if not found:
        raise HirejutsuError(
            f"Cannot tell the job board from '{text}'. Give its careers page URL or ats:board, like greenhouse:stripe."
        )
    return Company(*found)


def plain_name(company: Company) -> str:
    """A name for a board that gives none: its board name, or the tenant for Workday."""
    return company.slug.partition(".")[0] if company.ats == "workday" else company.slug


def source_for(app, ats: str):
    return available()[ats](app.config, app.client)


def board_state(source, company: Company) -> tuple[str, int, str]:
    """("live", open jobs, company name), ("dead", 0, why), or ("unknown", 0, why) when it could not be checked."""
    try:
        jobs, name = source.probe(company)
    except requests.HTTPError as exc:
        return "dead" if exc.response.status_code in GONE else "unknown", 0, str(exc)
    except (ValueError, ElementTree.ParseError):
        # Some boards, like BambooHR, send unknown names to their home page.
        return "dead", 0, "the answer is not a job list"
    except Exception as exc:
        return "unknown", 0, f"{type(exc).__name__}: {exc}"
    if not jobs:
        return "dead", 0, "no open jobs"
    return "live", jobs, name
