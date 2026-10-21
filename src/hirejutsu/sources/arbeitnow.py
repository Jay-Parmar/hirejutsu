"""Arbeitnow: jobs in Germany and the rest of Europe, about 300 per page."""

import html

from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

API_URL = "https://www.arbeitnow.com/api/job-board-api"


@register
class Arbeitnow(Source):
    name = "arbeitnow"
    label = "Arbeitnow"
    # Off by default: about 9 in 10 jobs are onsite, many of them in German.
    defaults = {"enabled": False, "max_pages": 3}

    def fetch(self) -> list[Job]:
        jobs = []
        for page in range(1, self.settings["max_pages"] + 1):
            data = self.client.get_json(API_URL, params={"page": page})
            # Each page joins several country sites that are sorted on their own,
            # so only a page with no recent job at all means the rest are older.
            recent = [job for job in map(to_job, data["data"]) if self.query.is_recent(job.posted_at)]
            jobs += recent
            if not recent or not data["links"].get("next"):
                break
        return jobs


def to_job(item: dict) -> Job:
    location = clean(item.get("location"))
    return Job(
        source="arbeitnow",
        external_id=item["slug"],
        title=clean(item["title"]),
        company=clean(item["company_name"]),
        url=item["url"],
        location=location,
        remote=bool(item.get("remote")) or location.lower() == "remote",
        description=description(item.get("description") or ""),
        posted_at=parse_date(item.get("created_at")),
        employment_type=", ".join(item.get("job_types") or []),
        tags=item.get("tags") or [],
    )


def description(value: str) -> str:
    # About a fifth of the descriptions are escaped twice and then get a plain HTML footer.
    if "&lt;" in value:
        value = html.unescape(value)
    return html_to_text(value)
