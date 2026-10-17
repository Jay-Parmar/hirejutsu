from datetime import date, datetime, timezone

import pytest

from hirejutsu.cli import main
from hirejutsu.commands import report
from hirejutsu.models import Job, Match
from hirejutsu.store import Store

DAY = date(2026, 10, 17)


def save_picks(home, day):
    with Store(home / "hirejutsu.db") as store:
        store.upsert_jobs([Job("demo", "1", "Python Engineer", "Acme", "https://x/1")], datetime.now(timezone.utc))
        store.record_picks(day, [Match(store.find_jobs()[0], 0.5, ["Skills: python"])])


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(report, "open_url", urls.append)
    return urls


def test_report_rebuilds_a_days_files(tmp_path, capsys):
    save_picks(tmp_path, DAY)
    assert main(["--home", str(tmp_path), "report", "--day", "2026-10-17"]) == 0
    out = capsys.readouterr().out
    for name in ("2026-10-17.md", "2026-10-17.html"):
        assert "Python Engineer" in (tmp_path / "reports" / name).read_text(encoding="utf-8")
        assert name in out


def test_report_writes_chosen_formats(tmp_path):
    save_picks(tmp_path, DAY)
    assert main(["--home", str(tmp_path), "report", "--day", "2026-10-17", "--format", "csv", "json"]) == 0
    assert sorted(path.name for path in (tmp_path / "reports").iterdir()) == ["2026-10-17.csv", "2026-10-17.json"]


def test_report_defaults_to_today(tmp_path):
    save_picks(tmp_path, date.today())
    assert main(["--home", str(tmp_path), "report"]) == 0
    assert (tmp_path / "reports" / f"{date.today().isoformat()}.md").exists()


def test_report_without_picks(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "report", "--day", "2026-10-17"]) == 1
    assert "No picks for 2026-10-17" in capsys.readouterr().out


def test_report_open_shows_the_html_file(tmp_path, opened):
    save_picks(tmp_path, DAY)
    assert main(["--home", str(tmp_path), "report", "--day", "2026-10-17", "--open"]) == 0
    assert opened == [(tmp_path / "reports" / "2026-10-17.html").as_uri()]


def test_report_open_without_html(tmp_path, opened, capsys):
    save_picks(tmp_path, DAY)
    assert main(["--home", str(tmp_path), "report", "--day", "2026-10-17", "--format", "md", "--open"]) == 0
    assert opened == []
    assert "No HTML report to open" in capsys.readouterr().out
