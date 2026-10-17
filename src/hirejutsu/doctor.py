"""Checks that a setup is ready for the daily run."""

import importlib.util
import os
import sys

from . import ai, notify, schedule
from .config import CONFIG_NAME, load_config
from .errors import HirejutsuError
from .resume import load_profile
from .sources import load_sources
from .sources.boards import Board

OK, WARN, FAIL = "ok", "warn", "fail"
FEW_SKILLS = 5
# The env var holding each notify channel's secret. ntfy only needs one for private topics.
CHANNEL_SECRETS = {"email": "password", "telegram": "bot_token", "discord": "webhook_url", "slack": "webhook_url"}


def run_checks(app) -> list[tuple[str, str, str]]:
    """(status, part, detail) for every part of the setup. Later parts are skipped if the config is broken."""
    results = [check_python(), check_config(app)]
    if results[-1][0] == FAIL:
        return results
    for check in (check_resume, check_sources, check_last_fetch, check_schedule, check_notify, check_ai):
        try:
            results.append(check(app))
        except HirejutsuError as exc:
            results.append((FAIL, check.__name__.removeprefix("check_").replace("_", " "), str(exc)))
    return results


def check_python() -> tuple[str, str, str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return (OK if sys.version_info >= (3, 10) else FAIL), "python", f"Python {version}"


def check_config(app) -> tuple[str, str, str]:
    path = app.home / CONFIG_NAME
    if not path.exists():
        return FAIL, "config", f"no {path}, run 'hirejutsu init'"
    try:
        load_config(app.home)
    except HirejutsuError as exc:
        return FAIL, "config", str(exc)
    return OK, "config", str(path)


def check_resume(app) -> tuple[str, str, str]:
    profile = load_profile(app.config)
    years = f", {profile.years:g} years" if profile.years else ""
    titles = f", {', '.join(profile.titles)}" if profile.titles else ""
    detail = f"{len(profile.skills)} skills{titles}{years}"
    if len(profile.skills) < FEW_SKILLS:
        return WARN, "resume", f"{detail}. Add skills under profile.skills, see 'hirejutsu resume'"
    return OK, "resume", detail


def check_sources(app) -> tuple[str, str, str]:
    enabled = load_sources(app.config, app.client)
    if not enabled:
        return FAIL, "sources", "none are on, see 'hirejutsu sources'"
    detail = f"{len(enabled)} on: {', '.join(source.name for source in enabled)}"
    if any(isinstance(source, Board) for source in enabled) and importlib.util.find_spec("jobspy") is None:
        return FAIL, "sources", f"{detail}. The big job boards need: pip install -e \".[jobspy]\""
    return OK, "sources", detail


def check_last_fetch(app) -> tuple[str, str, str]:
    rows = app.store.last_fetches()
    if not rows:
        return WARN, "last fetch", "never, run 'hirejutsu run'"
    failed = [row["source"] for row in rows if row["error"]]
    when = max(row["started_at"] for row in rows)[:16].replace("T", " ")
    if failed:
        return WARN, "last fetch", f"{when} UTC, failed: {', '.join(failed)}. See 'hirejutsu sources'"
    return OK, "last fetch", f"{when} UTC"


def check_schedule(app) -> tuple[str, str, str]:
    rows = schedule.status()
    if rows is None:
        return WARN, "schedule", "not scheduled, run 'hirejutsu schedule install'"
    return OK, "schedule", f"next run {dict(rows).get('Next run', '?')}"


def check_notify(app) -> tuple[str, str, str]:
    enabled = [name for name in notify.SENDERS if notify.channel_settings(app.config, name)["enabled"]]
    if not enabled:
        return OK, "notify", "off"
    missing = []
    for name in enabled:
        settings = notify.channel_settings(app.config, name)
        key = CHANNEL_SECRETS.get(name)
        if key and not settings[key] and not os.environ.get(settings[f"{key}_env"] or ""):
            missing.append(settings[f"{key}_env"] or f"notify.{name}.{key}_env")
    if missing:
        return FAIL, "notify", f"{', '.join(enabled)} on, but not set: {', '.join(missing)}"
    return OK, "notify", ", ".join(enabled)


def check_ai(app) -> tuple[str, str, str]:
    settings = ai.load_settings(app.config)
    if not settings["enabled"]:
        return OK, "ai", "off"
    local = "localhost" in settings["base_url"] or "127.0.0.1" in settings["base_url"]
    if not local and not os.environ.get(settings["api_key_env"] or ""):
        return FAIL, "ai", f"on, but {settings['api_key_env']} is not set"
    return OK, "ai", f"{settings['provider']} {settings['model']}"
