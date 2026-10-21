"""We Work Remotely: one RSS feed per job category."""

import re
import xml.etree.ElementTree as ET

from ..models import Job
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source, url_id

FEED_URL = "https://weworkremotely.com/categories/{}.rss"
# The main feed stops at about 10 jobs per category, so read the category feeds instead.
CATEGORIES = [
    "remote-full-stack-programming-jobs",
    "remote-back-end-programming-jobs",
    "remote-front-end-programming-jobs",
    "remote-programming-jobs",
    "remote-devops-sysadmin-jobs",
    "remote-design-jobs",
    "remote-product-jobs",
    "remote-customer-support-jobs",
    "remote-sales-and-marketing-jobs",
    "remote-management-and-finance-jobs",
    "all-other-remote-jobs",
]
# Countries come with flag emoji, which are pairs of these regional indicator letters.
FLAGS = re.compile("[\U0001F1E6-\U0001F1FF]")


@register
class WeWorkRemotely(Source):
    name = "weworkremotely"
    label = "We Work Remotely"
    defaults = {"categories": CATEGORIES}

    def fetch(self) -> list[Job]:
        jobs = []
        for category in self.settings["categories"]:
            feed = ET.fromstring(self.client.get_text(FEED_URL.format(category)))
            jobs += [to_job(item) for item in feed.iter("item")]
        return [job for job in jobs if self.query.is_recent(job.posted_at)]


def to_job(item: ET.Element) -> Job:
    heading = clean(item.findtext("title"))
    company, found, title = heading.partition(": ")
    if not found:
        company, title = "", heading
    country = clean(FLAGS.sub("", item.findtext("country") or ""))
    return Job(
        source="weworkremotely",
        external_id=url_id(item.findtext("guid")),
        title=title,
        company=company,
        url=item.findtext("link"),
        location=country or clean(item.findtext("region")),
        remote=True,
        description=html_to_text(item.findtext("description")),
        posted_at=parse_date(item.findtext("pubDate")),
        employment_type=clean(item.findtext("type")),
        department=clean(item.findtext("category")),
        tags=split_skills(item.findtext("skills")),
    )


def split_skills(text: str | None) -> list[str]:
    """Skills are written as a sentence: "A", "A and B" or "A, B, and C"."""
    return [skill for skill in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", clean(text)) if skill]
