"""run, today and top commands."""

from datetime import date, datetime

from ..daily import candidates, pick_today
from ..ranking import RANKING_DEFAULTS, rank
from ..report import print_picks, report_settings, write_reports
from ..resume import load_profile
from .fetch import fetch_jobs, print_results
from .notify import send_picks
from .report import show_saved


def register(sub) -> None:
    parser = sub.add_parser("run", help="fetch jobs and pick today's best matches")
    parser.add_argument("--no-fetch", action="store_true", help="rank the jobs already saved")
    parser.add_argument("--open", action="store_true", help="open the HTML report in your browser")
    parser.add_argument("--no-notify", action="store_true", help="do not send the picks to your notify channels")
    parser.add_argument("--log", action="store_true", help="write all output to logs/run-YYYY-MM-DD.log instead")
    parser.set_defaults(func=run)

    parser = sub.add_parser("today", help="show the jobs picked today")
    parser.add_argument("--day", type=date.fromisoformat, help="show another day (YYYY-MM-DD)")
    parser.set_defaults(func=today)

    parser = sub.add_parser("top", help="rank saved jobs without recording picks")
    parser.add_argument("-n", type=int, default=20, help="how many to show (default 20)")
    parser.set_defaults(func=top)


def run(app, args) -> int:
    now = datetime.now().astimezone()
    profile = load_profile(app.config)
    reports = report_settings(app.config)
    if not args.no_fetch:
        print_results(app.console, fetch_jobs(app))
    matches = pick_today(app.store, app.config, profile, now)
    if not matches:
        app.console.print("No matching jobs today. Add sources or skills and try again.")
        return 0
    print_picks(app.console, matches, title=f"Picks for {now.date()}")
    files = write_reports(matches, app.config, now.date())
    show_saved(app, files, args.open or reports["open"])
    if not args.no_notify:
        send_picks(app, matches, now.date(), files)
    return 0


def today(app, args) -> int:
    day = args.day or datetime.now().astimezone().date()
    matches = app.store.picks(day)
    if not matches:
        app.console.print(f"No picks for {day}. Run 'hirejutsu run' first.")
        return 1
    print_picks(app.console, matches, title=f"Picks for {day}")
    return 0


def top(app, args) -> int:
    profile = load_profile(app.config)
    settings = {**app.config.section("ranking", RANKING_DEFAULTS), "top": args.n}
    matches = rank(candidates(app.store, datetime.now().astimezone()), profile, settings)
    print_picks(app.console, matches)
    return 0
