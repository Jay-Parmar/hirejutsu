"""Remote OK: the newest 100 or so remote jobs in one JSON feed."""

from urllib.parse import urlsplit, urlunsplit

from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

API_URL = "https://remoteok.com/api"


@register
class RemoteOK(Source):
    name = "remoteok"
    label = "Remote OK"

    def fetch(self) -> list[Job]:
        # The first item is a legal notice, not a job.
        jobs = [to_job(item) for item in self.client.get_json(API_URL) if "id" in item]
        return [job for job in jobs if self.query.is_recent(job.posted_at)]


def to_job(item: dict) -> Job:
    low = item.get("salary_min") or None
    high = item.get("salary_max") or None
    top = high or low
    url = urlsplit(item["url"])  # links point at "remoteOK.com"
    return Job(
        source="remoteok",
        external_id=str(item["id"]),
        title=clean(fix_text(item["position"])),
        company=clean(fix_text(item["company"])),
        url=urlunsplit(url._replace(netloc=url.netloc.lower())),
        location=clean(fix_text(item.get("location"))),
        remote=True,
        description=html_to_text(fix_text(item.get("description"))),
        posted_at=parse_date(item.get("date")),
        salary_min=low,
        salary_max=high,
        # The feed has no currency or period. Amounts are US dollars, and small ones are hourly rates.
        salary_currency="USD" if top else "",
        salary_period=("hour" if top < 1000 else "year") if top else "",
        tags=item.get("tags") or [],
    )


def fix_text(value: str | None) -> str:
    """Undo Remote OK's double encoding, where UTF-8 bytes were read as Latin-1."""
    value = value or ""
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
