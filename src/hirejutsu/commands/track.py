"""Commands for keeping track of what you did with each job."""

import csv
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from rich.markup import escape
from rich.style import Style
from rich.table import Column, Table
from rich.text import Text

from ..desktop import open_url
from ..errors import HirejutsuError
from ..models import Job, Match
from ..store import STATUSES, Store

DESCRIPTION_LINES = 40
TRACKED = tuple(status for status in STATUSES if status != "new")
EXPORT_COLUMNS = [
    "id", "title", "company", "location", "status", "changed", "applied", "posted",
    "first_seen", "last_seen", "url", "notes",
]


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

    parser = sub.add_parser("open", help="open job links in your browser")
    add_ids(parser)
    parser.set_defaults(func=open_links)

    parser = sub.add_parser("list", help="list tracked jobs, latest change first")
    add_status_filter(parser)
    parser.add_argument("--since", type=int, metavar="DAYS", help="only jobs changed in the last DAYS days")
    parser.add_argument("--company", metavar="TEXT", help="only companies whose name contains TEXT")
    parser.add_argument("-n", type=int, default=50, metavar="LIMIT", help="how many to show (default 50)")
    parser.set_defaults(func=list_jobs)

    parser = sub.add_parser("stats", help="show how your applications are going")
    parser.set_defaults(func=stats)

    parser = sub.add_parser("export", help="save tracked jobs to a CSV file")
    add_status_filter(parser)
    parser.add_argument("-o", "--output", type=Path, metavar="PATH",
                        help="file to write (default: tracked-jobs-<date>.csv in the data folder)")
    parser.set_defaults(func=export)


def add_ids(parser, nargs="+") -> None:
    parser.add_argument("ids", nargs=nargs, type=int, metavar="ID", help="job id, or pick number with -t")
    parser.add_argument("-t", "--today", action="store_true", help="numbers refer to today's picks (the # column)")


def add_status_filter(parser) -> None:
    parser.add_argument(
        "--status", nargs="+", action="extend", choices=STATUSES, metavar="STATUS",
        help="only jobs with these statuses (default: all but new)",
    )


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


def open_links(app, args) -> int:
    jobs = named_jobs(app, args)
    for job in jobs:
        app.console.print(Text(f"Opening job {job.id}: {job.url}"))
        open_url(job.url)
    return 0 if len(jobs) == len(args.ids) else 1


def place(job: Job) -> str:
    return job.location or ("Remote" if job.remote else "")


def changed_at(job: Job) -> datetime:
    """When the job got its current status. New jobs count from when they were first seen."""
    return job.status_at or job.first_seen


def tracked_jobs(store: Store, statuses: list[str] | None) -> list[Job]:
    """Jobs with these statuses, or with any status but new, latest change first."""
    return sorted(store.find_jobs(statuses=statuses or TRACKED), key=changed_at, reverse=True)


def list_jobs(app, args) -> int:
    jobs = tracked_jobs(app.store, args.status)
    if args.since is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.since)
        jobs = [job for job in jobs if changed_at(job) >= cutoff]
    if args.company:
        jobs = [job for job in jobs if args.company.lower() in job.company.lower()]
    if not jobs:
        app.console.print("No matching jobs.")
        return 0
    fixed = [Column(header, no_wrap=True) for header in ("ID", "Status", "Since")]
    table = Table(*fixed, "Job", "Company", "Location", "Note")
    for job in jobs[:args.n]:
        table.add_row(
            str(job.id), job.status, local(changed_at(job)), Text(job.title, style=Style(link=job.url)),
            Text(job.company), Text(place(job)), Text(job.note),
        )
    app.console.print(table)
    if len(jobs) > args.n:
        app.console.print(f"Showing {args.n} of {len(jobs)}. Use -n to see more.")
    return 0


def per_week(days: list[date], today: date, weeks: int = 8) -> list[tuple[date, int]]:
    """How many of the days fall in each of the last few weeks, oldest first. Weeks start on Monday."""
    counts = Counter(day - timedelta(days=day.weekday()) for day in days)
    this_monday = today - timedelta(days=today.weekday())
    mondays = [this_monday - timedelta(weeks=back) for back in reversed(range(weeks))]
    return [(monday, counts[monday]) for monday in mondays]


def stats(app, args) -> int:
    console = app.console
    counts = app.store.status_counts()
    table = Table("Status", Column("Jobs", justify="right"), title="Jobs by status")
    for status in STATUSES:
        table.add_row(status, str(counts.get(status, 0)))
    console.print(table)

    applications = app.store.applications()
    days = [at.astimezone().date() for _, at, _ in applications]
    table = Table("Week of", Column("Applied", justify="right"), "", title="Applications per week")
    for monday, count in per_week(days, datetime.now().astimezone().date()):
        table.add_row(monday.isoformat(), str(count), "#" * count)
    console.print(table)

    if applications:
        answered = sum(1 for _, _, got_answer in applications if got_answer)
        console.print(
            f"Response rate: {answered / len(applications):.0%} "
            f"({answered} of {len(applications)} applications got an interview or offer)"
        )
    else:
        console.print("Response rate: no applications yet")
    console.print(f"Picks shown: {app.store.pick_count()}")
    top = Counter(company for company, _, _ in applications).most_common(5)
    if top:
        console.print(Text("Top companies: " + ", ".join(f"{company} ({count})" for company, count in top)))
    return 0


def export_row(job: Job, history: list) -> list:
    applied = next((at for status, at, _ in history if status == "applied"), None)
    notes = "; ".join(text for _, _, text in history if text)
    return [
        job.id, job.title, job.company, place(job), job.status, local(job.status_at), local(applied),
        local(job.posted_at), local(job.first_seen), local(job.last_seen), job.url, notes,
    ]


def export(app, args) -> int:
    path = args.output or app.home / f"tracked-jobs-{datetime.now().astimezone().date()}.csv"
    rows = [export_row(job, app.store.history(job.id)) for job in tracked_jobs(app.store, args.status)]
    try:
        # The BOM makes Excel read the file as UTF-8 instead of the Windows code page.
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(EXPORT_COLUMNS)
            writer.writerows(rows)
    except OSError as exc:
        raise HirejutsuError(f"Cannot write {path}: {exc.strerror}") from exc
    app.console.print(Text(f"Saved {len(rows)} jobs to {path}"))
    return 0
