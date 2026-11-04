"""applicant command."""

from rich.markup import escape

from ..applicant import applicant_path, found_in_resume, load_applicant, starter_text
from ..desktop import edit_file
from ..errors import HirejutsuError
from ..resume import read_text, resume_path


def register(sub) -> None:
    parser = sub.add_parser("applicant", help="show your details for applications and emails")
    parser.add_argument("--edit", action="store_true", help="open the file, starting it from your resume the first time")
    parser.set_defaults(func=applicant)


def applicant(app, args) -> int:
    path = applicant_path(app.config)
    if args.edit:
        if not path.exists():
            start_file(app, path)
        edit_file(path)
        return 0
    if not path.exists():
        app.console.print(f"No details at {path} yet. Run 'hirejutsu applicant --edit' to start them from your resume.")
        return 1
    details = load_applicant(app.config)
    phone = " ".join(part for part in (details.phone_code, details.phone) if part) if details.phone else ""
    rows = [
        ("Details", str(path)),
        ("Name", details.name),
        ("Email", details.email),
        ("Phone", phone),
        ("Links", ", ".join(details.links.values())),
        ("Work", "; ".join(f"{job.title} at {job.company}" for job in details.work)),
        ("Education", "; ".join(school.school for school in details.education)),
        ("Answers", ", ".join(details.answers)),
    ]
    for label, value in rows:
        app.console.print(f"[bold]{label}:[/bold] {escape(value or 'none')}")
    if details.missing():
        app.console.print(f"[bold]Missing:[/bold] {', '.join(details.missing())}")
    return 0


def start_file(app, path) -> None:
    """Write the starter file with what the resume already says."""
    try:
        found = found_in_resume(read_text(resume_path(app.config)))
    except HirejutsuError:
        found = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(starter_text(found), encoding="utf-8")
    if found:
        app.console.print(f"Created {path}, filled in from your resume: {', '.join(found)}. Check them and add the rest.")
    else:
        app.console.print(f"Created {path}")
