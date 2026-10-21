"""Shared state handed to every command."""

from functools import cached_property
from pathlib import Path

from rich.console import Console

from . import http
from .config import Config, load_config
from .store import Store


class App:
    def __init__(self, home: Path, console: Console | None = None):
        self.home = home
        self.console = console or Console(soft_wrap=True)

    @cached_property
    def config(self) -> Config:
        return load_config(self.home)

    @cached_property
    def store(self) -> Store:
        return Store(self.config.db_path)

    @cached_property
    def client(self) -> http.Client:
        return http.Client.from_settings(self.config.section("http", http.DEFAULTS))
