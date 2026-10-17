"""Choosing the day's picks."""

from datetime import datetime, timedelta

from .config import Config
from .models import Job, Match, Profile
from .ranking import RANKING_DEFAULTS, rank
from .sources.base import SEARCH_DEFAULTS
from .store import Store

STALE_AFTER_DAYS = 3


def candidates(store: Store, now: datetime) -> list[Job]:
    """New jobs that are still listed and were not picked on an earlier day."""
    shown = store.picked_job_ids(before=now.date())
    recent = store.find_jobs(statuses=["new"], seen_since=now - timedelta(days=STALE_AFTER_DAYS))
    return [job for job in recent if job.id not in shown]


def ranking_settings(config: Config) -> dict:
    """The ranking section, with the search age limit when ranking does not set its own."""
    settings = config.section("ranking", RANKING_DEFAULTS)
    if settings["max_age_days"] is None:
        settings["max_age_days"] = config.section("search", SEARCH_DEFAULTS)["max_age_days"]
    return settings


def pick_today(store: Store, config: Config, profile: Profile, now: datetime) -> list[Match]:
    matches = rank(candidates(store, now), profile, ranking_settings(config), now)
    store.record_picks(now.date(), matches)
    return matches
