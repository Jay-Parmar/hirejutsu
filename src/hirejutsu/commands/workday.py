"""workday command."""

from pathlib import Path

from rich.markup import escape

from .. import browser
from ..applicant import applicant_path, load_applicant
from ..errors import HirejutsuError
from ..resume import load_profile, resume_path
from ..workday import PAUSE, STEPS, UPLOADS, Report, WindowClosed, fill_step, load_settings, save_fields, steps

# Longest value shown when telling what was filled.
SHOWN = 60


def register(sub) -> None:
    parser = sub.add_parser("workday", help="fill a Workday application in a browser window, you sign in and submit")
    parser.add_argument("link", help="the job's link on its Workday career site")
    parser.add_argument(
        "--dump", action="store_true", help="also save the fields of each step, never their values, to the logs folder"
    )
    parser.set_defaults(func=workday)


def workday(app, args) -> int:
    path = applicant_path(app.config)
    if not path.exists():
        app.console.print(f"No details at {path} yet. Run 'hirejutsu applicant --edit' first.")
        return 1
    details = load_applicant(app.config)
    settings = load_settings(app.config)
    skills, resume = from_resume(app, settings["max_skills"])
    link = args.link if "://" in args.link else f"https://{args.link}"
    app.console.print(f"Opening {escape(link)} in {browser.NAMES[settings['browser']]}.")
    with browser.open_window(settings) as page:
        page.goto(link)
        app.console.print("Click Apply and sign in yourself. Each step is filled as it shows, then you check it.")
        reports: list[Report] = []
        try:
            for step in steps(page):
                if step in STEPS:
                    reports.append(fill_step(page, step, details, skills, resume))
                    show(app, reports[-1])
                if args.dump:
                    saved = save_fields(page, step, page.url, app.config.logs_dir)
                    app.console.print(f"Saved the fields of {escape(step)} to {saved}")
        except WindowClosed:
            app.console.print(f"The window was closed. {summary(reports)}")
            return 0
        app.console.print(f"{summary(reports)} Check the Review step and submit it yourself.")
        app.console.print("hirejutsu stops when you close the window.")
        wait_closed(page)
    return 0


def from_resume(app, max_skills: int) -> tuple[list[str], Path | None]:
    """The skills to add and the resume to upload. Without a resume both are left for you."""
    try:
        skills, resume = load_profile(app.config).skills[:max_skills], resume_path(app.config)
    except HirejutsuError as exc:
        app.console.print(f"{escape(str(exc))} Skills and the resume upload are left for you.")
        return [], None
    if resume.suffix.lower() not in UPLOADS:
        app.console.print(f"Workday takes a PDF or DOCX resume, so {resume.name} is left for you to upload.")
    return skills, resume


def show(app, report: Report) -> None:
    """What was filled on a step, and what was left."""
    fields = "field" if len(report.filled) == 1 else "fields"
    app.console.print(f"[bold]{escape(report.step)}[/bold]: filled {len(report.filled)} {fields}")
    for label, value in report.filled:
        value = " ".join(value.split())
        shown = value if len(value) <= SHOWN else value[: SHOWN - 3] + "..."
        app.console.print(f"  {escape(label)}: {escape(shown)}")
    if report.left:
        left = [(item.label or "a field without a label") + (" (required)" if item.required else "") for item in report.left]
        app.console.print(f"  Left for you: {escape(', '.join(left))}")
    app.console.print("  Check the page, then click Save and Continue yourself.")


def summary(reports: list[Report]) -> str:
    filled = sum(len(report.filled) for report in reports)
    fields = "field" if filled == 1 else "fields"
    return f"Filled {filled} {fields} on {len(reports)} {'step' if len(reports) == 1 else 'steps'}."


def wait_closed(page) -> None:
    """Wait while you check the application and submit it."""
    try:
        while True:
            page.wait(PAUSE)
    except WindowClosed:
        pass
