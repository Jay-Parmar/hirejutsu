"""Scoring jobs against the profile and picking the best ones."""

import math
from collections import Counter
from dataclasses import dataclass, field

from .models import Job, Match, Profile

RANKING_DEFAULTS = {"top": 10, "per_company": 2, "weights": {"skills": 1.0}}

# Score for a part that cannot be judged, such as skills when the profile lists none.
NEUTRAL = 0.5
# A skill named in the job title counts this many times.
TITLE_BONUS = 2
# A job that mentions about this many of your skills gets full skill marks, so a long skill list
# does not push every score down.
FULL_SKILLS = 8

WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


@dataclass
class _Entry:
    """A candidate job and what is known about it so far."""

    job: Job
    found: list[str]
    parts: dict[str, float] = field(default_factory=dict)
    score: float = 0.0


@dataclass
class _Run:
    """One ranking: the profile and settings, and what was learned from the candidate jobs."""

    profile: Profile
    settings: dict
    skill_weights: dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        self.skills = list(dict.fromkeys(skill.strip().lower() for skill in self.profile.skills if skill.strip()))


def rank(jobs: list[Job], profile: Profile, settings: dict) -> list[Match]:
    """Best matches first, at most settings["top"] of them."""
    run = _Run(profile, settings)
    pool = [_entry(job, run) for job in jobs]
    _learn(pool, run)
    for entry in pool:
        entry.parts = {"skills": _skills_score(entry, run)}
        entry.score = _combine(entry.parts, settings["weights"])
    best = sorted((entry for entry in pool if entry.found), key=lambda entry: entry.score, reverse=True)
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
    return _Entry(job, [skill for skill in run.skills if has_term(text, skill)])


def _learn(pool: list[_Entry], run: _Run) -> None:
    """Weigh each skill by how rare it is among the candidates."""
    counts = Counter(skill for entry in pool for skill in entry.found)
    run.skill_weights = {skill: _rarity(counts[skill], len(pool)) for skill in run.skills}


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


def _reasons(entry: _Entry, run: _Run) -> list[str]:
    return [reason for reason in [_skills_reason(entry, run)] if reason]


def _skills_reason(entry: _Entry, run: _Run) -> str:
    if not entry.found:
        return ""
    names = sorted(entry.found, key=lambda skill: _skill_weight(skill, entry, run), reverse=True)[:3]
    return f"Skills: {', '.join(names)} ({len(entry.found)} of {len(run.skills)})"
