"""Commands for keeping track of what you did with each job."""

from datetime import datetime

from rich.markup import escape
from rich.style import Style
from rich.table import Table
from rich.text import Text

from ..errors import HirejutsuError
from ..models import Job, Match
from ..store import STATUSES, Store

DESCRIPTION_LINES = 40


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

    parser = sub.add_parser("note", help="add a note to a job without changing its status")
    add_ids(parser, nargs=1)
    parser.add_argument("text", nargs="+", metavar="TEXT", help="the note, quotes are optional")
    parser.set_defaults(func=note)

    parser = sub.add_parser("show", help="show everything saved about a job")
    add_ids(parser)
    parser.set_defaults(func=show)


def add_ids(parser, nargs="+") -> None:
    parser.add_argument("ids", nargs=nargs, type=int, metavar="ID", help="job id, or pick number with -t")
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


def note(app, args) -> int:
    jobs = named_jobs(app, args)
    for job in jobs:
        app.store.add_note(job.id, " ".join(args.text))
        app.console.print(Text(f"Added a note to job {job.id}: {job.title} at {job.company}"))
    return 0 if jobs else 1


def local(value: datetime | None, fmt: str = "%Y-%m-%d") -> str:
    return value.astimezone().strftime(fmt) if value else ""


def salary(job: Job) -> str:
    amounts = " - ".join(f"{value:,.0f}" for value in (job.salary_min, job.salary_max) if value)
    if not amounts:
        return ""
    period = f" per {job.salary_period}" if job.salary_period else ""
    return f"{job.salary_currency} {amounts}{period}".strip()


def show(app, args) -> int:
    jobs = named_jobs(app, args)
    for job in jobs:
        print_job(app.console, job, app.store.history(job.id))
    return 0 if len(jobs) == len(args.ids) else 1


def print_job(console, job: Job, history: list) -> None:
    console.print(Text(f"{job.title} at {job.company}", style=Style(bold=True, link=job.url)))
    current = f"{job.status} since {local(job.status_at)}" if job.status_at else job.status
    remote = "" if job.remote is None else "yes" if job.remote else "no"
    details = Table.grid(padding=(0, 2))
    for label, value in (
        ("ID", str(job.id)),
        ("Status", current),
        ("Location", job.location),
        ("Remote", remote),
        ("Salary", salary(job)),
        ("Type", job.employment_type),
        ("Department", job.department),
        ("Posted", local(job.posted_at)),
        ("First seen", local(job.first_seen)),
        ("Last seen", local(job.last_seen)),
        ("Source", job.source),
        ("Link", job.url),
    ):
        if value:
            details.add_row(label, Text(value))
    console.print(details)
    notes = [f"{local(at)}  {text}" for _, at, text in history if text]
    changes = [f"{local(at, '%Y-%m-%d %H:%M')}  {status}" for status, at, _ in history if status]
    print_section(console, "Notes", notes)
    print_section(console, "History", changes)
    lines = job.description.splitlines()
    hidden = len(lines) - DESCRIPTION_LINES
    if hidden > 0:
        lines = lines[:DESCRIPTION_LINES] + [f"... {hidden} more lines, open the link to read on"]
    print_section(console, "Description", lines)


def print_section(console, title: str, lines: list[str]) -> None:
    if lines:
        console.print()
        console.print(Text(title, style="bold"))
        console.print(Text("\n".join(lines)))
