"""Finding who to write to about a job."""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .applicant import EMAIL
from .companies import URL_IN_TEXT
from .models import Job

# How sure a contact is: written in the job post, a hiring address on the company's site, or a guess.
STATED, SITE, GUESS = "stated", "site", "guess"
# Addresses in job posts that are there for something other than hiring, like the privacy notice.
NOT_FOR_HIRING = ("noreply", "donotreply", "privacy", "security", "legal", "abuse", "support", "accommodation")
SPELLED_AT = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.IGNORECASE)
SPELLED_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE)
# Applicant tracking systems and job boards list the jobs of many companies, so their sites are
# never the company's own.
SHARED_SITES = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "recruitee.com", "workable.com",
    "myworkdayjobs.com", "myworkdaysite.com", "personio.de", "personio.com", "breezy.hr", "bamboohr.com",
    "teamtailor.com", "remoteok.com", "remotive.com", "weworkremotely.com", "himalayas.app", "jobicy.com",
    "workingnomads.com", "4dayweek.io", "arbeitnow.com", "ycombinator.com", "linkedin.com", "indeed.com",
    "naukri.com", "glassdoor.com", "ziprecruiter.com",
}
# Labels such as the co in acme.co.uk, below which companies register their names.
SECOND_LEVEL = {"ac", "co", "com", "edu", "gov", "net", "org"}
LEGAL_WORDS = {"inc", "llc", "ltd", "limited", "corp", "gmbh", "pvt", "private"}


@dataclass
class Contact:
    address: str
    found: str
    confidence: str


def post_addresses(job: Job) -> list[str]:
    """Addresses written in the job post, also when spelled out like jobs [at] acme [dot] com."""
    text = SPELLED_DOT.sub(".", SPELLED_AT.sub("@", job.description))
    return list(dict.fromkeys(address.lower() for address in EMAIL.findall(text)))


def post_contacts(job: Job) -> list[Contact]:
    return [Contact(address, "job post", STATED) for address in post_addresses(job) if for_hiring(address)]


def for_hiring(address: str) -> bool:
    local = re.sub(r"[^a-z]", "", address.split("@")[0])
    return not any(word in local for word in NOT_FOR_HIRING)


def company_domain(job: Job) -> str:
    """The company's own domain from the job link, the addresses in the post or its links. Empty when unsure."""
    urls = [job.url, *(f"https://{address.split('@')[1]}" for address in post_addresses(job))]
    urls += URL_IN_TEXT.findall(job.description)
    return next((domain for domain in (site_domain(url, job.company) for url in urls) if domain), "")


def site_domain(url: str, company: str) -> str:
    """The domain of url when it is named like the company and is not an ATS or job board."""
    domain = registered_domain(urlparse(url).hostname or "")
    return domain if domain not in SHARED_SITES and named_like(domain, company) else ""


def registered_domain(host: str) -> str:
    """The name a company registers, like acme.co.uk for careers.acme.co.uk."""
    labels = [label for label in host.lower().split(".") if label]
    size = 3 if len(labels) > 2 and labels[-2] in SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-size:]) if len(labels) >= size else ""


def named_like(domain: str, company: str) -> bool:
    """True when one name holds the other, as acme.com does for Acme Inc and acmehq.com for Acme."""
    label = domain.split(".")[0].replace("-", "")
    name = "".join(word for word in re.findall(r"[a-z0-9]+", company.lower()) if word not in LEGAL_WORDS)
    # A name of one or two letters would match far too many sites.
    return len(min(label, name, key=len)) >= 3 and (label in name or name in label)
