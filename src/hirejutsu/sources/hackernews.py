"""Hacker News "Ask HN: Who is hiring?": the monthly thread where companies post their own jobs."""

import html
import re

from ..models import Job
from ..salary import parse_salary
from ..text import clean, html_to_text, parse_date
from . import register
from .base import Source

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{}"
COMMENT_URL = "https://news.ycombinator.com/item?id={}"
THREAD_TITLE = "Ask HN: Who is hiring?"

DASHES = re.compile(r"\s+[\N{EM DASH}\N{EN DASH}]\s+")
HREF = re.compile(r'href="([^"]+)"')
LINK = re.compile(r"https?://|www\.", re.I)
ROLE = re.compile(
    r"\b(engineer|developer|programmer|designer|manager|scientist|architect|analyst|researcher|consultant"
    r"|specialist|recruiter|writer|marketer|lead|head|director|founder|founding|cto|vp|swe|sre|mts|staff"
    r"|intern|roles?|positions?)(s|ing)?\b",
    re.I,
)
SALARY = re.compile(
    r"[$\N{EURO SIGN}\N{POUND SIGN}\N{INDIAN RUPEE SIGN}]\s?\d|\d\s?k\b|\b(usd|eur|gbp|cad|aud|chf|inr|pln)\b", re.I
)
JOB_TYPE = re.compile(r"\b(full[- ]?time|part[- ]?time|contract|contractor|freelance|internships?|permanent)\b", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
NOT_REMOTE = re.compile(r"\b(no|not|part|partly|partially)[ -]remote\b", re.I)
ONSITE = re.compile(r"\b(on[- ]?site|in[- ]office|in[- ]person|hybrid)\b", re.I)


@register
class HackerNews(Source):
    name = "hackernews"
    label = "Hacker News: Who is hiring?"
    defaults = {"months": 1}

    def fetch(self) -> list[Job]:
        jobs = []
        for thread in self.threads():
            comments = self.client.get_json(ITEM_URL.format(thread))["children"]
            jobs += [job for job in map(to_job, comments) if job and self.query.is_recent(job.posted_at)]
        return jobs

    def threads(self) -> list[str]:
        """Ids of the newest monthly threads, newest first."""
        months = self.settings["months"]
        params = {
            "query": '"who is hiring"',
            "tags": "story,author_whoishiring",
            "restrictSearchableAttributes": "title",
            "hitsPerPage": months * 2,
        }
        hits = self.client.get_json(SEARCH_URL, params=params)["hits"]
        return [hit["objectID"] for hit in hits if hit["title"].startswith(THREAD_TITLE)][:months]


def to_job(comment: dict) -> Job | None:
    text = comment.get("text") or ""
    first_line = re.split(r"<p>|\n", text, maxsplit=1)[0]
    fields = read_header(html_to_text(first_line))
    if fields is None:
        return None
    link = HREF.search(text)
    return Job(
        source="hackernews",
        external_id=str(comment["id"]),
        url=html.unescape(link[1]) if link else COMMENT_URL.format(comment["id"]),
        description=html_to_text(text),
        posted_at=parse_date(comment.get("created_at")),
        **fields,
    )


def read_header(header: str) -> dict | None:
    """Job fields from a first line like "Acme | Engineer | REMOTE (EU) | $150k", or None for chat."""
    parts = header.split("|") if "|" in header else DASHES.split(header)
    parts = [clean(part) for part in parts if clean(part)]
    if len(parts) < 2:
        return None
    fields = {"company": strip_links(re.sub(r"\([^)]*\)", "", parts[0])), "remote": is_remote(header)}
    title, places = "", []
    for part in parts[1:]:
        if not title and ROLE.search(part):
            title = strip_links(part)
        elif LINK.search(part):
            continue
        elif "salary_min" not in fields and SALARY.search(part):
            fields.update(parse_salary(part))
        elif "employment_type" not in fields and JOB_TYPE.search(part):
            fields["employment_type"] = part
        else:
            places.append(part)
    # Whatever is left is nearly always about where the job is.
    return {**fields, "title": title or "Open roles", "location": "; ".join(places)}


def is_remote(header: str) -> bool | None:
    if REMOTE.search(header) and not NOT_REMOTE.search(header):
        return True
    if ONSITE.search(header) or NOT_REMOTE.search(header):
        return False
    return None


def strip_links(text: str) -> str:
    return clean(re.sub(r"https?://\S+", "", text))
