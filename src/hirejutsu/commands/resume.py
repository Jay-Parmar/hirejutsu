"""resume command."""

from rich.markup import escape

from ..resume import load_profile, resume_path

FEW_SKILLS = 5


def register(sub) -> None:
    parser = sub.add_parser("resume", help="show what was read from your resume")
    parser.add_argument("--text", action="store_true", help="print the text read from the resume")
    parser.set_defaults(func=resume)


def resume(app, args) -> int:
    profile = load_profile(app.config)
    if args.text:
        app.console.out(profile.text, highlight=False)
        return 0
    rows = [
        ("Resume", f"{resume_path(app.config)} ({len(profile.text)} characters)"),
        (f"Skills ({len(profile.skills)})", ", ".join(profile.skills) or "none found"),
        ("Titles", ", ".join(profile.titles) or "none found"),
        ("Years of experience", "unknown" if profile.years is None else str(profile.years)),
        ("Locations", ", ".join(profile.locations) or "none"),
    ]
    for label, value in rows:
        app.console.print(f"[bold]{escape(label)}:[/bold] {escape(value)}")
    if len(profile.skills) < FEW_SKILLS:
        app.console.print("Few skills were found. Add yours under profile.skills ('hirejutsu config --edit').")
    return 0
