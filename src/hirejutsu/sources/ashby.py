"""Ashby job boards."""

from urllib.parse import quote

from ..companies import Company
from ..models import Job
from ..text import clean, parse_date
from . import register
from .ats import AtsSource, pay_period, remote_from, tags

API = "https://api.ashbyhq.com/posting-api/job-board"


@register
class Ashby(AtsSource):
    name = "ashby"
    label = "Ashby career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        data = self.client.get_json(f"{API}/{quote(board.slug)}", params={"includeCompensation": "true"})
        return [self.to_job(board, item) for item in data["jobs"] if item.get("isListed", True)]

    def to_job(self, board: Company, item: dict) -> Job:
        places = [item.get("location")] + [place.get("location") for place in item.get("secondaryLocations") or []]
        parts = (item.get("compensation") or {}).get("summaryComponents") or []
        salary = next((part for part in parts if part.get("compensationType") == "Salary"), {})
        return Job(
            source=self.name,
            external_id=item["id"],
            title=clean(item.get("title")),
            company=board.name,
            url=item.get("jobUrl") or f"https://jobs.ashbyhq.com/{quote(board.slug)}/{item['id']}",
            location="; ".join(clean(place) for place in places if place),
            # isRemote is true for hybrid jobs too, so only the workplace type says remote.
            remote=remote_from(item.get("workplaceType")),
            description=(item.get("descriptionPlain") or "").strip(),
            posted_at=parse_date(item.get("publishedAt")),
            salary_min=salary.get("minValue"),
            salary_max=salary.get("maxValue"),
            salary_currency=salary.get("currencyCode") or "",
            salary_period=pay_period(salary.get("interval")),
            employment_type=clean(item.get("employmentType")),
            department=clean(item.get("department")),
            tags=tags(item.get("department"), item.get("team"), item.get("workplaceType")),
        )
