"""Fetching jobs from all sources into the store."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import Job
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    source: str
    jobs: list[Job] = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""
    added: int = 0
    warning: str = ""

    @property
    def found(self) -> int:
        return len(self.jobs)


def fetch_all(sources: list, store: Store, workers: int = 8, now: datetime | None = None) -> list[FetchResult]:
    """Fetch every source in parallel and save what they return."""
    now = now or datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(_fetch_one, sources))
    for result in results:
        result.added = store.upsert_jobs(result.jobs, now)
        store.log_fetch(result.source, now, result.seconds, result.found, result.added, result.error or result.warning)
    return results


def _fetch_one(source) -> FetchResult:
    started = time.monotonic()
    try:
        jobs = _usable(source.fetch())
        error = ""
    except Exception as exc:
        log.warning("%s failed: %s", source.name, exc, exc_info=log.isEnabledFor(logging.DEBUG))
        jobs, error = [], f"{type(exc).__name__}: {exc}"
    return FetchResult(source.name, jobs, round(time.monotonic() - started, 2), error, warning=source.warning)


def _usable(jobs: list[Job]) -> list[Job]:
    """Drop jobs without a title or link and keep the last copy of duplicates."""
    unique = {job.key: job for job in jobs if job.title.strip() and job.url.strip()}
    return list(unique.values())
