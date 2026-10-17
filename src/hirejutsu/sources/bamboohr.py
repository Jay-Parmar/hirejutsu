"""BambooHR job boards."""

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import DetailSource

# locationType: 0 is on-site, 1 is remote and 2 is hybrid.
REMOTE = {"0": False, "1": True, "2": False}


@register
class BambooHR(DetailSource):
    """The job list has no descriptions or dates, so each wanted job is read on its own."""

    name = "bamboohr"
    label = "BambooHR career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        data = self.client.get_json(f"https://{board.slug}.bamboohr.com/careers/list")
        return [self.to_job(board, str(item["id"]), item) for item in data["result"]]

    def job_details(self, board: Company, job: Job) -> Job:
        job_id = job.external_id.partition(":")[2]
        data = self.client.get_json(f"https://{board.slug}.bamboohr.com/careers/{job_id}/detail")
        return self.to_job(board, job_id, data["result"]["jobOpening"])

    def to_job(self, board: Company, job_id: str, item: dict) -> Job:
        place = item.get("location") or {}
        if not place.get("city"):
            # Remote openings leave the office empty and name the area they hire in instead.
            place = item.get("atsLocation") or {}
        parts = [place.get("city"), place.get("state") or place.get("province"), place.get("addressCountry") or place.get("country")]
        names = [clean(part) for part in parts if part]
        description = html_to_text(item.get("description"))
        if item.get("compensation"):
            description = f"{description}\nCompensation: {clean(item['compensation'])}".strip()
        return Job(
            source=self.name,
            # Job ids count up from 1 on every board.
            external_id=f"{board.slug}:{job_id}",
            title=clean(item.get("jobOpeningName")),
            company=board.name,
            url=f"https://{board.slug}.bamboohr.com/careers/{job_id}",
            location=", ".join(name for name in names if name.strip(".")),
            remote=True if item.get("isRemote") else REMOTE.get(str(item.get("locationType"))),
            description=description,
            posted_at=parse_date(item.get("datePosted")),
            employment_type=clean(item.get("employmentStatusLabel")),
            department=clean(item.get("departmentLabel")),
        )
