"""Optional AI second opinion on the best matches."""

import json
import os
import re

import requests

from . import http
from .config import Config
from .errors import HirejutsuError
from .text import clean

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


def load_settings(config: Config) -> dict:
    """The ai section, with a blank model, base_url or api_key_env taken from the provider."""
    settings = config.section("ai", AI_DEFAULTS)
    for key, value in PROVIDERS.get(settings["provider"], {}).items():
        settings[key] = settings[key] or value
    return settings


def make_client(settings: dict) -> http.Client:
    """A client of its own, since a model can take far longer to answer than a job site."""
    return http.Client(timeout=settings["timeout"])


def ask(system: str, prompt: str, settings: dict, client) -> str:
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


def _ask_anthropic(system: str, prompt: str, settings: dict, client) -> str:
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


def _ask_openai(system: str, prompt: str, settings: dict, client) -> str:
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
