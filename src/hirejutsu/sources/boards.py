"""Big job boards searched through python-jobspy.

These sites forbid scraping in their terms, so every board here is off until the user turns it on.
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone

from ..errors import HirejutsuError
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

log = logging.getLogger(__name__)

PERIODS = {"yearly": "year", "monthly": "month", "weekly": "week", "daily": "day", "hourly": "hour"}
# What jobspy logs when a board refuses us for a while: HTTP 429, a captcha or a block page.
BLOCKED = re.compile(r"\b429\b|recaptcha|rate limited|blocked", re.IGNORECASE)


class _Recorder(logging.Handler):
    """Keeps log records instead of printing them."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _scrape(**search) -> list[dict]:
    """Run one jobspy search and return its rows."""
    try:
        from jobspy import scrape_jobs
    except ImportError as exc:
        raise HirejutsuError('python-jobspy is not installed. Run: pip install -e ".[jobspy]"') from exc
    return scrape_jobs(**search).to_dict(orient="records")


def _value(row: dict, key: str):
    """A cell, or None when it is empty."""
    value = row.get(key)
    # pandas fills empty cells with NaN or NaT, which are never equal to themselves.
    return None if value is None or value != value else value


def _text(row: dict, key: str) -> str:
    return clean(_value(row, key))


def _tags(row: dict) -> list[str]:
    """Naukri's skills, which jobspy joins with commas."""
    return [tag for tag in map(clean, _text(row, "skills").split(",")) if tag]


def _is_remote(place: str) -> bool:
    return place.strip().lower() == "remote"


class Board(Source):
    """A job board searched once per keyword and place. Subclasses set site to jobspy's name for it."""

    site = ""
    defaults = {"enabled": False, "results": 25, "max_searches": 3, "delay_seconds": 15, "descriptions": True}

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        errors: list[str] = []
        for number, search in enumerate(self.searches()):
            if number:
                time.sleep(self.settings["delay_seconds"])
            rows, records = self.run(search)
            jobs += [job for job in map(self.to_job, rows) if job]
            errors += [record.getMessage() for record in records if record.levelno >= logging.ERROR]
            if any(BLOCKED.search(record.getMessage()) for record in records):
                break
        errors = list(dict.fromkeys(errors))
        if errors and not jobs:
            raise HirejutsuError("; ".join(errors))
        if errors:
            log.warning("Some %s searches failed: %s", self.name, "; ".join(errors))
        return jobs

    def run(self, search: dict) -> tuple[list[dict], list[logging.LogRecord]]:
        """Run one search and keep what jobspy logs about it. Board failures are logged, not raised."""
        # jobspy 1.3 gives each board a "JobSpy:<Board>" logger whose own handler prints to stderr.
        logger = logging.getLogger(f"JobSpy:{self.label}")
        recorder = _Recorder()
        saved = logger.handlers
        logger.handlers = [recorder]
        try:
            rows = _scrape(**search)
        finally:
            logger.handlers = saved
        for record in recorder.records:
            log.debug("%s: %s", self.name, record.getMessage())
        return rows, recorder.records

    def searches(self) -> list[dict]:
        if not self.query.keywords:
            raise HirejutsuError("No search keywords. Set search.keywords or profile.titles in the config.")
        places = self.places()
        found = [self.search(keyword, place) for keyword in self.query.keywords for place in places]
        return found[: self.settings["max_searches"]]

    def places(self) -> list[str]:
        """Cities and "remote" from the profile. No locations means anywhere."""
        return self.query.locations or [""]

    def search(self, keyword: str, place: str) -> dict:
        remote = _is_remote(place)
        search = {
            "site_name": self.site,
            "search_term": keyword,
            "location": None if remote else place.strip() or None,
            "is_remote": remote,
            "results_wanted": self.settings["results"],
            "hours_old": self.query.max_age_days * 24,
            "fetch_description": self.settings["descriptions"],
            "description_format": "html",
        }
        if "country" in self.settings:
            search["country_indeed"] = self.settings["country"]
        return search

    def to_job(self, row: dict) -> Job | None:
        title, url = _text(row, "title"), _text(row, "job_url")
        if not title or not url:
            return None
        return Job(
            source=self.name,
            external_id=str(row["id"]),
            title=title,
            company=_text(row, "company"),
            url=url,
            location=_text(row, "location"),
            remote=self.remote(row),
            description=html_to_text(_value(row, "description")),
            posted_at=parse_date(_value(row, "date_posted")),
            salary_min=_value(row, "min_amount"),
            salary_max=_value(row, "max_amount"),
            salary_currency=_text(row, "currency"),
            salary_period=PERIODS.get(_value(row, "interval"), ""),
            employment_type=_text(row, "job_type"),
            department=_text(row, "job_function"),
            tags=_tags(row),
        )

    def remote(self, row: dict) -> bool | None:
        # jobspy says False when a job is not flagged as remote, which does not mean on site.
        return True if _value(row, "is_remote") else None


@register
class Indeed(Board):
    name = "indeed"
    label = "Indeed"
    site = "indeed"
    defaults = {**Board.defaults, "results": 50, "country": "India"}


@register
class Naukri(Board):
    name = "naukri"
    label = "Naukri"
    site = "naukri"
    defaults = {**Board.defaults, "results": 20}

    def fetch(self) -> list[Job]:
        # Searches have no age limit (see search), so old jobs are dropped here.
        oldest = (datetime.now(timezone.utc) - timedelta(days=self.query.max_age_days)).date()
        return [job for job in super().fetch() if not job.posted_at or job.posted_at.date() >= oldest]

    def search(self, keyword: str, place: str) -> dict:
        # Naukri only filters on a bare city name, and an age limit makes it sort by date
        # instead of relevance, which buries the jobs that match.
        return {**super().search(keyword, place.split(",")[0]), "hours_old": None}

    def remote(self, row: dict) -> bool | None:
        mode = _value(row, "work_from_home_type")
        return mode == "Remote" if mode else super().remote(row)
