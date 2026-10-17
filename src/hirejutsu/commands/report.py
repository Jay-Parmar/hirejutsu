"""report command."""

from datetime import date
from pathlib import Path

from ..desktop import open_url
from ..report import FORMATS, report_settings, save_reports


def register(sub) -> None:
    parser = sub.add_parser("report", help="rebuild a day's report files from its saved picks")
    parser.add_argument("--day", type=date.fromisoformat, help="another day (YYYY-MM-DD), default today")
    parser.add_argument(
        "--format", nargs="+", choices=FORMATS, dest="formats", metavar="FORMAT",
        help=f"formats to write: {', '.join(FORMATS)} (default: report.formats in the config)",
    )
    parser.add_argument("--open", action="store_true", help="open the HTML report in your browser")
    parser.set_defaults(func=report)


def report(app, args) -> int:
    day = args.day or date.today()
    matches = app.store.picks(day)
    if not matches:
        app.console.print(f"No picks for {day}. Run 'hirejutsu run' first.")
        return 1
    formats = args.formats or report_settings(app.config)["formats"]
    show_saved(app, save_reports(matches, app.config, day, formats), args.open)
    return 0


def show_saved(app, paths: list[Path], open_html: bool) -> None:
    """Print the saved report files and open the HTML one in the browser if asked."""
    for path in paths:
        app.console.print(f"Saved {path}")
    if not open_html:
        return
    pages = [path for path in paths if path.suffix == ".html"]
    if pages:
        open_url(pages[0].as_uri())
    else:
        app.console.print("No HTML report to open. Add html to the report formats.")
