"""Showing and saving the daily picks."""

from datetime import date
from html import escape
from importlib import resources
from pathlib import Path
from string import Template

from rich.style import Style
from rich.table import Table
from rich.text import Text

from .config import Config
from .errors import HirejutsuError
from .models import Job, Match

REPORT_DEFAULTS = {"formats": ["md", "html"]}
FORMATS = ("md", "html")


def report_settings(config: Config) -> dict:
    """The report section of the config over its defaults. Unknown formats are an error."""
    settings = config.section("report", REPORT_DEFAULTS)
    unknown = [name for name in settings["formats"] if name not in FORMATS]
    if unknown:
        raise HirejutsuError(f"Unknown report format: {', '.join(unknown)}. Use one of: {', '.join(FORMATS)}")
    return settings


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
    today = date.today()
    table = Table("#", "ID", "Score", "Job", "Company", "Location", "Salary", "Posted", title=title)
    for number, match in enumerate(matches, start=1):
        job = match.job
        table.add_row(
            str(number),
            str(job.id),
            f"{match.score:.2f}",
            Text(job.title, style=Style(link=job.url)),
            Text(job.company),
            Text(where(match)),
            Text(salary(job)),
            age(job, today),
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


def html_page(matches: list[Match], day: date) -> str:
    """The day's picks as one HTML file that loads nothing from the internet."""
    page = Template(resources.files("hirejutsu").joinpath("data", "report.html").read_text(encoding="utf-8"))
    count = len(matches)
    return page.substitute(
        title=f"Job picks for {day.isoformat()}",
        heading=f"Job picks for {day:%A}, {day.day} {day:%B %Y}",
        count=f"{count} job picked" if count == 1 else f"{count} jobs picked",
        picks="\n".join(_pick_html(number, match, day) for number, match in enumerate(matches, start=1)),
    )


def _pick_html(number: int, match: Match, day: date) -> str:
    job = match.job
    link = escape(_web_link(job.url))
    reasons = "".join(f"<li>{escape(reason)}</li>" for reason in match.reasons)
    command = f"hirejutsu applied {job.id}"
    return f"""<li class="pick">
<div class="rank">{number}</div>
<div>
<h2><a href="{link}" target="_blank" rel="noopener noreferrer">{escape(job.title)}</a></h2>
<p class="company">{escape(job.company)}</p>
<p class="facts">{_facts_html(job, day)}</p>
<p class="score"><span class="bar"><span style="width: {round(match.score * 100)}%"></span></span>Score {match.score:.2f}</p>
<ul class="reasons">{reasons}</ul>
<p class="actions"><a class="open" href="{link}" target="_blank" rel="noopener noreferrer">Open</a>
<span class="command"><code>{command}</code><button type="button" data-command="{command}">Copy</button></span></p>
</div>
</li>"""


def _facts_html(job: Job, day: date) -> str:
    facts = []
    if job.location:
        facts.append(f"<span>{escape(job.location)}</span>")
    if job.remote:
        facts.append('<span class="remote">Remote</span>')
    pay = salary(job)
    if pay:
        facts.append(f"<span>{escape(pay)}</span>")
    since = age(job, day)
    if since:
        facts.append(f"<span>posted {since}</span>")
    return "".join(facts)


def _web_link(url: str) -> str:
    """The job link, or "#" for anything that is not http(s), like a javascript: link from a bad listing."""
    return url if url.lower().startswith(("http://", "https://")) else "#"


def render(fmt: str, matches: list[Match], day: date) -> str:
    if fmt == "html":
        return html_page(matches, day)
    return markdown(matches, day)


def write_reports(matches: list[Match], config: Config, day: date) -> list[Path]:
    """Save the day's picks in each configured format. Returns the files written."""
    folder = config.reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for fmt in report_settings(config)["formats"]:
        path = folder / f"{day.isoformat()}.{fmt}"
        path.write_text(render(fmt, matches, day), encoding="utf-8")
        paths.append(path)
    return paths
