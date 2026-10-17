"""Showing and saving the daily picks."""

from datetime import date
from pathlib import Path

from rich.style import Style
from rich.table import Table
from rich.text import Text

from .config import Config
from .models import Job, Match


def where(match: Match) -> str:
    job = match.job
    if job.location:
        return job.location
    return "Remote" if job.remote else ""


def amount(value: float, currency: str) -> str:
    """Group digits the way people read them: 18,00,000 for INR, 1,800,000 for the rest."""
    if currency.upper() != "INR":
        return f"{value:,.2f}" if value % 1 else f"{value:,.0f}"
    digits = str(round(value))
    groups = [digits[-3:]]
    digits = digits[:-3]
    while digits:
        groups.insert(0, digits[-2:])
        digits = digits[:-2]
    return ",".join(groups)


def salary(job: Job) -> str:
    """Pay as text, like "INR 18,00,000 - 25,00,000 / year". Empty when unknown."""
    values = sorted({value for value in (job.salary_min, job.salary_max) if value})
    if not values:
        return ""
    text = " - ".join(amount(value, job.salary_currency) for value in values)
    if job.salary_currency:
        text = f"{job.salary_currency} {text}"
    if job.salary_period:
        text = f"{text} / {job.salary_period}"
    return text


def age(job: Job, today: date) -> str:
    """How long ago the job was posted, like "2 days ago". Empty when unknown."""
    if job.posted_at is None:
        return ""
    days = (today - job.posted_at.astimezone().date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def print_picks(console, matches: list[Match], title: str | None = None) -> None:
    table = Table("#", "ID", "Score", "Job", "Company", "Location", title=title)
    for number, match in enumerate(matches, start=1):
        job = match.job
        table.add_row(
            str(number),
            str(job.id),
            f"{match.score:.2f}",
            Text(job.title, style=Style(link=job.url)),
            Text(job.company),
            Text(where(match)),
        )
    console.print(table)
    for number, match in enumerate(matches, start=1):
        console.print(Text(f"{number}. {match.job.url}"))


def markdown(matches: list[Match], day: date) -> str:
    lines = [f"# Job picks for {day.isoformat()}", ""]
    for number, match in enumerate(matches, start=1):
        job = match.job
        since = age(job, day)
        facts = [where(match), salary(job), f"posted {since}" if since else "",
                 f"score {match.score:.2f}", f"id {job.id}"]
        lines.append(f"## {number}. {job.title} at {job.company}")
        lines.append(" | ".join(fact for fact in facts if fact))
        lines.append("")
        lines += [f"- {reason}" for reason in match.reasons]
        lines += [f"- Apply: {job.url}", ""]
    return "\n".join(lines)


def write_reports(matches: list[Match], config: Config, day: date) -> list[Path]:
    folder = config.reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{day.isoformat()}.md"
    path.write_text(markdown(matches, day), encoding="utf-8")
    return [path]
