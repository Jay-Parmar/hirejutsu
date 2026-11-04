"""Drafting emails to recruiters about the day's picks. Nothing here sends anything."""

import os
import re
from dataclasses import dataclass
from datetime import date
from html import escape
from importlib import resources
from pathlib import Path
from string import Template
from urllib.parse import quote, urlencode

from .applicant import Applicant
from .companies import ATSES
from .config import Config
from .contacts import Contact, Person, search_links
from .errors import HirejutsuError
from .models import Job, Match, Profile
from .report import source_label, web_link
from .store import Store

OUTREACH_DEFAULTS = {
    # Company career pages, and Hacker News, where companies post their own jobs. Job boards are
    # left out because a board's listing rarely says who at the company to write to.
    "sources": [*ATSES, "hackernews"],
    "pitch": "",
    "search": "",
    "search_key_env": "TAVILY_API_KEY",
    "ai": False,
}
SEARCH_APIS = ("tavily",)
# The skills reason of a pick, like "Skills: Python, Django (5 of 20)".
SKILLS_REASON = re.compile(r"Skills: (.+) \(\d+ of \d+\)")
ROLE_WORDS = {"role", "roles", "position", "positions"}
# How the note that you emailed someone about a job starts.
EMAILED = "Emailed "


@dataclass
class Draft:
    """An email about one pick, the contacts it could go to, surest first, and recruiters found by search."""

    match: Match
    contacts: list[Contact]
    people: list[Person]
    subject: str
    body: str
    signature: str

    @property
    def best(self) -> Contact | None:
        return self.contacts[0] if self.contacts else None

    @property
    def to(self) -> str:
        """The surest address, or "" when none was found."""
        return self.best.address if self.best else ""


def load_settings(config: Config) -> dict:
    settings = config.section("outreach", OUTREACH_DEFAULTS)
    if settings["search"] and settings["search"] not in SEARCH_APIS:
        raise HirejutsuError(f"Unknown outreach.search '{settings['search']}'. Use tavily, or leave it empty.")
    return settings


def search_key(settings: dict) -> str:
    """The search API key from the environment variable in search_key_env. Empty when search is off."""
    return os.environ.get(settings["search_key_env"] or "", "") if settings["search"] else ""


def picks_to_write(matches: list[Match], settings: dict) -> list[Match]:
    """The picks from the sources in outreach.sources."""
    return [match for match in matches if match.job.source in settings["sources"]]


def draft(match: Match, contacts: list[Contact], people: list[Person], profile: Profile, applicant: Applicant,
          settings: dict) -> Draft:
    job = match.job
    lines = [
        f"I saw the {role(job)} at {job.company} ({job.url}) and wanted to write to you directly.",
        fit_line(match, profile.years),
        settings["pitch"].strip(),
        "Could you pass my profile to the hiring manager, or would you have time for a short call?",
        "Thank you for your time.",
    ]
    body = "\n".join(line for line in lines if line)
    return Draft(match, contacts, people, f"{role(job)} at {job.company}", body, signature(applicant))


def role(job: Job) -> str:
    """The job title as a role, like "Backend Engineer role", leaving titles like "Open roles" as they are."""
    words = job.title.split()
    return job.title if words and words[-1].lower() in ROLE_WORDS else f"{job.title} role"


def fit_line(match: Match, years: float | None) -> str:
    """Your years and up to three skills the job and your resume share, as far as they are known."""
    skills = shared_skills(match)
    if years:
        experience = f"{years:g} year" if years == 1 else f"{years:g} years"
        if skills:
            return f"I have {experience} of experience, much of it with {and_list(skills)}, which the role asks for."
        return f"I have {experience} of experience and would like to bring it to {match.job.company}."
    return f"I work with {and_list(skills)}, which the role asks for." if skills else ""


def shared_skills(match: Match) -> list[str]:
    for reason in match.reasons:
        found = SKILLS_REASON.fullmatch(reason)
        if found:
            return found.group(1).split(", ")[:3]
    return []


def and_list(items: list[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def signature(applicant: Applicant) -> str:
    phone = " ".join(part for part in (applicant.phone_code, applicant.phone) if part) if applicant.phone else ""
    lines = ["Best regards,", applicant.name, phone, *applicant.links.values()]
    return "\n".join(line for line in lines if line)


def email_text(draft: Draft, contact: Contact | None = None) -> str:
    """The whole email to the surest contact, or the one given, greeting a known person by first name."""
    contact = contact or draft.best
    first = contact.name.split()[0] if contact and contact.name else ""
    greeting = f"Hi {first}," if first else f"Hi {draft.match.job.company} team,"
    return f"{greeting}\n\n{draft.body}\n\n{draft.signature}"


def mailto(address: str, subject: str, text: str) -> str:
    """A link that opens a new email in your mail app with the address, subject and text filled in."""
    # Mail apps read line breaks in a mailto body as CRLF.
    query = urlencode({"subject": subject, "body": text.replace("\n", "\r\n")}, quote_via=quote)
    return f"mailto:{quote(address, safe='@')}?{query}"


def sent_note(addresses: list[str]) -> str:
    return EMAILED + ", ".join(addresses)


def emailed(store: Store, job_id: int) -> bool:
    """True once a note says you emailed someone about the job."""
    return any(note.startswith(EMAILED) for _, _, note in store.history(job_id))


def sent_command(draft: Draft) -> str:
    return f"hirejutsu outreach sent {draft.match.job.id} {draft.to or '<address>'}"


def contact_groups(contacts: list[Contact]) -> list[list[Contact]]:
    """Contacts found in the same place and just as sure, together, like the guesses for one person."""
    groups: dict[tuple[str, str], list[Contact]] = {}
    for contact in contacts:
        groups.setdefault((contact.confidence, contact.found), []).append(contact)
    return list(groups.values())


def contact_line(group: list[Contact]) -> str:
    return f"{', '.join(contact.address for contact in group)} ({group[0].confidence}): {group[0].found}"


def markdown(drafts: list[Draft], day: date) -> str:
    lines = [f"# Recruiter emails for {day.isoformat()}", ""]
    for number, draft in enumerate(drafts, start=1):
        job = draft.match.job
        lines += [f"## {number}. {job.title} at {job.company}",
                  f"{job.url} | via {source_label(job.source)} | id {job.id}", "", "Who to write to:"]
        lines += [f"- {contact_line(group)}" for group in contact_groups(draft.contacts)] or ["- Nobody found."]
        if draft.people:
            found = " | ".join(f"[{person.name}, {person.role}]({person.link})" for person in draft.people)
            lines += ["", f"Recruiters found: {found}"]
        searches = " | ".join(f"[{label}]({url})" for label, url in search_links(job.company))
        lines += ["", f"Find someone yourself: {searches}"]
        lines += ["", "```", f"Subject: {draft.subject}", "", email_text(draft), "```", ""]
        lines += [f"[Write email]({mailto(draft.to, draft.subject, email_text(draft))})", "",
                  f"After sending it: `{sent_command(draft)}`", ""]
    return "\n".join(lines)


def save_drafts(drafts: list[Draft], config: Config, day: date) -> list[Path]:
    """Write the drafts to outreach-YYYY-MM-DD.md and .html in the reports folder. Returns the files."""
    folder = config.reports_dir
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix, render in (("md", markdown), ("html", html_page)):
        path = folder / f"outreach-{day.isoformat()}.{suffix}"
        path.write_text(render(drafts, day), encoding="utf-8")
        paths.append(path)
    return paths


def html_page(drafts: list[Draft], day: date) -> str:
    """The drafts as one HTML file that loads nothing from the internet."""
    page = Template(resources.files("hirejutsu").joinpath("data", "outreach.html").read_text(encoding="utf-8"))
    count = len(drafts)
    return page.substitute(
        title=f"Recruiter emails for {day.isoformat()}",
        heading=f"Recruiter emails for {day:%A}, {day.day} {day:%B %Y}",
        count=f"{count} job to write about" if count == 1 else f"{count} jobs to write about",
        jobs="\n".join(_job_html(number, draft) for number, draft in enumerate(drafts, start=1)),
    )


def _job_html(number: int, draft: Draft) -> str:
    job = draft.match.job
    link = escape(web_link(job.url))
    text = email_text(draft)
    contacts = "".join(_contacts_html(group, draft) for group in contact_groups(draft.contacts))
    command = escape(sent_command(draft))
    searches = " ".join(f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'
                        for label, url in search_links(job.company))
    return f"""<li class="job">
<div class="rank">{number}</div>
<div>
<h2><a href="{link}" target="_blank" rel="noopener noreferrer">{escape(job.title)}</a></h2>
<p class="company">{escape(job.company)}</p>
<p class="facts"><span>via {escape(source_label(job.source))}</span><span>id {job.id}</span></p>
<h3>Who to write to</h3>
<ul class="contacts">{contacts or "<li>Nobody found.</li>"}</ul>
{_people_html(draft.people)}<p class="find">Find someone yourself: {searches}</p>
<h3>Draft</h3>
<pre class="draft">Subject: {escape(draft.subject)}

{escape(text)}</pre>
<p class="actions"><a class="open" href="{escape(mailto(draft.to, draft.subject, text))}">Write email</a>
<span class="command"><code>{command}</code><button type="button" data-command="{command}">Copy</button></span></p>
</div>
</li>"""


def _people_html(people: list[Person]) -> str:
    """The recruiters found by search, each linked to their profile. Empty when there are none."""
    if not people:
        return ""
    found = "; ".join(
        f'<a href="{escape(web_link(person.link))}" target="_blank" rel="noopener noreferrer">{escape(person.name)}</a>,'
        f" {escape(person.role)}"
        for person in people
    )
    return f'<p class="find">Recruiters found: {found}</p>\n'


def _contacts_html(group: list[Contact], draft: Draft) -> str:
    """One line of contacts, each address a link that opens the draft written to it."""
    links = ", ".join(
        f'<a href="{escape(mailto(contact.address, draft.subject, email_text(draft, contact)))}">'
        f"{escape(contact.address)}</a>"
        for contact in group
    )
    return (f'<li>{links} <span class="sure">{escape(group[0].confidence)}</span>'
            f' <span class="found">{escape(group[0].found)}</span></li>')
