"""Job sources. Any module in this package that registers a Source is picked up."""

import importlib
import pkgutil

from ..config import Config
from ..errors import HirejutsuError
from ..http import Client
from .base import Query, Source

SOURCES: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    SOURCES[cls.name] = cls
    return cls


def available() -> dict[str, type[Source]]:
    for module in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module.name}")
    return dict(sorted(SOURCES.items()))


def load_sources(config: Config, client: Client, names: list[str] | None = None) -> list[Source]:
    """Enabled sources, or exactly the named ones when names is given."""
    classes = available()
    if names:
        unknown = sorted(set(names) - set(classes))
        if unknown:
            raise HirejutsuError(f"Unknown source: {', '.join(unknown)}. Run 'hirejutsu sources' to list them.")
        return [classes[name](config, client) for name in names]
    loaded = [cls(config, client) for cls in classes.values()]
    return [source for source in loaded if source.settings["enabled"]]
