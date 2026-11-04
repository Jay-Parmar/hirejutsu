"""applicant command."""

from rich.markup import escape

from ..applicant import applicant_path, load_applicant


def register(sub) -> None:
    parser = sub.add_parser("applicant", help="show your details for applications and emails")
    parser.set_defaults(func=applicant)


def applicant(app, args) -> int:
    path = applicant_path(app.config)
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
