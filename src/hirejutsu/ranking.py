"""Scoring jobs against the profile and picking the best ones."""

import difflib
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .models import Job, Match, Profile

RANKING_DEFAULTS = {"top": 10, "per_company": 2, "weights": {"skills": 0.35, "title": 0.2}}

# Score for a part that cannot be judged, such as skills when the profile lists none.
NEUTRAL = 0.5
# A skill named in the job title counts this many times.
TITLE_BONUS = 2
# A job that mentions about this many of your skills gets full skill marks, so a long skill list
# does not push every score down.
FULL_SKILLS = 8
# Title similarity from which a title counts as close to one you want.
CLOSE_TITLE = 0.6

WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
WORD = re.compile(r"[a-z0-9+#]+")
COMPOUND = re.compile(r"\b(back|front|full)[ -](end|stack)\b")
# Title words spelled out, or swapped for the word most titles use: a backend developer and a
# backend engineer do the same job.
TITLE_ALIASES = {
    "sr": "senior", "snr": "senior", "jr": "junior", "eng": "engineer", "engg": "engineer", "dev": "engineer",
    "developer": "engineer", "mgr": "manager", "sde": "software engineer", "swe": "software engineer",
}
# Seniority is scored on its own, so these words are left out when comparing titles.
SENIORITY_WORDS = {"intern", "internship", "trainee", "junior", "mid", "senior", "lead", "staff", "principal"}
NUMERALS = {"i", "ii", "iii", "iv", "v"}
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
    parts: dict[str, float] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class _Run:
    """One ranking: the profile and settings, and what was learned from the candidate jobs."""

    profile: Profile
    settings: dict
    skills: list[str] = field(init=False)
    titles: list[tuple[str, list[str]]] = field(init=False)
    size: int = 0
    skill_weights: dict[str, float] = field(default_factory=dict)
    title_counts: Counter = field(default_factory=Counter)
    title_cache: dict[tuple, tuple[float, str]] = field(default_factory=dict)

    def __post_init__(self):
        self.skills = list(dict.fromkeys(skill.strip().lower() for skill in self.profile.skills if skill.strip()))
        self.titles = [(title, _role_words(_title_words(title))) for title in self.profile.titles]


def rank(jobs: list[Job], profile: Profile, settings: dict) -> list[Match]:
    """Best matches first, at most settings["top"] of them."""
    run = _Run(profile, settings)
    pool = [_entry(job, run) for job in jobs]
    _learn(pool, run)
    for entry in pool:
        entry.parts = {"skills": _skills_score(entry, run), "title": _title_match(entry.words, run)[0]}
        entry.score = _combine(entry.parts, settings["weights"])
    best = sorted((entry for entry in pool if _relevant(entry)), key=lambda entry: entry.score, reverse=True)
    matches = [Match(entry.job, round(entry.score, 3), _reasons(entry, run)) for entry in best]
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


def _entry(job: Job, run: _Run) -> _Entry:
    text = f"{job.title}\n{job.description}".lower()
    return _Entry(job, [skill for skill in run.skills if has_term(text, skill)], _title_words(job.title))


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


def _relevant(entry: _Entry) -> bool:
    """A job needs one of your skills or a close title to be worth showing."""
    return bool(entry.found) or entry.parts["title"] >= CLOSE_TITLE


def _reasons(entry: _Entry, run: _Run) -> list[str]:
    reasons = [_skills_reason(entry, run), _title_reason(entry, run)]
    return [reason for reason in reasons if reason]


def _skills_reason(entry: _Entry, run: _Run) -> str:
    if not entry.found:
        return ""
    names = sorted(entry.found, key=lambda skill: _skill_weight(skill, entry, run), reverse=True)[:3]
    return f"Skills: {', '.join(names)} ({len(entry.found)} of {len(run.skills)})"


def _title_reason(entry: _Entry, run: _Run) -> str:
    similarity, title = _title_match(entry.words, run)
    return f"Title close to {title}" if title and similarity >= CLOSE_TITLE else ""
