"""Lever job boards, on the US host or the EU one."""

import requests

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, pay_period, remote_from, tags

US_API = "https://api.lever.co/v0/postings"
EU_API = "https://api.eu.lever.co/v0/postings"


@register
class Lever(AtsSource):
    name = "lever"
    label = "Lever career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        return [self.to_job(board, item) for item in self.postings(board)]

    def postings(self, board: Company) -> list[dict]:
        try:
            return self.client.get_json(f"{US_API}/{board.slug}", params={"mode": "json"})
        except requests.HTTPError as exc:
            # An account lives on one of the two hosts and the other one answers 404.
            if exc.response.status_code != 404:
                raise
        return self.client.get_json(f"{EU_API}/{board.slug}", params={"mode": "json"})

    def to_job(self, board: Company, item: dict) -> Job:
        categories = item.get("categories") or {}
        places = categories.get("allLocations") or [categories.get("location")]
        salary = item.get("salaryRange") or {}
        parts = [item.get("descriptionPlain")]
        for section in item.get("lists") or []:
            parts += [section.get("text"), html_to_text(section.get("content"))]
        parts.append(item.get("additionalPlain"))
        return Job(
            source=self.name,
            external_id=item["id"],
            title=clean(item.get("text")),
            company=board.name,
            url=item.get("hostedUrl") or f"https://jobs.lever.co/{board.slug}/{item['id']}",
            location="; ".join(clean(place) for place in places if place),
            remote=remote_from(item.get("workplaceType")),
            description="\n".join(part.strip() for part in parts if part and part.strip()),
            posted_at=parse_date(item.get("createdAt")),
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            salary_currency=salary.get("currency") or "",
            salary_period=pay_period(salary.get("interval")),
            employment_type=clean(categories.get("commitment")),
            department=clean(categories.get("department") or categories.get("team")),
            tags=tags(categories.get("team"), categories.get("department"), item.get("workplaceType"), item.get("country")),
        )
