"""Finding who to write to about a job."""

import html
import logging
import re
import unicodedata
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
RECRUITING = re.compile(r"\b(recruit\w*|talent|sourcer|sourcing|hiring|hr|people partner)\b", re.IGNORECASE)
PROFILE = re.compile(r"linkedin\.com/in/([^/?#]+)", re.IGNORECASE)
NAME_WORD = re.compile(r"[^\W\d_]+(?:[.'-][^\W\d_]*)*")


@dataclass
class Contact:
    address: str
    found: str
    confidence: str
    # The person behind the address, when it is known.
    name: str = ""


@dataclass
class Person:
    """Someone found by a web search, with the role their profile gives."""

    name: str
    role: str
    link: str


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
    name = company_words(company).replace(" ", "")
    # A name of one or two letters would match far too many sites.
    return len(min(label, name, key=len)) >= 3 and (label in name or name in label)


def company_words(company: str) -> str:
    """The company name in lower case without words like Inc or Ltd."""
    return " ".join(word for word in re.findall(r"[a-z0-9]+", company.lower()) if word not in LEGAL_WORDS)


def people_in(results: list[dict], company: str) -> list[Person]:
    """Recruiters at the company in LinkedIn results titled like "Jane Doe - Recruiter - Acme | LinkedIn"."""
    people = {}
    for result in results:
        url = result.get("url") or ""
        profile = PROFILE.search(url)
        person = person_in(result.get("title") or "", company, url) if profile else None
        if person:
            people.setdefault(profile.group(1).lower(), person)
    return list(people.values())


def person_in(title: str, company: str, link: str) -> Person | None:
    parts = re.split(r"\s+[-|]\s+", re.sub(r"\s*\|\s*LinkedIn\s*$", "", title, flags=re.IGNORECASE))
    # Credentials come after a comma, as in "Jane Doe, SHRM-CP".
    name = parts[0].split(",")[0].strip()
    words = name.split()
    if not 2 <= len(words) <= 4 or not all(NAME_WORD.fullmatch(word) for word in words):
        return None
    rest = " ".join(parts[1:])
    if not RECRUITING.search(rest) or not mentions(rest, company):
        return None
    return Person(name, parts[1], link)


def guesses(person: Person, domain: str) -> list[Contact]:
    """Likely addresses of a person at the company domain, like jane.doe@ and jdoe@."""
    words = plain_words(person.name)
    if not domain or len(words) < 2:
        return []
    first, last = words[0], words[-1]
    found = f"{person.name}, {person.role}"
    return [
        Contact(f"{local}@{domain}", found, GUESS, person.name)
        for local in (f"{first}.{last}", first, f"{first}{last}", f"{first[0]}{last}")
    ]


def plain_words(name: str) -> list[str]:
    """The words of a name in plain lower case letters, without accents, for building addresses."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [word for word in (re.sub(r"[^a-z]", "", part) for part in plain.split()) if word]


def mentions(text: str, company: str) -> bool:
    """True when text names the whole company, so Acme Logistics is not Acme Robotics."""
    name = company_words(company)
    words = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    return bool(name) and re.search(rf"\b{re.escape(name)}\b", words) is not None


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
