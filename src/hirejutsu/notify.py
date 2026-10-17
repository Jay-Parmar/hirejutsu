"""Sending the daily picks by email, Telegram, Discord, Slack and ntfy."""

import logging
import mimetypes
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate
from html import escape
from pathlib import Path

import requests

from .config import Config, deep_merge
from .errors import HirejutsuError
from .models import Match
from .report import where
from .text import clean

log = logging.getLogger(__name__)

TELEGRAM_LIMIT = 4096
DISCORD_LIMIT = 2000
SMTP_PORTS = {"starttls": 587, "ssl": 465, "none": 25}
SMTP_TIMEOUT = 30

NOTIFY_DEFAULTS = {
    "email": {
        "enabled": False, "host": "", "port": None, "security": "starttls", "username": "",
        "password_env": "HIREJUTSU_SMTP_PASSWORD", "password": "", "from": "", "to": [], "attach": False,
    },
    "telegram": {"enabled": False, "bot_token_env": "HIREJUTSU_TELEGRAM_TOKEN", "bot_token": "", "chat_id": ""},
    "discord": {"enabled": False, "webhook_url_env": "HIREJUTSU_DISCORD_WEBHOOK", "webhook_url": ""},
    "slack": {"enabled": False, "webhook_url_env": "HIREJUTSU_SLACK_WEBHOOK", "webhook_url": ""},
    "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token_env": "", "token": ""},
}


@dataclass
class Message:
    """One notification, ready for any channel."""

    subject: str
    text: str
    html: str
    link: str = ""
    files: list[Path] = field(default_factory=list)


def picks_message(matches: list[Match], day: date, files: list[Path]) -> Message:
    return Message(
        subject=f"hirejutsu: {len(matches)} picks for {day.isoformat()}",
        text=picks_text(matches, files),
        html=picks_html(matches, files),
        link=matches[0].job.url if matches else "",
        files=list(files),
    )


def details(match: Match) -> str:
    return " | ".join(part for part in (where(match), f"score {match.score:.2f}") if part)


def picks_text(matches: list[Match], files: list[Path]) -> str:
    blocks = [
        f"{number}. {match.job.title} at {match.job.company}\n   {details(match)}\n   {match.job.url}"
        for number, match in enumerate(matches, start=1)
    ]
    if files:
        blocks.append("\n".join(f"Report: {path}" for path in files))
    return "\n\n".join(blocks)


def picks_html(matches: list[Match], files: list[Path]) -> str:
    items = "".join(
        f'<li style="margin-bottom:12px"><a href="{escape(match.job.url)}" style="color:#1a56db;font-weight:bold">'
        f"{escape(match.job.title)}</a> at {escape(match.job.company)}<br>"
        f'<span style="color:#555555">{escape(details(match))}</span></li>'
        for match in matches
    )
    reports = "".join(f'<p style="color:#555555">Report: {escape(str(path))}</p>' for path in files)
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#222222"><ol>{items}</ol>{reports}</div>'


def send_all(config: Config, client, message: Message, only: str | None = None) -> list[tuple[str, str]]:
    """Send to every enabled channel. Returns (channel, error) pairs, the error is empty when it was sent."""
    results = []
    for name, send in SENDERS.items():
        settings = deep_merge(NOTIFY_DEFAULTS[name], config.section("notify").get(name) or {})
        if not settings["enabled"] or (only and only != name):
            continue
        try:
            send(settings, client, message)
        except Exception as exc:
            log.debug("Sending to %s failed", name, exc_info=True)
            results.append((name, describe(exc)))
        else:
            results.append((name, ""))
    return results


def describe(exc: Exception) -> str:
    # Request errors quote the URL, and for some channels the URL holds the token.
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code} {clean(exc.response.text)[:200]}".strip()
    if isinstance(exc, requests.RequestException):
        return f"{type(exc).__name__}, check the address and your connection"
    return str(exc) or type(exc).__name__


def secret(settings: dict, key: str, channel: str) -> str:
    """Read key from the environment variable named in key_env, or from the config with a warning."""
    if settings[key]:
        log.warning("notify.%s.%s is written in config.yaml. Put it in an environment variable "
                    "and set %s_env to its name instead.", channel, key, key)
        return str(settings[key])
    name = settings[f"{key}_env"]
    if not name:
        raise HirejutsuError(f"notify.{channel} needs {key}_env in config.yaml")
    value = os.environ.get(name)
    if not value:
        raise HirejutsuError(f"notify.{channel}: environment variable {name} is not set")
    return value


def require(settings: dict, channel: str, *keys: str) -> None:
    missing = [key for key in keys if not settings[key]]
    if missing:
        raise HirejutsuError(f"notify.{channel} needs {', '.join(missing)} in config.yaml")


def split_text(text: str, limit: int) -> list[str]:
    """Pieces of at most limit characters, cut between paragraphs where possible."""
    pieces: list[str] = []
    for block in text.split("\n\n"):
        if pieces and len(pieces[-1]) + 2 + len(block) <= limit:
            pieces[-1] += "\n\n" + block
        else:
            pieces += [block[start:start + limit] for start in range(0, len(block), limit)]
    return pieces


def send_email(settings: dict, client, message: Message) -> None:
    settings = {**settings, "from": settings["from"] or settings["username"]}
    require(settings, "email", "host", "from", "to")
    security = settings["security"]
    if security not in SMTP_PORTS:
        raise HirejutsuError("notify.email.security must be starttls, ssl or none")
    password = secret(settings, "password", "email") if settings["username"] else ""
    mail = email_message(settings, message)
    port = settings["port"] or SMTP_PORTS[security]
    context = ssl.create_default_context()
    if security == "ssl":
        smtp = smtplib.SMTP_SSL(settings["host"], port, timeout=SMTP_TIMEOUT, context=context)
    else:
        smtp = smtplib.SMTP(settings["host"], port, timeout=SMTP_TIMEOUT)
    with smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        if settings["username"]:
            smtp.login(settings["username"], password)
        smtp.send_message(mail)


def email_message(settings: dict, message: Message) -> EmailMessage:
    to = settings["to"]
    mail = EmailMessage()
    mail["Subject"] = message.subject
    mail["From"] = settings["from"]
    mail["To"] = to if isinstance(to, str) else ", ".join(to)
    mail["Date"] = formatdate(localtime=True)
    mail.set_content(message.text)
    mail.add_alternative(message.html, subtype="html")
    if settings["attach"]:
        for path in message.files:
            maintype, subtype = (mimetypes.guess_type(path.name)[0] or "application/octet-stream").split("/")
            mail.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return mail


def send_telegram(settings: dict, client, message: Message) -> None:
    require(settings, "telegram", "chat_id")
    url = f"https://api.telegram.org/bot{secret(settings, 'bot_token', 'telegram')}/sendMessage"
    for piece in split_text(f"{message.subject}\n\n{message.text}", TELEGRAM_LIMIT):
        payload = {"chat_id": settings["chat_id"], "text": piece, "link_preview_options": {"is_disabled": True}}
        client.post(url, json=payload)


def send_discord(settings: dict, client, message: Message) -> None:
    url = secret(settings, "webhook_url", "discord")
    for piece in split_text(f"{message.subject}\n\n{message.text}", DISCORD_LIMIT):
        # Flag 4 is SUPPRESS_EMBEDS, so the job links do not each get a preview card.
        client.post(url, json={"content": piece, "flags": 4})


def send_slack(settings: dict, client, message: Message) -> None:
    url = secret(settings, "webhook_url", "slack")
    # Slack reads &, < and > as markup, so they have to be escaped.
    text = f"{message.subject}\n\n{message.text}".replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    client.post(url, json={"text": text})


def send_ntfy(settings: dict, client, message: Message) -> None:
    require(settings, "ntfy", "topic")
    headers = {"Title": message.subject}
    if message.link:
        headers["Click"] = message.link
    if settings["token"] or settings["token_env"]:
        headers["Authorization"] = f"Bearer {secret(settings, 'token', 'ntfy')}"
    url = f"{settings['server'].rstrip('/')}/{settings['topic']}"
    client.post(url, data=message.text.encode("utf-8"), headers=headers)


SENDERS = {
    "email": send_email,
    "telegram": send_telegram,
    "discord": send_discord,
    "slack": send_slack,
    "ntfy": send_ntfy,
}
