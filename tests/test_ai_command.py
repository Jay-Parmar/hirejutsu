from datetime import datetime, timezone

import pytest
from fakes import CLAUDE_URL, FakeClient, claude_reply

from hirejutsu import ai
from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.store import Store


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (tmp_path / "resume.txt").write_text("Python developer", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\nai:\n  enabled: true\n", encoding="utf-8")
    return tmp_path


def fake_ai(monkeypatch, answer):
    client = FakeClient({CLAUDE_URL: answer})
    monkeypatch.setattr(ai, "make_client", lambda settings: client)
    return client


def test_ai_test_shows_the_model_and_that_it_works(home, monkeypatch, capsys):
    fake_ai(monkeypatch, claude_reply("OK"))
    assert main(["--home", str(home), "ai", "test"]) == 0
    out = capsys.readouterr().out
    assert "claude-haiku-5-5" in out
    assert "It works" in out


def test_ai_test_says_when_ai_is_off(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    fake_ai(monkeypatch, claude_reply("OK"))
    assert main(["--home", str(tmp_path), "ai", "test"]) == 0
    assert "ai.enabled" in capsys.readouterr().out


def test_ai_test_reports_a_failure(home, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    fake_ai(monkeypatch, claude_reply("OK"))
    assert main(["--home", str(home), "ai", "test"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def test_ai_explain_prints_the_answer(home, monkeypatch, capsys):
    with Store(home / "hirejutsu.db") as store:
        store.upsert_jobs([Job("demo", "1", "Python Engineer", "Acme", "https://x/1")], datetime.now(timezone.utc))
        job_id = store.find_jobs()[0].id
    client = fake_ai(monkeypatch, claude_reply("8/10. Python fits."))
    assert main(["--home", str(home), "ai", "explain", str(job_id)]) == 0
    out = capsys.readouterr().out
    assert "Python Engineer at Acme" in out
    assert "8/10. Python fits." in out
    assert "Python developer" in client.calls[0][3]["messages"][0]["content"]


def test_ai_explain_unknown_job(home, monkeypatch, capsys):
    fake_ai(monkeypatch, claude_reply("unused"))
    assert main(["--home", str(home), "ai", "explain", "99"]) == 2
    assert "No job with id 99" in capsys.readouterr().out
