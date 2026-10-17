"""fetch and sources commands."""

from rich.table import Table

from ..pipeline import FetchResult, fetch_all
from ..sources import available, load_sources

FETCH_DEFAULTS = {"workers": 8}


def register(sub) -> None:
    parser = sub.add_parser("fetch", help="download jobs from your sources")
    parser.add_argument(
        "-s", "--source", action="append", dest="sources", metavar="NAME",
        help="fetch only this source, can be repeated",
    )
    parser.set_defaults(func=fetch)

    parser = sub.add_parser("sources", help="list job sources and their last fetch")
    parser.set_defaults(func=list_sources)


def fetch_jobs(app, names: list[str] | None = None) -> list[FetchResult]:
    found = load_sources(app.config, app.client, names)
    settings = app.config.section("fetch", FETCH_DEFAULTS)
    with app.console.status(f"Fetching from {len(found)} sources..."):
        return fetch_all(found, app.store, workers=settings["workers"])


def print_results(console, results: list[FetchResult]) -> None:
    table = Table("Source", "Found", "New", "Seconds", "Error")
    for result in sorted(results, key=lambda r: r.source):
        table.add_row(result.source, str(result.found), str(result.added), f"{result.seconds:.1f}", result.error)
    console.print(table)


def fetch(app, args) -> int:
    results = fetch_jobs(app, args.sources)
    if not results:
        app.console.print("No sources are enabled. See 'hirejutsu sources'.")
        return 1
    print_results(app.console, results)
    return 1 if all(result.error for result in results) else 0


def list_sources(app, args) -> int:
    last = {row["source"]: row for row in app.store.last_fetches()}
    table = Table("Source", "Enabled", "Last fetch", "Found", "New", "Error")
    for name, cls in available().items():
        enabled = cls(app.config, app.client).settings["enabled"]
        row = last.get(name)
        if row:
            table.add_row(name, "yes" if enabled else "no", row["started_at"][:16].replace("T", " "),
                          str(row["found"]), str(row["added"]), row["error"])
        else:
            table.add_row(name, "yes" if enabled else "no", "never", "", "", "")
    app.console.print(table)
    return 0
