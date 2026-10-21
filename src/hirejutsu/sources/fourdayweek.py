"""4dayweek.io: jobs with a 4 day week or other good working hours, remote and onsite."""

import re

from ..models import Job
from ..text import clean, parse_date
from . import register
from .base import Source

API_URL = "https://4dayweek.io/api/v2/jobs"
PAGE_SIZE = 100


@register
class FourDayWeek(Source):
    name = "fourdayweek"
    label = "4 Day Week"
    defaults = {"max_pages": 3}

    def fetch(self) -> list[Job]:
        params = {"sort": "date", "limit": PAGE_SIZE, "posted_after": min(self.query.max_age_days, 365)}
        # Most jobs on this board are onsite or hybrid.
        if self.query.wants_remote:
            params["work_arrangement"] = "remote"
        jobs = []
        for page in range(1, self.settings["max_pages"] + 1):
            data = self.client.get_json(API_URL, params={**params, "page": page})
            jobs += [to_job(item) for item in data["data"]]
            if not data.get("has_more"):
                break
        return jobs


def to_job(item: dict) -> Job:
    # Salaries are in cents or pence, so 8000000 means 80,000.
    low, high = item.get("salary_min"), item.get("salary_max")
    schedule = (item.get("schedule_type") or "").replace("_", " ")
    skills = [tag["name"] for key in ("skills", "stack", "tools") for tag in item.get(key) or []]
    return Job(
        source="fourdayweek",
        external_id=item["id"],
        title=clean(item["title"]),
        company=clean((item.get("company") or {}).get("name")),
        url=item["url"],
        location="; ".join(filter(None, map(place, item.get("locations") or []))),
        remote=item.get("work_arrangement") == "remote",
        description=plain_text(item.get("description") or ""),
        posted_at=parse_date(item.get("posted_at")),
        salary_min=None if low is None else low / 100,
        salary_max=None if high is None else high / 100,
        salary_currency=item.get("salary_currency") or "",
        salary_period=item.get("salary_period") or "",
        employment_type=item.get("contract_type") or "",
        department=item.get("category") or "",
        tags=([schedule] if schedule else []) + skills,
    )


def place(location: dict) -> str:
    parts = [location.get("city"), location.get("state"), location.get("country")]
    return ", ".join(part for part in parts if part) or location.get("continent") or ""


def plain_text(markdown: str) -> str:
    """Descriptions are Markdown. Drop the heading and bold marks and the blank lines."""
    text = re.sub(r"^#+\s*|\*\*|__", "", markdown, flags=re.M)
    return "\n".join(line for line in map(clean, text.splitlines()) if line)
