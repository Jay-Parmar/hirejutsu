"""SmartRecruiters job boards."""

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import DetailSource, tags

API = "https://api.smartrecruiters.com/v1/companies"


@register
class SmartRecruiters(DetailSource):
    """The posting list has no descriptions, so each wanted posting is read on its own."""

    name = "smartrecruiters"
    label = "SmartRecruiters career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        # Only recent postings: some companies still list postings that are years old.
        since = self.since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        jobs, offset = [], 0
        while True:
            params = {"limit": 100, "offset": offset, "releasedAfter": since}
            data = self.client.get_json(f"{API}/{board.slug}/postings", params=params)
            items = data.get("content") or []
            jobs += [self.to_job(board, item) for item in items]
            offset += len(items)
            if not items or offset >= data.get("totalFound", 0):
                return jobs

    def job_details(self, board: Company, job: Job) -> Job:
        return self.to_job(board, self.client.get_json(f"{API}/{board.slug}/postings/{job.external_id}"))

    def probe(self, board: Company) -> tuple[int, str]:
        # Unknown companies answer 200 with no postings, so only the count tells a live board.
        data = self.client.get_json(f"{API}/{board.slug}/postings", params={"limit": 1})
        items = data.get("content") or []
        return data.get("totalFound", 0), clean((items[0].get("company") or {}).get("name")) if items else ""

    def to_job(self, board: Company, item: dict) -> Job:
        def label(key):
            return clean((item.get(key) or {}).get("label"))

        location = item.get("location") or {}
        parts = []
        for section in ((item.get("jobAd") or {}).get("sections") or {}).values():
            parts += [clean(section.get("title")), html_to_text(section.get("text"))]
        return Job(
            source=self.name,
            external_id=str(item["id"]),
            title=clean(item.get("name")),
            company=board.name or clean((item.get("company") or {}).get("name")),
            url=item.get("postingUrl") or f"https://jobs.smartrecruiters.com/{board.slug}/{item['id']}",
            location=clean(location.get("fullLocation")),
            remote=location.get("remote"),
            description="\n".join(part for part in parts if part),
            posted_at=parse_date(item.get("releasedDate")),
            employment_type=label("typeOfEmployment"),
            department=label("department") or label("function"),
            tags=tags(label("function"), label("industry")),
        )
