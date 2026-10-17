"""Teamtailor job boards, read from their RSS feed."""

from xml.etree import ElementTree

from ..companies import Company
from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .ats import AtsSource, tags

NS = {"tt": "https://teamtailor.com/locations"}
# remoteStatus is fully for fully remote jobs. Others, like none or temporary, do not say.
REMOTE = {"fully": True, "hybrid": False, "onsite": False}


@register
class Teamtailor(AtsSource):
    name = "teamtailor"
    label = "Teamtailor career pages"

    def board_jobs(self, board: Company) -> list[Job]:
        feed = ElementTree.fromstring(self.client.get_bytes(f"https://{board.slug}.teamtailor.com/jobs.rss"))
        channel = feed.find("channel")
        company = board.name or clean(channel.findtext("title"))
        return [self.to_job(company, item) for item in channel.iter("item")]

    def to_job(self, company: str, item: ElementTree.Element) -> Job:
        def text(path, within=item):
            return clean(within.findtext(path, namespaces=NS))

        places = []
        for place in item.iterfind("tt:locations/tt:location", NS):
            parts = [text("tt:city", place), text("tt:country", place)]
            places.append(", ".join(part for part in parts if part))
        return Job(
            source=self.name,
            external_id=text("guid"),
            title=text("title"),
            company=company,
            url=text("link"),
            location="; ".join(place for place in places if place),
            remote=REMOTE.get(text("remoteStatus").lower()),
            description=html_to_text(item.findtext("description")),
            posted_at=parse_date(text("pubDate")),
            department=text("tt:department"),
            tags=tags(text("tt:role")),
        )
