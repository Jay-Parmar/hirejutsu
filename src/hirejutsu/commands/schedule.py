"""schedule command: run hirejutsu every morning by itself."""

import argparse
from datetime import datetime, time

from rich.text import Text

from .. import schedule


def clock(value: str) -> time:
    """Parse a 24 hour HH:MM time for --time."""
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a time, use HH:MM like 07:30") from None


def register(sub) -> None:
    parser = sub.add_parser("schedule", help="run hirejutsu every morning by itself")
    actions = parser.add_subparsers(dest="action", metavar="action", required=True)
    for name, func, help_text in (
        ("install", install, "run every morning from now on"),
        ("show", show, "print what install would register, without registering it"),
    ):
        action = actions.add_parser(name, help=help_text)
        action.add_argument("--time", type=clock, default="09:00", metavar="HH:MM", help="when to run (default 09:00)")
        action.add_argument("--weekdays", action="store_true", help="run Monday to Friday only")
        action.add_argument("--wake", action="store_true", help="wake the PC from sleep to run (Windows only)")
        action.set_defaults(func=func)
    actions.add_parser("status", help="show the next and last run").set_defaults(func=status)
    actions.add_parser("remove", help="stop running every morning").set_defaults(func=remove)


def install(app, args) -> int:
    schedule.install(app.home, args.time, args.weekdays, args.wake)
    days = "weekday" if args.weekdays else "day"
    app.console.print(f"hirejutsu will run every {days} at {args.time:%H:%M}. See 'hirejutsu schedule status'.")
    return 0


def show(app, args) -> int:
    app.console.print(schedule.task_xml(app.home, args.time, args.weekdays, args.wake), markup=False, highlight=False)
    return 0


def status(app, args) -> int:
    rows = schedule.status()
    if rows is None:
        app.console.print("hirejutsu is not scheduled. Set it up with 'hirejutsu schedule install'.")
        return 1
    for label, value in rows:
        app.console.print(Text(f"{label:<12}{value}"))
    return 0


def remove(app, args) -> int:
    if schedule.remove():
        app.console.print("Removed. hirejutsu will no longer run by itself.")
    else:
        app.console.print("hirejutsu is not scheduled, nothing to remove.")
    return 0
