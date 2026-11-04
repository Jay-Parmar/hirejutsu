"""Drafting emails to recruiters about the day's picks. Nothing here sends anything."""

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote, urlencode

from .applicant import Applicant
from .companies import ATSES
from .config import Config
from .contacts import Contact
from .models import Job, Match, Profile
from .report import source_label

# Company career pages, and Hacker News, where companies post their own jobs. Job boards are
# left out because a board's listing rarely says who at the company to write to.
OUTREACH_DEFAULTS = {"sources": [*ATSES, "hackernews"], "pitch": ""}
# The skills reason of a pick, like "Skills: Python, Django (5 of 20)".
SKILLS_REASON = re.compile(r"Skills: (.+) \(\d+ of \d+\)")
ROLE_WORDS = {"role", "roles", "position", "positions"}


@dataclass
class Draft:
    """An email about one pick and the contacts it could go to, surest first."""

    match: Match
    contacts: list[Contact]
    subject: str
    body: str
    signature: str

    @property
    def to(self) -> str:
        """The surest address, or "" when none was found."""
        return self.contacts[0].address if self.contacts else ""


def load_settings(config: Config) -> dict:
    return config.section("outreach", OUTREACH_DEFAULTS)


def picks_to_write(matches: list[Match], settings: dict) -> list[Match]:
    """The picks from the sources in outreach.sources."""
    return [match for match in matches if match.job.source in settings["sources"]]


def draft(match: Match, contacts: list[Contact], profile: Profile, applicant: Applicant, settings: dict) -> Draft:
    job = match.job
    lines = [
        f"I saw the {role(job)} at {job.company} ({job.url}) and wanted to write to you directly.",
        fit_line(match, profile.years),
        settings["pitch"].strip(),
        "Could you pass my profile to the hiring manager, or would you have time for a short call?",
        "Thank you for your time.",
    ]
    body = "\n".join(line for line in lines if line)
    return Draft(match, contacts, f"{role(job)} at {job.company}", body, signature(applicant))


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


def email_text(draft: Draft) -> str:
    return f"Hi {draft.match.job.company} team,\n\n{draft.body}\n\n{draft.signature}"


def mailto(address: str, subject: str, text: str) -> str:
    """A link that opens a new email in your mail app with the address, subject and text filled in."""
    # Mail apps read line breaks in a mailto body as CRLF.
    query = urlencode({"subject": subject, "body": text.replace("\n", "\r\n")}, quote_via=quote)
    return f"mailto:{quote(address, safe='@')}?{query}"


def sent_command(draft: Draft) -> str:
    return f"hirejutsu outreach sent {draft.match.job.id} {draft.to or '<address>'}"


def contact_line(contact: Contact) -> str:
    return f"{contact.address} ({contact.confidence}): {contact.found}"


def markdown(drafts: list[Draft], day: date) -> str:
    lines = [f"# Recruiter emails for {day.isoformat()}", ""]
    for number, draft in enumerate(drafts, start=1):
        job = draft.match.job
        lines += [f"## {number}. {job.title} at {job.company}",
                  f"{job.url} | via {source_label(job.source)} | id {job.id}", "", "Who to write to:"]
        lines += [f"- {contact_line(contact)}" for contact in draft.contacts] or ["- Nobody found."]
        lines += ["", "```", f"Subject: {draft.subject}", "", email_text(draft), "```", ""]
        lines += [f"[Write email]({mailto(draft.to, draft.subject, email_text(draft))})", "",
                  f"After sending it: `{sent_command(draft)}`", ""]
    return "\n".join(lines)
