"""Himalayas: remote jobs with a real search API, 20 per page."""

from ..models import Job
from ..salary import salary_period
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source, url_id

BROWSE_URL = "https://himalayas.app/jobs/api"
SEARCH_URL = "https://himalayas.app/jobs/api/search"


@register
class Himalayas(Source):
    name = "himalayas"
    label = "Himalayas"
    defaults = {"max_pages": 3}

    def fetch(self) -> list[Job]:
        if not self.query.keywords:
            return self.collect(self.browse())
        jobs = []
        for keyword in self.query.keywords:
            jobs += self.collect(self.search(keyword))
        return jobs

    def search(self, keyword: str):
        for page in range(1, self.settings["max_pages"] + 1):
            yield self.client.get_json(SEARCH_URL, params={"q": keyword, "sort": "recent", "page": page})

    def browse(self):
        params = {}
        for _ in range(self.settings["max_pages"]):
            data = self.client.get_json(BROWSE_URL, params=params)
            yield data
            if not data.get("nextCursor"):
                return
            params = {"cursor": data["nextCursor"]}

    def collect(self, pages) -> list[Job]:
        """Jobs from each page, until a page has none that are recent enough."""
        jobs = []
        for data in pages:
            recent = [job for job in map(to_job, data["jobs"]) if self.query.is_recent(job.posted_at)]
            if not recent:
                break
            jobs += recent
        return jobs


def to_job(item: dict) -> Job:
    low, high = item.get("minSalary"), item.get("maxSalary")
    paid = low is not None or high is not None
    parents = item.get("parentCategories") or []
    return Job(
        source="himalayas",
        external_id=url_id(item["guid"]),
        title=clean(item["title"]),
        company=clean(item["companyName"]),
        # The API terms say every apply link must be the applicationLink.
        url=item["applicationLink"],
        location=", ".join(item.get("locationRestrictions") or []) or "Worldwide",
        remote=True,
        description=html_to_text(item.get("description")),
        posted_at=parse_date(item.get("pubDate")),
        salary_min=low,
        salary_max=high,
        salary_currency=(item.get("currency") or "") if paid else "",
        salary_period=salary_period(item.get("salaryPeriod") or "") if paid else "",
        employment_type=clean(item.get("employmentType")),
        department=parents[0] if parents else "",
        tags=[category.replace("-", " ") for category in item.get("categories") or []],
    )
