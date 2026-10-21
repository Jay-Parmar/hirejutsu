import logging
from datetime import date, datetime, timezone

import pytest

from hirejutsu import http, sources
from hirejutsu.cli import main
from hirejutsu.models import Job, Match
from hirejutsu.sources import Source
from hirejutsu.store import Store

WEBHOOK = "https://discord.com/api/webhooks/1/abc"
DISCORD = "notify:\n  discord:\n    enabled: true\n"


class Demo(Source):
    name = "demo"

    def fetch(self):
        return [
            Job("demo", str(n), f"Python Engineer {n}", f"Company {n}", f"https://x/{n}", description="python")
            for n in range(3)
        ]


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(sources, "SOURCES", {"demo": Demo})
    monkeypatch.setattr(sources.pkgutil, "iter_modules", lambda path: [])


@pytest.fixture
def posts(monkeypatch):
    """Keep what the HTTP client would post instead of sending it."""
    sent = []

    def post(self, url, json=None, data=None, headers=None):
        sent.append({"url": url, "json": json})
        return ""

    monkeypatch.setattr(http.Client, "post", post)
    return sent


@pytest.fixture
def webhook(monkeypatch):
    monkeypatch.setenv("HIREJUTSU_DISCORD_WEBHOOK", WEBHOOK)


def make_home(tmp_path, extra=""):
    (tmp_path / "resume.txt").write_text("Python developer", encoding="utf-8")
    config = "resume: resume.txt\nprofile:\n  skills: [python]\n" + extra
    (tmp_path / "config.yaml").write_text(config, encoding="utf-8")
    return str(tmp_path)


def test_run_sends_picks_to_enabled_channels(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path, DISCORD), "run"]) == 0
    assert "discord: sent" in capsys.readouterr().out
    [post] = posts
    assert post["url"] == WEBHOOK
    content = post["json"]["content"]
    assert content.startswith("hirejutsu: 3 picks for ")
    assert "1. Python Engineer 0 at Company 0" in content
    assert f"Report: {tmp_path / 'reports'}" in content


def test_run_failed_notification_keeps_exit_code(tmp_path, posts, monkeypatch, capsys):
    monkeypatch.delenv("HIREJUTSU_DISCORD_WEBHOOK", raising=False)
    assert main(["--home", make_home(tmp_path, DISCORD), "run"]) == 0
    assert "discord: failed: notify.discord: environment variable HIREJUTSU_DISCORD_WEBHOOK" in capsys.readouterr().out
    assert posts == []


def test_run_no_notify_sends_nothing(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path, DISCORD), "run", "--no-notify"]) == 0
    assert posts == []
    assert "discord" not in capsys.readouterr().out


def test_run_without_channels_sends_nothing(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path), "run"]) == 0
    assert posts == []
    assert "sent" not in capsys.readouterr().out


def test_notify_test_goes_to_enabled_channels(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path, DISCORD), "notify", "--test"]) == 0
    assert "discord: sent" in capsys.readouterr().out
    [post] = posts
    assert post["json"]["content"].startswith("hirejutsu: test message")


def test_notify_resends_todays_picks(tmp_path, posts, webhook):
    home = make_home(tmp_path, DISCORD)
    main(["--home", home, "run", "--no-notify"])
    assert main(["--home", home, "notify"]) == 0
    [post] = posts
    assert "1. Python Engineer 0 at Company 0" in post["json"]["content"]


def test_notify_day_sends_that_days_picks_and_report(tmp_path, posts, webhook):
    home = make_home(tmp_path, DISCORD)
    with Store(tmp_path / "hirejutsu.db") as store:
        store.upsert_jobs([Job("demo", "a", "Go Developer", "Gopher", "https://x/a"),
                           Job("demo", "b", "Rust Developer", "Crab", "https://x/b")], datetime.now(timezone.utc))
        store.record_picks(date(2026, 10, 16), [Match(job, 0.4) for job in store.find_jobs()])
    report = tmp_path / "reports" / "2026-10-16.md"
    report.parent.mkdir()
    report.write_text("# Job picks", encoding="utf-8")
    assert main(["--home", home, "notify", "--day", "2026-10-16"]) == 0
    content = posts[0]["json"]["content"]
    assert content.startswith("hirejutsu: 2 picks for 2026-10-16")
    assert "1. Go Developer at Gopher" in content
    assert f"Report: {report}" in content


def test_notify_day_without_picks(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path, DISCORD), "notify", "--day", "2026-10-16"]) == 1
    assert "No picks for 2026-10-16" in capsys.readouterr().out
    assert posts == []


def test_notify_without_enabled_channels(tmp_path, posts, capsys):
    assert main(["--home", make_home(tmp_path), "notify", "--test"]) == 1
    assert "Nothing sent" in capsys.readouterr().out


def test_notify_named_channel_must_be_enabled(tmp_path, posts, webhook, capsys):
    assert main(["--home", make_home(tmp_path, DISCORD), "notify", "--test", "--channel", "slack"]) == 1
    assert "notify.slack" in capsys.readouterr().out
    assert posts == []


def test_notify_failure_sets_exit_code(tmp_path, posts, monkeypatch, capsys):
    monkeypatch.delenv("HIREJUTSU_DISCORD_WEBHOOK", raising=False)
    assert main(["--home", make_home(tmp_path, DISCORD), "notify", "--test"]) == 1
    assert "discord: failed" in capsys.readouterr().out


@pytest.fixture
def urllib3_log():
    log = logging.getLogger("urllib3")
    level = log.level
    yield log
    log.setLevel(level)


def test_retry_warnings_with_urls_stay_hidden_unless_verbose(tmp_path, urllib3_log):
    main(["--home", str(tmp_path), "config"])
    assert not urllib3_log.isEnabledFor(logging.WARNING)
    main(["--home", str(tmp_path), "-v", "config"])
    assert urllib3_log.isEnabledFor(logging.WARNING)
