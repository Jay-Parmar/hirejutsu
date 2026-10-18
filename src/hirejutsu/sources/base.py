"""Base class for job sources."""

from dataclasses import dataclass, field

from ..config import Config, deep_merge
from ..http import Client
from ..models import Job

SEARCH_DEFAULTS = {"keywords": [], "max_age_days": 14}


@dataclass
class Query:
    """What to look for on sites that need a search term."""

    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    max_age_days: int = 14

    @classmethod
    def from_config(cls, config: Config) -> "Query":
        search = config.section("search", SEARCH_DEFAULTS)
        profile = config.section("profile")
        return cls(
            keywords=list(search["keywords"] or profile.get("titles") or []),
            locations=list(profile.get("locations") or []),
            max_age_days=int(search["max_age_days"]),
        )

    @property
    def wants_remote(self) -> bool:
        return any(location.strip().lower() == "remote" for location in self.locations)


class Source:
    """A place jobs come from. Subclasses set name and implement fetch()."""

    name = ""
    label = ""
    defaults: dict = {}

    def __init__(self, config: Config, client: Client):
        self.config = config
        self.client = client
        self.query = Query.from_config(config)
        user = config.section("sources").get(self.name)
        if isinstance(user, bool):
            user = {"enabled": user}
        self.settings = deep_merge({"enabled": True, **self.defaults}, user or {})

    def fetch(self) -> list[Job]:
        raise NotImplementedError
