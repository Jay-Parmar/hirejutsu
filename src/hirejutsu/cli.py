"""Command line interface."""

import argparse
import logging

from rich.markup import escape

from . import __version__
from .app import App
from .commands import daily, explain, fetch, report, resume, setup, track
from .config import HOME_ENV, resolve_home
from .errors import HirejutsuError

COMMANDS = [setup, resume, fetch, daily, explain, report, track]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hirejutsu",
        description="Daily job picks matched to your resume.",
    )
    parser.add_argument("--version", action="version", version=f"hirejutsu {__version__}")
    parser.add_argument("--home", help=f"data folder (default: ${HOME_ENV} or ~/.hirejutsu)")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logs")
    sub = parser.add_subparsers(dest="command", metavar="command")
    for module in COMMANDS:
        module.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    app = App(resolve_home(args.home))
    try:
        return args.func(app, args)
    except HirejutsuError as exc:
        app.console.print(f"[red]error:[/red] {escape(str(exc))}")
        return 2
    except KeyboardInterrupt:
        return 130
