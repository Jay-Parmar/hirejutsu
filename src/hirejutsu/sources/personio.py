"""Personio job boards, read from their XML feed."""

from xml.etree import ElementTree

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, pay_period, tags


@register
class Personio(AtsSource):
    name = "personio"
    label = "Personio career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        # The feed is UTF-8 without saying so in its headers, so it is parsed from the raw bytes.
        root = ElementTree.fromstring(self.client.get_bytes(f"https://{board.slug}.jobs.personio.de/xml"))
        return [self.to_job(board, position) for position in root.iter("position")]

    def to_job(self, board: Company, position: ElementTree.Element) -> Job:
        def text(path):
            return clean(position.findtext(path))

        parts = []
        for section in position.iter("jobDescription"):
            parts += [clean(section.findtext("name")), html_to_text(section.findtext("value"))]
        offices = [text("office")] + [clean(office.text) for office in position.iterfind("additionalOffices/office")]
        return Job(
            source=self.name,
            external_id=text("id"),
            title=text("name"),
            company=board.name or text("subcompany"),
            url=f"https://{board.slug}.jobs.personio.de/job/{text('id')}",
            location="; ".join(office for office in offices if office),
            remote=True if "remote" in text("office").lower() else None,
            description="\n".join(part for part in parts if part),
            posted_at=parse_date(text("createdAt")),
            salary_min=amount(text("salaryInformation/min")),
            salary_max=amount(text("salaryInformation/max")),
            salary_currency=text("salaryInformation/currencyCode"),
            salary_period=pay_period(text("salaryInformation/type")),
            employment_type=", ".join(part for part in (text("employmentType"), text("schedule")) if part),
            department=text("department"),
            tags=tags(text("recruitingCategory"), text("seniority"), *text("keywords").split(",")),
        )


def amount(value: str) -> float | None:
    return float(value) if value else None
