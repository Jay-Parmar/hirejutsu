"""Finding who to write to about a job."""

import re
from dataclasses import dataclass

from .applicant import EMAIL
from .models import Job

# How sure a contact is: written in the job post, a hiring address on the company's site, or a guess.
STATED, SITE, GUESS = "stated", "site", "guess"
# Addresses in job posts that are there for something other than hiring, like the privacy notice.
NOT_FOR_HIRING = ("noreply", "donotreply", "privacy", "security", "legal", "abuse", "support", "accommodation")
SPELLED_AT = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.IGNORECASE)
SPELLED_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE)


@dataclass
class Contact:
    address: str
    found: str
    confidence: str


def post_contacts(job: Job) -> list[Contact]:
    """Addresses written in the job post, also when spelled out like jobs [at] acme [dot] com."""
    text = SPELLED_DOT.sub(".", SPELLED_AT.sub("@", job.description))
    addresses = dict.fromkeys(address.lower() for address in EMAIL.findall(text))
    return [Contact(address, "job post", STATED) for address in addresses if for_hiring(address)]


def for_hiring(address: str) -> bool:
    local = re.sub(r"[^a-z]", "", address.split("@")[0])
    return not any(word in local for word in NOT_FOR_HIRING)
