from datetime import date

import pytest

from hirejutsu import sources
from hirejutsu.cli import main
from hirejutsu.commands import report as report_command
from hirejutsu.models import Job
from hirejutsu.sources import Source
from hirejutsu.store import Store


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
def home(tmp_path):
    (tmp_path / "resume.txt").write_text("Python developer", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\nprofile:\n  skills: [python]\n", encoding="utf-8")
    return str(tmp_path)


def test_run_picks_jobs_and_saves_report(home, tmp_path, capsys):
    assert main(["--home", home, "run"]) == 0
    out = capsys.readouterr().out
    assert "Python Engineer 0" in out
    assert len(list((tmp_path / "reports").glob("*.md"))) == 1


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(report_command, "open_url", urls.append)
    return urls


def todays_html(tmp_path):
    return (tmp_path / "reports" / f"{date.today().isoformat()}.html").as_uri()


def test_run_does_not_open_the_report_by_default(home, opened):
    assert main(["--home", home, "run"]) == 0
    assert opened == []


def test_run_open_shows_the_html_report(home, tmp_path, opened):
    assert main(["--home", home, "run", "--open"]) == 0
    assert opened == [todays_html(tmp_path)]


def test_run_opens_the_html_report_when_configured(home, tmp_path, opened):
    with (tmp_path / "config.yaml").open("a", encoding="utf-8") as config:
        config.write("report:\n  open: true\n")
    assert main(["--home", home, "run"]) == 0
    assert opened == [todays_html(tmp_path)]


def test_run_with_bad_report_format_fails_before_fetching(home, tmp_path, capsys):
    with (tmp_path / "config.yaml").open("a", encoding="utf-8") as config:
        config.write("report:\n  formats: [pdf]\n")
    assert main(["--home", home, "run"]) == 2
    assert "Unknown report format: pdf" in capsys.readouterr().out
    with Store(tmp_path / "hirejutsu.db") as store:
        assert store.find_jobs() == []


def test_today_shows_saved_picks(home, capsys):
    main(["--home", home, "run"])
    capsys.readouterr()
    assert main(["--home", home, "today"]) == 0
    assert "Python Engineer 2" in capsys.readouterr().out


def test_today_without_picks(home, capsys):
    assert main(["--home", home, "today"]) == 1
    assert "hirejutsu run" in capsys.readouterr().out


def test_run_without_resume_fails_before_fetching(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "run"]) == 2
    assert "Resume not found" in capsys.readouterr().out
    with Store(tmp_path / "hirejutsu.db") as store:
        assert store.find_jobs() == []


def test_top_does_not_record_picks(home, tmp_path, capsys):
    main(["--home", home, "fetch"])
    assert main(["--home", home, "top", "-n", "2"]) == 0
    assert "Python Engineer" in capsys.readouterr().out
    with Store(tmp_path / "hirejutsu.db") as store:
        assert store.picked_job_ids() == set()
