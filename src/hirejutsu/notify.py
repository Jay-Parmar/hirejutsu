"""Sending the daily picks by email, Telegram, Discord, Slack and ntfy."""

from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path

from .models import Match
from .report import where


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
