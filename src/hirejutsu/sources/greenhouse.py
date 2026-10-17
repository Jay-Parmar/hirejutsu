"""Greenhouse job boards."""

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import DetailSource, remote_from, tags

API = "https://boards-api.greenhouse.io/v1/boards"


@register
class Greenhouse(DetailSource):
    """The board list has no descriptions, so each wanted job is read on its own."""

    name = "greenhouse"
    label = "Greenhouse career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        data = self.client.get_json(f"{API}/{board.slug}/jobs")
        return [self.to_job(board, item) for item in data["jobs"]]

    def job_details(self, board: Company, job: Job) -> Job:
        item = self.client.get_json(f"{API}/{board.slug}/jobs/{job.external_id}", params={"pay_transparency": "true"})
        return self.to_job(board, item)

    def to_job(self, board: Company, item: dict) -> Job:
        location = clean((item.get("location") or {}).get("name"))
        fields = {clean(field.get("name")).lower(): field.get("value") for field in item.get("metadata") or []}
        departments = [clean(department.get("name")) for department in item.get("departments") or []]
        offices = [clean(office.get("name")) for office in item.get("offices") or []]
        job = Job(
            source=self.name,
            external_id=str(item["id"]),
            title=clean(item.get("title")),
            company=board.name or clean(item.get("company_name")),
            url=item.get("absolute_url") or f"https://job-boards.greenhouse.io/{board.slug}/jobs/{item['id']}",
            location=location,
            remote=remote_from(str(fields.get("workplace type") or location)),
            description=html_to_text(item.get("content")),
            posted_at=parse_date(item.get("first_published") or item.get("updated_at")),
            employment_type=clean(str(fields.get("employment type") or "")),
            department=departments[0] if departments else "",
            tags=tags(*departments, *offices),
        )
        ranges = item.get("pay_input_ranges") or []
        if ranges:
            pay = ranges[0]
            job.salary_min = pay["min_cents"] / 100
            job.salary_max = pay["max_cents"] / 100
            job.salary_currency = pay.get("currency_type") or ""
            # Ranges are yearly unless titled otherwise, like "Hourly Rate:".
            job.salary_period = "hour" if "hour" in (pay.get("title") or "").lower() else "year"
        return job
