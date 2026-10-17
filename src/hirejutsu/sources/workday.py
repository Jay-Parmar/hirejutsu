"""Workday career sites, read through the API their own pages use."""

import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ..companies import Company, workday_url
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import DetailSource, remote_from, tags

PAGE = 20  # the most Workday returns at once
POSTED = re.compile(r"posted (today|yesterday|(\d+)\+? days? ago)", re.I)


def posted_on(text: str | None) -> datetime | None:
    """The rough date in "Posted Today", "Posted Yesterday" or "Posted 3 Days Ago"."""
    found = POSTED.search(text or "")
    if not found:
        return None
    word = found.group(1).lower()
    days = 0 if word == "today" else 1 if word == "yesterday" else int(found.group(2))
    return datetime.now(timezone.utc) - timedelta(days=days)


def remote(remote_type: str | None, location: str) -> bool | None:
    """Each company words remoteType its own way, from Office - Flexible to a plain Yes or No."""
    answer = clean(remote_type).lower()
    if answer in ("yes", "no"):
        return answer == "yes"
    return remote_from(answer or location)


def tenant(board: Company) -> str:
    return board.slug.partition(".")[0]


@register
class Workday(DetailSource):
    """Lists newest jobs first, 20 at a time, and only gives exact dates and descriptions per job."""

    name = "workday"
    label = "Workday career pages"
    defaults = {**DetailSource.defaults, "max_pages": 10}

    def api(self, board: Company) -> str:
        host, _, site = board.slug.partition("/")
        return f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant(board)}/{site}"

    def search(self, board: Company, offset: int, limit: int = PAGE) -> dict:
        payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
        return self.client.post_json(f"{self.api(board)}/jobs", payload)

    def board_jobs(self, board: Company) -> list[Job]:
        jobs, total = [], 0
        for page in range(self.settings["max_pages"]):
            data = self.search(board, page * PAGE)
            # Only the first page carries the total.
            total = total or data.get("total") or 0
            items = data.get("jobPostings") or []
            listed = [self.to_job(board, item) for item in items if item.get("externalPath")]
            jobs += listed
            old = all(job.posted_at and job.posted_at < self.since for job in listed)
            if not items or old or (page + 1) * PAGE >= total:
                break
        return jobs

    def job_details(self, board: Company, job: Job) -> Job:
        path = job.url.removeprefix(workday_url(board.slug))
        info = self.client.get_json(f"{self.api(board)}{path}")["jobPostingInfo"]
        places = [info.get("location")] + (info.get("additionalLocations") or [])
        location = "; ".join(clean(place) for place in places if place) or job.location
        return replace(
            job,
            title=clean(info.get("title")) or job.title,
            url=info.get("externalUrl") or job.url,
            location=location,
            remote=remote(info.get("remoteType"), location),
            description=html_to_text(info.get("jobDescription")),
            posted_at=parse_date(info.get("startDate")) or job.posted_at,
            employment_type=clean(info.get("timeType")),
        )

    def probe(self, board: Company) -> tuple[int, str]:
        # Workday only gives the legal entity, not the company name people know.
        return self.search(board, 0, limit=1).get("total") or 0, ""

    def to_job(self, board: Company, item: dict) -> Job:
        path = item["externalPath"]
        return Job(
            source=self.name,
            # Job ids are only unique within one company.
            external_id=f"{tenant(board)}:{path.rsplit('/', 1)[-1]}",
            title=clean(item.get("title")),
            company=board.name,
            url=workday_url(board.slug) + path,
            location=clean(item.get("locationsText")),
            remote=remote(item.get("remoteType"), clean(item.get("locationsText"))),
            posted_at=posted_on(item.get("postedOn")),
            tags=tags(*item.get("bulletFields") or []),
        )
