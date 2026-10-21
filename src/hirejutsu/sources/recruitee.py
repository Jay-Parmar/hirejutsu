"""Recruitee job boards."""

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, pay_period, tags


@register
class Recruitee(AtsSource):
    name = "recruitee"
    label = "Recruitee career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        data = self.client.get_json(f"https://{board.slug}.recruitee.com/api/offers/")
        return [self.to_job(board, item) for item in data["offers"]]

    def to_job(self, board: Company, item: dict) -> Job:
        if item.get("remote"):
            remote = True
        elif item.get("hybrid") or item.get("on_site"):
            remote = False
        else:
            remote = None
        salary = item.get("salary") or {}
        texts = [html_to_text(item.get("description")), html_to_text(item.get("requirements"))]
        return Job(
            source=self.name,
            external_id=str(item["id"]),
            title=clean(item.get("title")),
            company=board.name or clean(item.get("company_name")),
            url=item.get("careers_url") or f"https://{board.slug}.recruitee.com/o/{item['slug']}",
            location=clean(item.get("location")),
            remote=remote,
            description="\n".join(text for text in texts if text),
            posted_at=parse_date((item.get("published_at") or "").removesuffix(" UTC")),
            salary_min=amount(salary.get("min")),
            salary_max=amount(salary.get("max")),
            salary_currency=salary.get("currency") or "",
            salary_period=pay_period(salary.get("period")),
            employment_type=clean(item.get("employment_type_code")),
            department=clean(item.get("department")),
            tags=tags(*(item.get("tags") or []), item.get("category_code"), item.get("experience_code")),
        )


def amount(value) -> float | None:
    """Amounts come as text, and some boards put 1 where they mean no minimum."""
    number = float(value) if value else 0.0
    return number if number > 1 else None
