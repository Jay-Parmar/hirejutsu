"""Breezy HR job boards."""

from ..companies import Company
from ..models import Job
from ..salary import parse_salary
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, remote_from


@register
class Breezy(AtsSource):
    name = "breezy"
    label = "Breezy HR career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        # verbose=true adds the descriptions.
        items = self.client.get_json(f"https://{board.slug}.breezy.hr/json", params={"verbose": "true"})
        return [self.to_job(board, item) for item in items]

    def to_job(self, board: Company, item: dict) -> Job:
        location = item.get("location") or {}
        workplace = (location.get("remote_details") or {}).get("value")
        return Job(
            source=self.name,
            external_id=item["id"],
            title=clean(item.get("name")),
            company=board.name or clean((item.get("company") or {}).get("name")),
            url=item.get("url") or f"https://{board.slug}.breezy.hr/p/{item['friendly_id']}",
            location=clean(location.get("name")),
            # is_remote is set for hybrid jobs too, so the remote details come first.
            remote=remote_from(workplace) if workplace else location.get("is_remote"),
            description=html_to_text(item.get("description")),
            posted_at=parse_date(item.get("published_date")),
            employment_type=clean((item.get("type") or {}).get("name")),
            department=clean(item.get("department")),
            **parse_salary(item.get("salary") or ""),
        )
