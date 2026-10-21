"""Jobicy: remote jobs from the last 7 days, 200 per page."""

import html

from ..models import Job
from ..salary import salary_period
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

API_URL = "https://jobicy.com/api/v2/remote-jobs"
PAGE_SIZE = 200


@register
class Jobicy(Source):
    name = "jobicy"
    label = "Jobicy"
    # Five pages hold the whole 7 day feed.
    defaults = {"max_pages": 5}

    def fetch(self) -> list[Job]:
        jobs = []
        params = {"count": PAGE_SIZE}
        for _ in range(self.settings["max_pages"]):
            data = self.client.get_json(API_URL, params=params)
            recent = [job for job in map(to_job, data["jobs"]) if self.query.is_recent(job.posted_at)]
            jobs += recent
            if not recent or not data.get("hasMore"):
                break
            params = {"count": PAGE_SIZE, "cursor": data["nextCursor"]}
        return jobs


def to_job(item: dict) -> Job:
    industries = item.get("jobIndustry") or []
    return Job(
        source="jobicy",
        external_id=str(item["id"]),
        title=clean(item["jobTitle"]),
        company=clean(html.unescape(item["companyName"])),
        url=item["url"],
        location=clean(item.get("jobGeo")),
        remote=True,
        description=html_to_text(item.get("jobDescription")),
        posted_at=parse_date(item.get("pubDate")),
        salary_min=item.get("salaryMin"),
        salary_max=item.get("salaryMax"),
        salary_currency=item.get("salaryCurrency") or "",
        salary_period=salary_period(item.get("salaryPeriod") or ""),
        employment_type=", ".join(item.get("jobType") or []),
        department=industries[0] if industries else "",
        tags=industries,
    )
