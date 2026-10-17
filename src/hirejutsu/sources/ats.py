"""Shared code for the sources that read company career pages hosted by an ATS."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ..companies import Company, companies_for
from ..errors import HirejutsuError
from ..models import Job
from ..store import Store
from ..text import clean
from .base import Source

log = logging.getLogger(__name__)

# Too common in job titles to tell one job from another.
STOP_WORDS = {"a", "an", "and", "at", "de", "for", "in", "of", "on", "or", "the", "to", "with"}
OLDEST = datetime.min.replace(tzinfo=timezone.utc)
PERIODS = {"year": "year", "annual": "year", "month": "month", "week": "week", "day": "day", "daily": "day",
           "hour": "hour"}


def title_words(keywords: list[str]) -> tuple[str, ...]:
    words = {word for keyword in keywords for word in re.findall(r"\w+", keyword.lower())}
    return tuple(sorted(words - STOP_WORDS))


def likely_match(title: str, words: tuple[str, ...]) -> bool:
    """True when a word of the title starts with a keyword word, so engineer also finds Engineering."""
    return any(word.startswith(words) for word in re.findall(r"\w+", title.lower()))


def remote_from(text: str | None) -> bool | None:
    """True for remote, False for hybrid or on-site, None when the text does not say."""
    text = (text or "").lower()
    if re.search(r"hybrid|on-?site|on_site|office|flex", text):
        return False
    return True if "remote" in text else None


def pay_period(text: str | None) -> str:
    """year, month, week, day or hour from values like per-year-salary, 1 MONTH or yearly."""
    text = (text or "").lower()
    return next((period for word, period in PERIODS.items() if word in text), "")


def tags(*values) -> list[str]:
    """The given values cleaned up, without blanks or repeats."""
    cleaned = (clean(str(value)) for value in values if value)
    return [tag for tag in dict.fromkeys(cleaned) if tag]


class AtsSource(Source):
    """Reads the job board of every company in the registry that uses this ATS."""

    defaults = {"workers": 4, "title_filter": True}

    def __init__(self, config, client):
        super().__init__(config, client)
        self.since = datetime.now(timezone.utc) - timedelta(days=self.query.max_age_days)
        self.words = title_words(self.query.keywords) if self.settings["title_filter"] else ()

    def boards(self) -> list[Company]:
        return companies_for(self.config, self.name)

    def board_jobs(self, board: Company) -> list[Job]:
        """Every job listed on one board."""
        raise NotImplementedError

    def probe(self, board: Company) -> tuple[int, str]:
        """How many jobs a board lists and the company name it gives, to tell whether it is live."""
        jobs = self.board_jobs(board)
        return len(jobs), jobs[0].company if jobs else ""

    def fetch(self) -> list[Job]:
        return [job for _, job in self.listed()]

    def listed(self) -> list[tuple[Company, Job]]:
        """The wanted jobs of every board. Failed boards are logged and skipped, unless all of them fail."""
        boards = self.boards()
        listed, failed = [], []
        for board, result in zip(boards, self.parallel(self.board_jobs, boards)):
            if isinstance(result, Exception):
                failed.append((board, result))
            else:
                listed += [(board, job) for job in result if self.wanted(job)]
        if failed and len(failed) == len(boards):
            board, exc = failed[0]
            raise HirejutsuError(f"all {len(boards)} boards failed, {board.slug}: {exc}")
        for board, exc in failed:
            log.warning("%s board %s failed: %s", self.name, board.slug, exc)
        if failed:
            self.warn(f"{len(failed)} of {len(boards)} boards failed")
        return listed

    def wanted(self, job: Job) -> bool:
        """Posted within max_age_days and, with the title filter on, titled like the keywords."""
        if job.posted_at and job.posted_at < self.since:
            return False
        return not self.words or likely_match(job.title, self.words)

    def parallel(self, fn, items: list) -> list:
        """fn(item) for every item on the source's workers. A failure comes back as its exception."""

        def call(item):
            try:
                return fn(item)
            except Exception as exc:
                return exc

        with ThreadPoolExecutor(max_workers=self.settings["workers"]) as pool:
            return list(pool.map(call, items))

    def warn(self, text: str) -> None:
        self.warning = f"{self.warning}, {text}" if self.warning else text


class DetailSource(AtsSource):
    """An ATS whose job list is light, so every job worth keeping takes one more call for its posting."""

    defaults = {**AtsSource.defaults, "max_details": 300}

    def job_details(self, board: Company, job: Job) -> Job:
        """The listed job completed from its own posting."""
        raise NotImplementedError

    def fetch(self) -> list[Job]:
        listed = self.listed()
        known = self.known_jobs()
        jobs = [known[job.external_id] for _, job in listed if job.external_id in known]
        todo = [(board, job) for board, job in listed if job.external_id not in known]
        todo.sort(key=lambda pair: pair[1].posted_at or OLDEST, reverse=True)
        limit = self.settings["max_details"]
        results = self.parallel(lambda pair: self.job_details(*pair), todo[:limit])
        failed = 0
        for (_, job), result in zip(todo, results):
            if isinstance(result, Exception):
                log.warning("%s job %s failed: %s", self.name, job.url, result)
                failed += 1
                result = job
            jobs.append(result)
        if failed:
            self.warn(f"{failed} of {len(results)} job pages failed")
        if len(todo) > limit:
            log.info("%s: %d jobs wait for their details until the next fetch", self.name, len(todo) - limit)
        return jobs + [job for _, job in todo[limit:]]

    def known_jobs(self) -> dict[str, Job]:
        """Jobs saved with their details by an earlier fetch, whose postings need no new call."""
        with Store(self.config.db_path) as store:
            saved = store.find_jobs(seen_since=self.since)
        return {job.external_id: job for job in saved if job.source == self.name and job.description}
