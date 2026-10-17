"""Showing and saving the daily picks."""

from datetime import date
from pathlib import Path

from rich.style import Style
from rich.table import Table
from rich.text import Text

from .config import Config
from .models import Match


def where(match: Match) -> str:
    job = match.job
    if job.location:
        return job.location
    return "Remote" if job.remote else ""


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
        lines.append(f"## {number}. {job.title} at {job.company}")
        lines.append(" | ".join(part for part in (where(match), f"score {match.score:.2f}", f"id {job.id}") if part))
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
