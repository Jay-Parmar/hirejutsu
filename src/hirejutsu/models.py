"""Data types shared across the app."""

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    location: str = ""
    remote: bool | None = None
    description: str = ""
    posted_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_period: str = ""
    employment_type: str = ""
    department: str = ""
    tags: list[str] = field(default_factory=list)
    id: int | None = None
    status: str = "new"
    status_at: datetime | None = None
    note: str = ""
    first_seen: datetime | None = None
    last_seen: datetime | None = None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"

    @property
    def fingerprint(self) -> str:
        """Company and title squashed, to spot the same job listed on two sites."""
        return f"{_squash(self.company)}|{_squash(self.title)}"


def _squash(text: str) -> str:
    text = re.sub(r"\b(inc|llc|ltd|limited|corp|gmbh|pvt|private)\b", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "", text)


@dataclass
class Profile:
    text: str = ""
    skills: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    years: float | None = None
    locations: list[str] = field(default_factory=list)


@dataclass
class Match:
    job: Job
    score: float
    reasons: list[str] = field(default_factory=list)
