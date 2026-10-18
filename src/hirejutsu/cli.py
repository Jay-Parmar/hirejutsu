"""Command line interface."""

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hirejutsu",
        description="Daily job picks matched to your resume.",
    )
    parser.add_argument("--version", action="version", version=f"hirejutsu {__version__}")
    parser.add_subparsers(dest="command", metavar="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)
