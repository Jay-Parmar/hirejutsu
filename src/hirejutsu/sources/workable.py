"""Workable job boards."""

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, tags

API = "https://apply.workable.com/api/v1/widget/accounts"


@register
class Workable(AtsSource):
    name = "workable"
    label = "Workable career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        # The widget API lists every job. The careers page API leaves some out.
        data = self.client.get_json(f"{API}/{board.slug}", params={"details": "true"})
        company = board.name or clean(data.get("name"))
        return [self.to_job(board, company, item) for item in data["jobs"]]

    def to_job(self, board: Company, company: str, item: dict) -> Job:
        place = [item.get("city"), item.get("state"), item.get("country")]
        return Job(
            source=self.name,
            external_id=item["shortcode"],
            title=clean(item.get("title")),
            company=company,
            url=f"https://apply.workable.com/{board.slug}/j/{item['shortcode']}/",
            location=", ".join(clean(part) for part in place if part),
            remote=item.get("telecommuting"),
            description=html_to_text(item.get("description")),
            posted_at=parse_date(item.get("published_on") or item.get("created_at")),
            employment_type=clean(item.get("employment_type")),
            department=clean(item.get("department")),
            tags=tags(item.get("function"), item.get("industry"), item.get("experience"), item.get("education")),
        )
