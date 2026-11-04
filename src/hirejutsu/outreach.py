"""Drafting emails to recruiters about the day's picks. Nothing here sends anything."""

from .companies import ATSES
from .config import Config
from .models import Match

# Company career pages, and Hacker News, where companies post their own jobs. Job boards are
# left out because a board's listing rarely says who at the company to write to.
OUTREACH_DEFAULTS = {"sources": [*ATSES, "hackernews"]}


def load_settings(config: Config) -> dict:
    return config.section("outreach", OUTREACH_DEFAULTS)


def picks_to_write(matches: list[Match], settings: dict) -> list[Match]:
    """The picks from the sources in outreach.sources."""
    return [match for match in matches if match.job.source in settings["sources"]]
