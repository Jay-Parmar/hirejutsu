from datetime import datetime

import pytest

from hirejutsu import schedule, sources
from hirejutsu.app import App
from hirejutsu.cli import main
from hirejutsu.doctor import FAIL, OK, WARN, run_checks
from hirejutsu.models import Job
from hirejutsu.sources import Source


class Demo(Source):
    name = "demo"

    def fetch(self):
        return [Job("demo", "1", "Python Engineer", "Acme", "https://x/1", description="python")]


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(sources, "SOURCES", {"demo": Demo})
    monkeypatch.setattr(sources.pkgutil, "iter_modules", lambda path: [])
    monkeypatch.setattr(schedule, "status", lambda: [("Next run", "18-10-2026 09:00:00")])


def write_home(tmp_path, extra=""):
    (tmp_path / "resume.txt").write_text(
        "Backend Engineer, Acme, 2018 - 2024\nPython, Django, PostgreSQL, Docker, AWS, Redis", encoding="utf-8"
    )
    (tmp_path / "config.yaml").write_text("resume: resume.txt\n" + extra, encoding="utf-8")


def statuses(tmp_path):
    return {name: (status, detail) for status, name, detail in run_checks(App(tmp_path))}


def test_fresh_folder_needs_init(tmp_path):
    found = statuses(tmp_path)
    assert found["config"][0] == FAIL
    assert "hirejutsu init" in found["config"][1]


def test_ready_setup_passes(tmp_path):
    write_home(tmp_path)
    found = statuses(tmp_path)
    assert found["config"][0] == OK
    assert found["resume"][0] == OK
    assert "Backend Engineer, 6 years" in found["resume"][1]
    assert found["sources"] == (OK, "1 on: demo")
    assert found["schedule"] == (OK, "next run 18-10-2026 09:00:00")


def test_missing_resume_fails(tmp_path):
    (tmp_path / "config.yaml").write_text("resume: nope.pdf\n", encoding="utf-8")
    assert statuses(tmp_path)["resume"][0] == FAIL


def test_never_fetched_is_a_warning(tmp_path):
    write_home(tmp_path)
    assert statuses(tmp_path)["last fetch"][0] == WARN


def test_failed_sources_are_listed(tmp_path):
    write_home(tmp_path)
    main(["--home", str(tmp_path), "fetch"])
    App(tmp_path).store.log_fetch("demo", datetime.now().astimezone(), 1, 0, 0, "HTTPError")
    status, detail = statuses(tmp_path)["last fetch"]
    assert status == WARN
    assert "demo" in detail


def test_unscheduled_is_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "status", lambda: None)
    write_home(tmp_path)
    assert statuses(tmp_path)["schedule"] == (WARN, "not scheduled, run 'hirejutsu schedule install'")


def test_notify_channel_without_its_secret_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("HIREJUTSU_TELEGRAM_TOKEN", raising=False)
    write_home(tmp_path, "notify:\n  telegram:\n    enabled: true\n    chat_id: '42'\n")
    status, detail = statuses(tmp_path)["notify"]
    assert status == FAIL
    assert "HIREJUTSU_TELEGRAM_TOKEN" in detail


def test_ai_without_a_key_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    write_home(tmp_path, "ai:\n  enabled: true\n")
    status, detail = statuses(tmp_path)["ai"]
    assert status == FAIL
    assert "ANTHROPIC_API_KEY" in detail


def test_local_ai_needs_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    write_home(tmp_path, "ai:\n  enabled: true\n  provider: openai\n  base_url: http://localhost:11434/v1\n")
    assert statuses(tmp_path)["ai"][0] == OK


def test_doctor_command_exit_code(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "doctor"]) == 1
    assert "hirejutsu init" in capsys.readouterr().out
    write_home(tmp_path)
    assert main(["--home", str(tmp_path), "doctor"]) == 0
