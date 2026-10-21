"""doctor command."""

from rich.text import Text

from ..doctor import FAIL, run_checks

STYLES = {"ok": "green", "warn": "yellow", "fail": "red"}


def register(sub) -> None:
    parser = sub.add_parser("doctor", help="check that everything is ready for the daily run")
    parser.set_defaults(func=doctor)


def doctor(app, args) -> int:
    results = run_checks(app)
    for status, part, detail in results:
        line = Text(f"{status:<5}", style=STYLES[status])
        line.append(f" {part:<11} {detail}")
        app.console.print(line)
    return 1 if any(status == FAIL for status, _, _ in results) else 0
