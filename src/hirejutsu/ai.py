"""Optional AI second opinion on the best matches."""

import hashlib
import json
import logging
import os
import re

import requests

from . import http
from .config import Config
from .errors import HirejutsuError
from .models import Job, Match, Profile
from .store import Store
from .text import clean

log = logging.getLogger(__name__)

AI_DEFAULTS = {
    "enabled": False,
    "provider": "anthropic",
    "model": "",
    "base_url": "",
    "api_key_env": "",
    "candidates": 30,
    "batch_size": 10,
    "weight": 0.5,
    "max_resume_chars": 8000,
    "max_description_chars": 3000,
    "timeout": 120,
}

PROVIDERS = {
    "anthropic": {
        "model": "claude-haiku-5-5",
        "base_url": "https://api.anthropic.com",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "model": "gpt-5-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
    },
}

# Thinking counts toward this limit, so leave plenty of room for the answer itself.
MAX_TOKENS = 16000

# Part of the cache key. Bump it when the scoring prompt changes so old scores are not reused.
PROMPT_VERSION = 1

SYSTEM = (
    "You help a job seeker decide where to apply. You compare their resume with job postings and judge "
    "the fit honestly: skills, experience, seniority, location and must-have requirements."
)

SCORE_REQUEST = """Rate how well each job above fits my resume, from 0 (no fit) to 10 (excellent fit).
Reply with only a JSON array holding one object per job, like this:
[{"id": 12, "score": 7, "reason": "Strong Python and AWS, but asks for Kubernetes"}]
Keep each reason to one short line: what fits and what is missing."""

EXPLAIN_REQUEST = """How well does this job fit my resume? Give a score from 0 to 10, then a few short lines on
what fits, what is missing and whether I should apply. Plain text, no Markdown."""


def load_settings(config: Config) -> dict:
    """The ai section, with a blank model, base_url or api_key_env taken from the provider."""
    settings = config.section("ai", AI_DEFAULTS)
    for key, value in PROVIDERS.get(settings["provider"], {}).items():
        settings[key] = settings[key] or value
    return settings


def make_client(settings: dict) -> http.Client:
    """A client of its own, since a model can take far longer to answer than a job site."""
    return http.Client(timeout=settings["timeout"])


def ask(system: str, prompt: str, settings: dict, client: http.Client) -> str:
    """Send one prompt to the configured provider and return the text of its answer."""
    provider = settings["provider"]
    if provider not in PROVIDERS:
        raise HirejutsuError(f"Unknown ai.provider '{provider}'. Use anthropic or openai.")
    send = _ask_anthropic if provider == "anthropic" else _ask_openai
    try:
        return send(system, prompt, settings, client)
    except requests.RequestException as exc:
        body = exc.response.text[:300] if exc.response is not None else ""
        raise HirejutsuError(f"AI request failed: {exc} {body}".strip()) from exc


def _ask_anthropic(system: str, prompt: str, settings: dict, client: http.Client) -> str:
    key = os.environ.get(settings["api_key_env"])
    if not key:
        raise HirejutsuError(f"Set the {settings['api_key_env']} environment variable to your Anthropic API key.")
    reply = client.post_json(
        f"{settings['base_url'].rstrip('/')}/v1/messages",
        {
            "model": settings["model"],
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    if reply.get("stop_reason") == "refusal":
        raise HirejutsuError("The model declined to answer.")
    # Thinking blocks can come first; the answer is in the text blocks.
    return "".join(block["text"] for block in reply["content"] if block["type"] == "text")


def _ask_openai(system: str, prompt: str, settings: dict, client: http.Client) -> str:
    key = os.environ.get(settings["api_key_env"])
    reply = client.post_json(
        f"{settings['base_url'].rstrip('/')}/chat/completions",
        {
            "model": settings["model"],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        },
        # Local servers such as Ollama need no key.
        headers={"Authorization": f"Bearer {key}"} if key else None,
    )
    return reply["choices"][0]["message"]["content"] or ""


def rerank(matches: list[Match], profile: Profile, settings: dict, store: Store, client: http.Client) -> list[Match]:
    """Blend AI fit scores into the matches, reusing cached ones, and return them best first."""
    resume = profile.text[: settings["max_resume_chars"]]
    key = _resume_hash(resume)
    scores = {}
    for match in matches:
        cached = store.ai_score(match.job.id, settings["model"], key)
        if cached is not None:
            scores[match.job.id] = cached
    todo = [match.job for match in matches if match.job.id not in scores]
    size = max(1, settings["batch_size"])
    for start in range(0, len(todo), size):
        found = _score_batch(todo[start:start + size], resume, settings, client)
        store.save_ai_scores(settings["model"], key, found)
        scores.update(found)
    rescored = [_blend(match, scores.get(match.job.id), settings["weight"]) for match in matches]
    return sorted(rescored, key=lambda match: match.score, reverse=True)


def _resume_hash(resume: str) -> str:
    """Changes with the resume text or the prompt version, so stale cached scores are not used."""
    return hashlib.sha256(f"{PROMPT_VERSION}\n{resume}".encode()).hexdigest()


def _score_batch(jobs: list[Job], resume: str, settings: dict, client: http.Client) -> dict[int, tuple[float, str]]:
    prompt = _build_prompt(resume, jobs, SCORE_REQUEST, settings["max_description_chars"])
    try:
        reply = ask(SYSTEM, prompt, settings, client)
    except Exception as exc:  # The daily run must never fail because of the AI.
        log.warning("AI scoring failed for a batch of %d, keeping their usual scores: %s", len(jobs), exc)
        return {}
    scores = parse_scores(reply, {job.id for job in jobs})
    if len(scores) < len(jobs):
        log.warning("AI scored only %d of %d jobs, the rest keep their usual scores", len(scores), len(jobs))
    return scores


def _blend(match: Match, scored: tuple[float, str] | None, weight: float) -> Match:
    if scored is None:
        return match
    ai_score, reason = scored
    score = (1 - weight) * match.score + weight * ai_score / 10
    reasons = [f"AI: {reason}", *match.reasons] if reason else match.reasons
    return Match(match.job, round(score, 3), reasons)


def _build_prompt(resume: str, jobs: list[Job], request: str, max_description_chars: int) -> str:
    parts = [f"<resume>\n{resume}\n</resume>"]
    for job in jobs:
        lines = [f'<job id="{job.id}">', f"Title: {job.title}", f"Company: {job.company}"]
        if job.location:
            lines.append(f"Location: {job.location}")
        if job.remote:
            lines.append("Remote: yes")
        lines += ["", job.description[:max_description_chars], "</job>"]
        parts.append("\n".join(lines))
    parts.append(request)
    return "\n\n".join(parts)


def explain(job: Job, profile: Profile, settings: dict, client: http.Client) -> str:
    """The AI's plain text verdict on how well one job fits the resume."""
    resume = profile.text[: settings["max_resume_chars"]]
    prompt = _build_prompt(resume, [job], EXPLAIN_REQUEST, settings["max_description_chars"])
    return ask(SYSTEM, prompt, settings, client).strip()


def parse_scores(reply: str, job_ids: set[int]) -> dict[int, tuple[float, str]]:
    """Score and reason by job id from the model's JSON answer. Malformed entries are skipped."""
    scores = {}
    for item in _json_list(reply):
        try:
            job_id, score = int(item["id"]), float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if job_id in job_ids and 0 <= score <= 10:
            scores[job_id] = (score, clean(str(item.get("reason") or "")))
    return scores


def _json_list(reply: str) -> list:
    """The first JSON list of objects in the reply. Models like to wrap it in code fences or prose."""
    decoder = json.JSONDecoder()
    for found in re.finditer(r"\[", reply):
        try:
            value, _ = decoder.raw_decode(reply, found.start())
        except ValueError:
            continue
        if any(isinstance(item, dict) for item in value):
            return value
    return []
