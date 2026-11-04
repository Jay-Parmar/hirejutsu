"""Finding who to write to about a job."""

import html
import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlparse

import requests

from .applicant import EMAIL
from .companies import URL_IN_TEXT
from .models import Job

log = logging.getLogger(__name__)

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
# Pages of the company's site that are read for hiring addresses: the home page, careers, jobs and contact.
SITE_PAGES = ("", "careers", "jobs", "contact")
# The first word of addresses like careers@, jobs@ or talent.team@.
HIRING_WORDS = {
    "careers", "career", "jobs", "job", "talent", "recruiting", "recruitment", "recruiter", "recruiters",
    "hr", "people", "hiring", "join", "joinus", "apply",
}


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


def site_contacts(client, domain: str) -> list[Contact]:
    """Hiring addresses like careers@ on a few pages of the company's site. Pages that fail are skipped."""
    found = {}
    for page in SITE_PAGES:
        url = f"https://{domain}/{page}"
        try:
            text = client.get_text(url)
        except requests.HTTPError as exc:
            log.debug("Skipped %s: %s", url, exc)
            continue
        except requests.RequestException as exc:
            # A site that does not answer for one page will not answer for the others either.
            log.debug("Could not read %s: %s", url, exc)
            break
        for address in hiring_addresses(text, domain):
            found.setdefault(address, Contact(address, url, SITE))
    return list(found.values())


def hiring_addresses(page: str, domain: str) -> list[str]:
    addresses = dict.fromkeys(address.lower() for address in EMAIL.findall(html.unescape(page)))
    return [address for address in addresses if on_domain(address, domain) and is_hiring(address)]


def on_domain(address: str, domain: str) -> bool:
    host = address.split("@")[1]
    return host == domain or host.endswith(f".{domain}")


def is_hiring(address: str) -> bool:
    return re.split(r"[._+-]", address.split("@")[0])[0] in HIRING_WORDS


def search_links(company: str) -> list[tuple[str, str]]:
    """Searches for finding the right person yourself. They are only links, nothing is fetched."""
    web = f'"{company}" recruiter OR "talent acquisition" site:linkedin.com/in'
    return [
        ("Web search", "https://www.google.com/search?" + urlencode({"q": web}, quote_via=quote)),
        ("LinkedIn people search", "https://www.linkedin.com/search/results/people/?"
         + urlencode({"keywords": f"{company} recruiter"}, quote_via=quote)),
    ]


def surest_first(contacts: list[Contact]) -> list[Contact]:
    """Each address once: stated ones first, then the company site's, then guesses."""
    order = (STATED, SITE, GUESS)
    unique = {}
    for contact in sorted(contacts, key=lambda contact: order.index(contact.confidence)):
        unique.setdefault(contact.address, contact)
    return list(unique.values())


class Finder:
    """Finds who to write to about each job, reading each company's site once a run."""

    def __init__(self, client):
        self.client = client
        self.sites: dict[str, list[Contact]] = {}

    def contacts(self, job: Job) -> list[Contact]:
        found = post_contacts(job)
        domain = company_domain(job)
        if domain:
            if domain not in self.sites:
                self.sites[domain] = site_contacts(self.client, domain)
            found += self.sites[domain]
        return surest_first(found)
