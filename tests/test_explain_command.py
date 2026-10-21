from datetime import datetime, timezone

import pytest

from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.store import Store

CONFIG = """\
resume: resume.txt
profile:
  skills: [python, django]
  titles: [Backend Engineer]
  locations: [remote]
ranking:
  exclude_title_words: [intern]
"""


@pytest.fixture
def home(tmp_path):
    (tmp_path / "resume.txt").write_text("Python developer building Django services", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(CONFIG, encoding="utf-8")
    jobs = [
        Job("demo", "1", "Backend Engineer", "Acme", "https://x/1", remote=True, description="python and django"),
        Job("demo", "2", "Python Intern", "Beta", "https://x/2", remote=True, description="python"),
    ]
    with Store(tmp_path / "hirejutsu.db") as store:
        store.upsert_jobs(jobs, datetime.now(timezone.utc))
    return str(tmp_path)


def test_explain_shows_parts_filters_and_reasons(home, capsys):
    assert main(["--home", home, "explain", "1"]) == 0
    out = capsys.readouterr().out
    assert "Backend Engineer at Acme" in out
    assert "skills" in out and "freshness" in out and "0.35" in out
    assert "exclude_title_words: passed" in out
    assert "shortlist: passed" in out
    assert "Title close to Backend Engineer" in out


def test_explain_says_why_a_job_is_filtered_out(home, capsys):
    assert main(["--home", home, "explain", "2"]) == 0
    assert "exclude_title_words: failed, title has intern" in capsys.readouterr().out


def test_explain_unknown_job(home, capsys):
    assert main(["--home", home, "explain", "99"]) == 2
    assert "No job with id 99" in capsys.readouterr().out
