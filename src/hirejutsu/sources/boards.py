"""Big job boards searched through python-jobspy.

These sites forbid scraping in their terms, so every board here is off until the user turns it on.
"""

import time

from ..errors import HirejutsuError
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

PERIODS = {"yearly": "year", "monthly": "month", "weekly": "week", "daily": "day", "hourly": "hour"}


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


def _is_remote(place: str) -> bool:
    return place.strip().lower() == "remote"


class Board(Source):
    """A job board searched once per keyword and place. Subclasses set site to jobspy's name for it."""

    site = ""
    defaults = {"enabled": False, "results": 25, "max_searches": 3, "delay_seconds": 15, "descriptions": True}

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for number, search in enumerate(self.searches()):
            if number:
                time.sleep(self.settings["delay_seconds"])
            jobs += [job for job in map(self.to_job, _scrape(**search)) if job]
        return jobs

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
