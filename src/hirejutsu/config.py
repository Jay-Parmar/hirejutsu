"""Config file loading and data folder layout."""

import os
from importlib import resources
from pathlib import Path

import yaml

from .errors import ConfigError

HOME_ENV = "HIREJUTSU_HOME"
CONFIG_NAME = "config.yaml"


def resolve_home(value: str | None = None) -> Path:
    """Return the data folder from the flag, the env var or the default."""
    raw = value or os.environ.get(HOME_ENV) or "~/.hirejutsu"
    return Path(os.path.expandvars(raw)).expanduser().resolve()


def deep_merge(base: dict, override: dict) -> dict:
    """Return a copy of base updated with override, merging nested dicts."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Config:
    def __init__(self, data: dict, home: Path):
        self.data = data
        self.home = home

    def get(self, key: str, default=None):
        value = self.data.get(key)
        return default if value is None else value

    def section(self, name: str, defaults: dict | None = None) -> dict:
        """Return a config section merged over its defaults."""
        value = self.data.get(name) or {}
        if not isinstance(value, dict):
            raise ConfigError(f"'{name}' in {CONFIG_NAME} must be a mapping")
        return deep_merge(defaults or {}, value)

    def path(self, value: str) -> Path:
        """Expand ~ and env vars. Relative paths are relative to the data folder."""
        path = Path(os.path.expandvars(str(value))).expanduser()
        return path if path.is_absolute() else self.home / path

    @property
    def db_path(self) -> Path:
        return self.home / "hirejutsu.db"

    @property
    def reports_dir(self) -> Path:
        return self.path(self.get("reports_dir", "reports"))

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"


def load_config(home: Path) -> Config:
    path = home / CONFIG_NAME
    if not path.exists():
        return Config({}, home)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return Config(data, home)


def template() -> str:
    return resources.files("hirejutsu").joinpath("data", CONFIG_NAME).read_text(encoding="utf-8")


def init_home(home: Path, force: bool = False) -> list[Path]:
    """Create the data folder with a starter config. Returns the files written."""
    home.mkdir(parents=True, exist_ok=True)
    for name in ("reports", "logs"):
        (home / name).mkdir(exist_ok=True)
    config_path = home / CONFIG_NAME
    if config_path.exists() and not force:
        return []
    config_path.write_text(template(), encoding="utf-8")
    return [config_path]
