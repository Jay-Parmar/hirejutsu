import pytest

from hirejutsu import http, sources
from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.sources import Source

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
