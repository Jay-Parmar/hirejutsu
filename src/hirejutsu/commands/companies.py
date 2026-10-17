"""companies command: the company career pages that the ATS sources read."""

from collections import Counter

from rich.table import Table
from rich.text import Text

from ..companies import ATSES, load_companies


def register(sub) -> None:
    parser = sub.add_parser("companies", help="list, add, remove and check company career pages")
    parser.set_defaults(func=list_companies, ats=None, search=None)
    actions = parser.add_subparsers(dest="action", metavar="action")

    action = actions.add_parser("list", help="count the companies of each ATS and list them (the default)")
    action.add_argument("--ats", choices=ATSES, help="only companies on this ATS")
    action.add_argument("--search", metavar="TEXT", help="only companies whose name or board contains TEXT")
    action.set_defaults(func=list_companies)


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
