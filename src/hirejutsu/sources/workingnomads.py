"""Working Nomads: about 50 recent remote jobs in one JSON feed."""

from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source, url_id

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


@register
class WorkingNomads(Source):
    name = "workingnomads"
    label = "Working Nomads"

    def fetch(self) -> list[Job]:
        jobs = [to_job(item) for item in self.client.get_json(API_URL)]
        return [job for job in jobs if self.query.is_recent(job.posted_at)]


def to_job(item: dict) -> Job:
    return Job(
        source="workingnomads",
        external_id=url_id(item["url"]),
        title=clean(item["title"]),
        company=clean(item["company_name"]),
        url=item["url"],
        location=clean(item.get("location")),
        remote=True,
        description=html_to_text(item.get("description")),
        posted_at=parse_date(item.get("pub_date")),
        department=clean(item.get("category_name")),
        tags=[tag.strip() for tag in (item.get("tags") or "").split(",") if tag.strip()],
    )
