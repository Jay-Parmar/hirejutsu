"""Remotive: a small public feed of remote jobs, shown a day after they are posted."""

from ..models import Job
from ..salary import parse_salary
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

API_URL = "https://remotive.com/api/remote-jobs"


@register
class Remotive(Source):
    name = "remotive"
    label = "Remotive"

    def fetch(self) -> list[Job]:
        # Remotive asks for at most 4 calls a day and its cache ignores every filter,
        # so one plain call per run gets everything.
        jobs = [to_job(item) for item in self.client.get_json(API_URL)["jobs"]]
        return [job for job in jobs if self.query.is_recent(job.posted_at)]


def to_job(item: dict) -> Job:
    return Job(
        source="remotive",
        external_id=str(item["id"]),
        title=clean(item["title"]),
        company=clean(item["company_name"]),
        url=item["url"],
        location=clean(item.get("candidate_required_location")),
        remote=True,
        description=html_to_text(item.get("description")),
        posted_at=parse_date(item.get("publication_date")),
        employment_type=(item.get("job_type") or "").replace("_", "-"),
        department=clean(item.get("category")),
        tags=item.get("tags") or [],
        **parse_salary(item.get("salary") or ""),
    )
