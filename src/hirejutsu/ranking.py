"""Scoring jobs against the profile and picking the best ones."""

from collections import Counter

from .models import Job, Match, Profile

RANKING_DEFAULTS = {"top": 10, "per_company": 2}

WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")


def rank(jobs: list[Job], profile: Profile, settings: dict) -> list[Match]:
    """Best matches first, at most settings["top"] of them."""
    matches = sorted((score(job, profile) for job in jobs), key=lambda match: match.score, reverse=True)
    return pick(matches, settings["top"], settings["per_company"])


def score(job: Job, profile: Profile) -> Match:
    text = f"{job.title}\n{job.description}".lower()
    found = [skill for skill in profile.skills if has_term(text, skill.lower())]
    value = len(found) / len(profile.skills) if profile.skills else 0.0
    return Match(job, round(value, 3), [f"Skills: {', '.join(found)}"] if found else [])


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
