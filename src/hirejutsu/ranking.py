"""Scoring jobs against the profile and picking the best ones."""

import difflib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from .models import Job, Match, Profile

RANKING_DEFAULTS = {
    "top": 10,
    "per_company": 2,
    "weights": {"skills": 0.35, "title": 0.2, "seniority": 0.1, "freshness": 0.1, "location": 0.05},
    "half_life_days": 3,
    "seniority_tolerance": 2,
    "location_mode": "filter",
    "exclude_keywords": [],
    "exclude_title_words": [],
    "exclude_companies": [],
    "require_keywords": [],
    "min_score": 0,
    "max_age_days": None,
    "min_salary": None,
    "salary_currency": "",
}

# Score for a part that cannot be judged, such as skills when the profile lists none.
NEUTRAL = 0.5
# A skill named in the job title counts this many times.
TITLE_BONUS = 2
# A job that mentions about this many of your skills gets full skill marks, so a long skill list
# does not push every score down.
FULL_SKILLS = 8
# Title similarity from which a title counts as close to one you want.
CLOSE_TITLE = 0.6
MAX_REASONS = 4

WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
WORD = re.compile(r"[a-z0-9+#]+")
COMPOUND = re.compile(r"\b(back|front|full)[ -](end|stack)\b")
YEARS = re.compile(r"(\d{1,2})\s*(\+|plus)?\s*(?:(?:-|\N{EN DASH}|to)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?)\b")
# Experience right after the years, as in "5 years of relevant experience" or "4 yrs exp".
EXPERIENCE = re.compile(r"(?:\s+of)?(?:\s+[\w-]+){0,2}?\s+exp")
# Title words spelled out, or swapped for the word most titles use: a backend developer and a
# backend engineer do the same job.
TITLE_ALIASES = {
    "sr": "senior", "snr": "senior", "jr": "junior", "eng": "engineer", "engg": "engineer", "dev": "engineer",
    "developer": "engineer", "mgr": "manager", "sde": "software engineer", "swe": "software engineer",
}
# Years of experience a title word usually means, as (low, high) with high None when open ended.
LEVELS = {
    "intern": (0, 1), "internship": (0, 1), "trainee": (0, 1), "junior": (0, 2), "mid": (2, 5),
    "senior": (4, 10), "lead": (6, 12), "staff": (8, 15), "principal": (10, None),
    "manager": (6, None), "director": (10, None), "head": (10, None), "vp": (12, None),
}
# Seniority is scored on its own, so these words are left out when comparing titles. Manager,
# director, head and vp stay in because they also name the role.
SENIORITY_WORDS = set(LEVELS) - {"manager", "director", "head", "vp"}
NUMERALS = {"i", "ii", "iii", "iv", "v"}
REMOTE_WORDS = ("remote", "anywhere", "wfh", "work from home")
PLACE_ALIASES = [
    {"bengaluru", "bangalore"}, {"gurugram", "gurgaon"}, {"mumbai", "bombay"}, {"delhi", "ncr"},
    {"chennai", "madras"}, {"kolkata", "calcutta"}, {"us", "usa", "united states"}, {"uk", "united kingdom"},
]
# Pay periods per year, to compare salaries with min_salary.
SALARY_PERIODS = {"hour": 2080, "day": 260, "week": 52, "month": 12}
STOPWORDS = frozenset(
    "a about after all also an and any are as at be been but by can could do does each for from had has have he "
    "her here his how i if in into is its just may me more most my no not of on only or other our out over she "
    "should so some such than that the their them then there these they this those through to too under up very "
    "was we were what when where which while who why will with would you your".split()
)


@dataclass
class _Entry:
    """A candidate job and what is known about it so far."""

    job: Job
    found: list[str]
    words: list[str]
    asked: tuple[int, int | None] | None = None
    parts: dict[str, float] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class _Run:
    """One ranking: the profile and settings, and what was learned from the candidate jobs."""

    profile: Profile
    settings: dict
    now: datetime
    skills: list[str] = field(init=False)
    titles: list[tuple[str, list[str]]] = field(init=False)
    places: dict[str, str] = field(init=False)
    wants_remote: bool = field(init=False)
    size: int = 0
    skill_weights: dict[str, float] = field(default_factory=dict)
    title_counts: Counter = field(default_factory=Counter)
    title_cache: dict[tuple, tuple[float, str]] = field(default_factory=dict)

    def __post_init__(self):
        self.skills = list(dict.fromkeys(skill.strip().lower() for skill in self.profile.skills if skill.strip()))
        self.titles = [(title, _role_words(_title_words(title))) for title in self.profile.titles]
        self.places = _places(self.profile.locations)
        self.wants_remote = any(location.strip().lower() == "remote" for location in self.profile.locations)


def rank(jobs: list[Job], profile: Profile, settings: dict, now: datetime | None = None) -> list[Match]:
    """Best matches first, at most settings["top"] of them."""
    run = _Run(profile, settings, now or datetime.now().astimezone())
    pool = []
    for job in jobs:
        text = _text(job)
        if not any(problem for _, problem in _checks(job, text, run)):
            pool.append(_entry(job, text, run))
    _learn(pool, run)
    for entry in pool:
        entry.parts = {
            "skills": _skills_score(entry, run),
            "title": _title_match(entry.words, run)[0],
            "seniority": _seniority(entry, run),
            "freshness": _freshness(entry.job, run),
            "location": _location(entry.job, run),
        }
        entry.score = _combine(entry.parts, settings["weights"])
    best = sorted((entry for entry in pool if _relevant(entry)), key=lambda entry: entry.score, reverse=True)
    matches = [
        Match(entry.job, round(entry.score, 3), _reasons(entry, run))
        for entry in best
        if entry.score >= settings["min_score"]
    ]
    return pick(matches, settings["top"], settings["per_company"])


def has_term(text: str, term: str) -> bool:
    """True if term appears in text as a whole word. Works for terms like c++ and node.js."""
    # A find loop is many times faster than a regex with a lookbehind, and this runs for every skill of every job.
    start = text.find(term)
    while start != -1:
        end = start + len(term)
        if (start == 0 or text[start - 1] not in WORD_CHARS) and (end == len(text) or text[end] not in WORD_CHARS):
            return True
        start = text.find(term, start + 1)
    return False


def pick(matches: list[Match], top: int, per_company: int) -> list[Match]:
    """Take matches in order, skipping duplicates and companies that hit their limit."""
    chosen: list[Match] = []
    per: Counter = Counter()
    seen: set[str] = set()
    for match in matches:
        if match.score <= 0 or len(chosen) >= top:
            break
        company = match.job.company.strip().lower()
        if match.job.fingerprint in seen or per[company] >= per_company:
            continue
        seen.add(match.job.fingerprint)
        per[company] += 1
        chosen.append(match)
    return chosen


def _places(locations: list[str]) -> dict[str, str]:
    """Each accepted place name, aliases included, mapped to the profile location it stands for."""
    places = {}
    for location in locations:
        name = location.strip().lower()
        if name and name != "remote":
            for alias in next((group for group in PLACE_ALIASES if name in group), {name}):
                places[alias] = location.strip()
    return places


def _text(job: Job) -> str:
    return f"{job.title}\n{job.description}".lower()


def _checks(job: Job, text: str, run: _Run) -> list[tuple[str, str]]:
    """The hard filters that are on, each with why the job fails it, or "" when it passes."""
    settings = run.settings
    checks = []
    if settings["exclude_companies"]:
        hit = _first_term(job.company.lower(), settings["exclude_companies"])
        checks.append(("exclude_companies", f"company matches {hit}" if hit else ""))
    if settings["exclude_title_words"]:
        hit = _first_term(job.title.lower(), settings["exclude_title_words"])
        checks.append(("exclude_title_words", f"title has {hit}" if hit else ""))
    if settings["exclude_keywords"]:
        hit = _first_term(text, settings["exclude_keywords"])
        checks.append(("exclude_keywords", f"mentions {hit}" if hit else ""))
    if settings["require_keywords"]:
        hit = _first_term(text, settings["require_keywords"])
        checks.append(("require_keywords", "" if hit else "mentions none of them"))
    if settings["max_age_days"] is not None:
        # Jobs without a post date are kept.
        age = _age_days(job.posted_at, run) if job.posted_at else 0.0
        checks.append(("max_age_days", f"posted {age:.0f} days ago" if age > settings["max_age_days"] else ""))
    if settings["min_salary"] is not None:
        pay = _yearly_salary(job, settings["salary_currency"])
        low = pay is not None and pay < settings["min_salary"]
        checks.append(("min_salary", f"pays up to {pay:,.0f} a year" if low else ""))
    if settings["location_mode"] == "filter" and (run.places or run.wants_remote):
        outside = _place(job, run) == ""
        checks.append(("location", f"{job.location or 'Remote'} is not one of your locations" if outside else ""))
    return checks


def _first_term(text: str, terms: list[str]) -> str | None:
    """The first of terms that text has as a whole word, or None."""
    return next((term for term in terms if has_term(text, term.lower())), None)


def _age_days(when: datetime, run: _Run) -> float:
    return max(0.0, (run.now - when).total_seconds() / 86400)


def _yearly_salary(job: Job, currency: str) -> float | None:
    """The job's top salary per year, or None when it is not listed or is in another currency."""
    if not job.salary_max:
        return None
    if currency and job.salary_currency and job.salary_currency.upper() != currency.upper():
        return None
    return job.salary_max * SALARY_PERIODS.get(job.salary_period.lower(), 1)


def _entry(job: Job, text: str, run: _Run) -> _Entry:
    found = [skill for skill in run.skills if has_term(text, skill)]
    return _Entry(job, found, _title_words(job.title), _years_asked(text))


def _learn(pool: list[_Entry], run: _Run) -> None:
    """Count how many candidates mention each skill and title word, so rare ones can weigh more."""
    run.size = len(pool)
    counts = Counter(skill for entry in pool for skill in entry.found)
    run.skill_weights = {skill: _rarity(counts[skill], run.size) for skill in run.skills}
    run.title_counts = Counter(word for entry in pool for word in set(_role_words(entry.words)))


def _rarity(count: int, total: int) -> float:
    """1 for a word that every job has, more the fewer jobs have it."""
    return 1 + math.log((total + 1) / (count + 1))


def _combine(parts: dict[str, float], weights: dict) -> float:
    """Weighted average of the parts, so the score stays between 0 and 1."""
    total = sum(weights.get(name, 0) for name in parts)
    return sum(weights.get(name, 0) * value for name, value in parts.items()) / total if total else 0.0


def _skills_score(entry: _Entry, run: _Run) -> float:
    """Share of your skills the job mentions, rare skills and skills in the title counting more."""
    if not run.skills:
        return NEUTRAL
    weights = run.skill_weights
    got = sum(_skill_weight(skill, entry, run) for skill in entry.found)
    full = sum(weights.values()) * min(1, FULL_SKILLS / len(weights))
    return min(1.0, got / full)


def _skill_weight(skill: str, entry: _Entry, run: _Run) -> float:
    weight = run.skill_weights[skill]
    return weight * TITLE_BONUS if has_term(entry.job.title.lower(), skill) else weight


def _title_words(title: str) -> list[str]:
    """Lower case title words with aliases applied, so "Sr. Back-end Dev" gives senior backend engineer."""
    words = []
    for word in WORD.findall(COMPOUND.sub(r"\1\2", title.lower())):
        words += TITLE_ALIASES.get(word, word).split()
    return words


def _role_words(words: list[str]) -> list[str]:
    """Title words that name the role, without seniority words, numbers and filler."""
    return [
        word for word in words
        if word not in SENIORITY_WORDS and word not in STOPWORDS and word not in NUMERALS and not word.isdigit()
    ]


def _title_match(words: list[str], run: _Run) -> tuple[float, str]:
    """Similarity to the closest wanted title, and that title as the profile spells it."""
    role = tuple(_role_words(words))
    if role not in run.title_cache:
        run.title_cache[role] = max(
            ((_title_similarity(role, wanted, run), title) for title, wanted in run.titles),
            default=(NEUTRAL, ""),
        )
    return run.title_cache[role]


def _title_similarity(words: tuple[str, ...], wanted: list[str], run: _Run) -> float:
    if not words or not wanted:
        return 0.0
    ours, theirs = set(words), set(wanted)
    overlap = 2 * _title_weight(ours & theirs, run) / (_title_weight(ours, run) + _title_weight(theirs, run))
    spelling = difflib.SequenceMatcher(None, " ".join(words), " ".join(wanted)).ratio()
    # Shared words decide most of it, weighted by rarity so a common word like engineer counts for
    # little. The spelling ratio adds some credit for near misses like analyst and analytics.
    return 0.75 * overlap + 0.25 * spelling


def _title_weight(words: set[str], run: _Run) -> float:
    return sum(_rarity(run.title_counts[word], run.size) for word in words)


def _level(words: list[str]) -> str | None:
    """The seniority word in a title, if any."""
    found = [word for word in words if word in LEVELS]
    if not found:
        return None
    # An intern or junior word decides, so a junior product manager is still a junior role.
    entry = [word for word in found if LEVELS[word][0] == 0]
    return entry[0] if entry else max(found, key=lambda word: LEVELS[word][0])


def _years_asked(text: str) -> tuple[int, int | None] | None:
    """Years of experience a description asks for, as (low, high) with high None when open ended."""
    asked = None
    for match in YEARS.finditer(text):
        low, plus, high = int(match[1]), match[2], match[3]
        before = text[max(0, match.start() - 12):match.start()]
        clear = plus or high or "least" in before or "min" in before or EXPERIENCE.match(text, match.end())
        # Only clear requirements count: a bare "12 years" or anything above 15 is usually about the company.
        if clear and low <= 15 and (asked is None or low > asked[0]):
            asked = (low, int(high) if high else None)
    return asked


def _seniority(entry: _Entry, run: _Run) -> float:
    """Full marks when the level and years asked fit your years, halving for each year beyond the tolerance."""
    years = run.profile.years
    bands = [band for band in (LEVELS.get(_level(entry.words)), entry.asked) if band]
    if years is None or not bands:
        return NEUTRAL
    gap = max(_gap(years, band) for band in bands)
    tolerance = run.settings["seniority_tolerance"]
    return 1.0 if gap <= tolerance else 0.5 ** (gap - tolerance)


def _gap(years: float, band: tuple[int, int | None]) -> float:
    """Years between your experience and a (low, high) band, 0 inside it."""
    low, high = band
    if years < low:
        return low - years
    if high is not None and years > high:
        return years - high
    return 0


def _freshness(job: Job, run: _Run) -> float:
    """Halves every half_life_days after the job was posted, or first seen when the post date is unknown."""
    posted = job.posted_at or job.first_seen
    if posted is None:
        return NEUTRAL
    return 0.5 ** (_age_days(posted, run) / run.settings["half_life_days"])


def _place(job: Job, run: _Run) -> str | None:
    """Which of your locations the job is in: "Remote" or a place, "" for none, None when it is unknown."""
    if not run.places and not run.wants_remote:
        return None
    where = job.location.lower()
    remote = job.remote is True or any(has_term(where, word) for word in REMOTE_WORDS)
    if remote and run.wants_remote:
        return "Remote"
    if not where:
        return "" if remote else None
    return next((location for name, location in run.places.items() if has_term(where, name)), "")


def _location(job: Job, run: _Run) -> float:
    place = _place(job, run)
    if place is None:
        return NEUTRAL
    return 1.0 if place else 0.0


def _relevant(entry: _Entry) -> bool:
    """A job needs one of your skills or a close title to be worth showing."""
    return bool(entry.found) or entry.parts["title"] >= CLOSE_TITLE


def _reasons(entry: _Entry, run: _Run) -> list[str]:
    reasons = [
        _skills_reason(entry, run),
        _title_reason(entry, run),
        _seniority_reason(entry, run),
        _location_reason(entry.job, run),
        _freshness_reason(entry.job, run),
    ]
    return [reason for reason in reasons if reason][:MAX_REASONS]


def _skills_reason(entry: _Entry, run: _Run) -> str:
    if not entry.found:
        return ""
    names = sorted(entry.found, key=lambda skill: _skill_weight(skill, entry, run), reverse=True)[:3]
    return f"Skills: {', '.join(names)} ({len(entry.found)} of {len(run.skills)})"


def _title_reason(entry: _Entry, run: _Run) -> str:
    similarity, title = _title_match(entry.words, run)
    return f"Title close to {title}" if title and similarity >= CLOSE_TITLE else ""


def _seniority_reason(entry: _Entry, run: _Run) -> str:
    years = run.profile.years
    if years is None:
        return ""
    tolerance = run.settings["seniority_tolerance"]
    if entry.asked and (years < entry.asked[0] or _gap(years, entry.asked) > tolerance):
        low, high = entry.asked
        span = f"{low}+" if high is None else f"{low}-{high}"
        return f"Asks {span} years, you have {years:g}"
    level = _level(entry.words)
    if level and _gap(years, LEVELS[level]) > tolerance:
        return f"Asks {level} level, you have {years:g} years"
    return ""


def _location_reason(job: Job, run: _Run) -> str:
    place = _place(job, run)
    if place is None:
        return ""
    if not place:
        return f"Outside your locations: {job.location or 'Remote'}"
    return place if place == "Remote" else f"In {place}"


def _freshness_reason(job: Job, run: _Run) -> str:
    if job.posted_at is None:
        return ""
    days = max(0, (run.now.date() - job.posted_at.astimezone(run.now.tzinfo).date()).days)
    if days == 0:
        return "Posted today"
    return "Posted yesterday" if days == 1 else f"Posted {days} days ago"
