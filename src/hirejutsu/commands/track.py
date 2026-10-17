"""Commands for keeping track of what you did with each job."""

from datetime import datetime

from rich.markup import escape
from rich.text import Text

from ..errors import HirejutsuError
from ..models import Job, Match
from ..store import STATUSES, Store


def register(sub) -> None:
    for name, status, summary in (
        ("applied", "applied", "mark jobs you applied to"),
        ("skip", "skipped", "mark jobs you will not apply to"),
        ("save", "saved", "keep jobs to apply to later"),
    ):
        parser = sub.add_parser(name, help=summary)
        add_ids(parser)
        parser.add_argument("--note", metavar="TEXT", help="a note to keep with the change")
        parser.set_defaults(func=mark, status=status)

    parser = sub.add_parser("status", help="set any status, like interview, offer or rejected")
    add_ids(parser)
    parser.add_argument("status", choices=STATUSES, metavar="STATUS", help=", ".join(STATUSES))
    parser.add_argument("--note", metavar="TEXT", help="a note to keep with the change")
    parser.set_defaults(func=mark)


def add_ids(parser) -> None:
    parser.add_argument("ids", nargs="+", type=int, metavar="ID", help="job ids, or pick numbers with -t")
    parser.add_argument("-t", "--today", action="store_true", help="numbers refer to today's picks (the # column)")


def print_error(console, exc: Exception) -> None:
    console.print(f"[red]error:[/red] {escape(str(exc))}")


def todays_picks(store: Store) -> list[Match]:
    day = datetime.now().astimezone().date()
    picks = store.picks(day)
    if not picks:
        raise HirejutsuError(f"No picks for {day}. Run 'hirejutsu run' first.")
    return picks


def find_job(store: Store, number: int, picks: list[Match] | None = None) -> Job:
    """The job with this id, or the job at this place in picks when picks are given."""
    if picks is not None:
        if not 1 <= number <= len(picks):
            raise HirejutsuError(f"No pick #{number} today. See 'hirejutsu today'.")
        return picks[number - 1].job
    job = store.get_job(number)
    if job is None:
        raise HirejutsuError(f"No job with id {number}")
    return job


def named_jobs(app, args) -> list[Job]:
    """The jobs given on the command line. Each number that matches nothing is reported."""
    picks = todays_picks(app.store) if args.today else None
    jobs = []
    for number in args.ids:
        try:
            jobs.append(find_job(app.store, number, picks))
        except HirejutsuError as exc:
            print_error(app.console, exc)
    return jobs


def mark(app, args) -> int:
    jobs = named_jobs(app, args)
    for job in jobs:
        app.store.set_status(job.id, args.status, args.note)
        app.console.print(Text(f"Marked job {job.id} as {args.status}: {job.title} at {job.company}"))
    return 0 if len(jobs) == len(args.ids) else 1
