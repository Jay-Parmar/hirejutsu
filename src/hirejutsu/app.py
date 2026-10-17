"""Shared state handed to every command."""

from functools import cached_property
from pathlib import Path

from rich.console import Console

from .config import Config, load_config


class App:
    def __init__(self, home: Path, console: Console | None = None):
        self.home = home
        self.console = console or Console(soft_wrap=True)

    @cached_property
    def config(self) -> Config:
        return load_config(self.home)
