import csv
from datetime import date, datetime, timedelta, timezone

import pytest

from hirejutsu.cli import main
from hirejutsu.commands import track
from hirejutsu.models import Job, Match
from hirejutsu.store import Store

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def job(external_id, **kwargs):
    fields = {"title": f"Engineer {external_id}", "company": f"Company {external_id}",
              "url": f"https://x/{external_id}"}
    fields.update(kwargs)
    return Job("demo", external_id, **fields)


@pytest.fixture
def home(tmp_path):
    with Store(tmp_path / "hirejutsu.db") as store:
        store.upsert_jobs([job("a"), job("b"), job("c")], NOW)
    return tmp_path


def hj(home, *args) -> int:
    return main(["--home", str(home), *args])


def statuses(home) -> dict[int, str]:
    with Store(home / "hirejutsu.db") as store:
        return {stored.id: stored.status for stored in store.find_jobs()}


def pick_today(home, *job_ids):
    with Store(home / "hirejutsu.db") as store:
        matches = [Match(store.get_job(job_id), 0.5, ["Skills: python"]) for job_id in job_ids]
        store.record_picks(datetime.now().astimezone().date(), matches)


def set_statuses(home, *changes):
    """(job id, status, days ago) for each change."""
    now = datetime.now(timezone.utc)
    with Store(home / "hirejutsu.db") as store:
        for job_id, status, days_ago in changes:
            store.set_status(job_id, status, at=now - timedelta(days=days_ago))


def listed(home, capsys, *args) -> list[str]:
    assert hj(home, "list", *args) == 0
    out = capsys.readouterr().out
    return [title for title in ("Engineer a", "Engineer b", "Engineer c") if title in out]


def test_applied_marks_several_jobs(home, capsys):
    assert hj(home, "applied", "1", "3", "--note", "via referral") == 0
    assert statuses(home) == {1: "applied", 2: "new", 3: "applied"}
    out = capsys.readouterr().out
    assert "Marked job 1 as applied: Engineer a at Company a" in out
    assert "Marked job 3 as applied" in out
    with Store(home / "hirejutsu.db") as store:
        assert store.get_job(3).note == "via referral"


def test_skip_and_save(home):
    assert hj(home, "skip", "1") == 0
    assert hj(home, "save", "2") == 0
    assert statuses(home) == {1: "skipped", 2: "saved", 3: "new"}


def test_status_sets_any_status(home):
    assert hj(home, "status", "1", "2", "interview") == 0
    assert statuses(home) == {1: "interview", 2: "interview", 3: "new"}


def test_unknown_id_is_reported_and_the_rest_are_marked(home, capsys):
    assert hj(home, "applied", "1", "99", "2") == 1
    assert "No job with id 99" in capsys.readouterr().out
    assert statuses(home) == {1: "applied", 2: "applied", 3: "new"}


def test_status_rejects_unknown_status(home, capsys):
    with pytest.raises(SystemExit):
        hj(home, "status", "1", "maybe")
    assert "invalid choice: 'maybe'" in capsys.readouterr().err
    assert statuses(home)[1] == "new"


def test_today_flag_uses_pick_numbers(home):
    pick_today(home, 3, 1)
    assert hj(home, "applied", "-t", "1", "2") == 0
    assert statuses(home) == {1: "applied", 2: "new", 3: "applied"}


def test_today_flag_reports_missing_pick(home, capsys):
    pick_today(home, 3)
    assert hj(home, "skip", "--today", "1", "4") == 1
    assert "No pick #4 today" in capsys.readouterr().out
    assert statuses(home)[3] == "skipped"


def test_today_flag_without_picks(home, capsys):
    assert hj(home, "applied", "-t", "1") == 2
    assert "hirejutsu run" in capsys.readouterr().out
    assert statuses(home)[1] == "new"


def test_note_keeps_status(home, capsys):
    hj(home, "applied", "1")
    assert hj(home, "note", "1", "recruiter", "called", "back") == 0
    assert "Added a note to job 1" in capsys.readouterr().out
    with Store(home / "hirejutsu.db") as store:
        stored = store.get_job(1)
        assert (stored.status, stored.note) == ("applied", "recruiter called back")


def test_note_on_todays_pick(home):
    pick_today(home, 2)
    assert hj(home, "note", "-t", "1", "ask about visa") == 0
    with Store(home / "hirejutsu.db") as store:
        assert store.get_job(2).note == "ask about visa"


def test_note_on_unknown_job(home, capsys):
    assert hj(home, "note", "99", "hello") == 1
    assert "No job with id 99" in capsys.readouterr().out


def test_show_prints_details_history_and_start_of_description(home, capsys):
    description = "\n".join(f"line {n}" for n in range(1, 51))
    with Store(home / "hirejutsu.db") as store:
        store.upsert_jobs([job("a", location="Pune", salary_min=100000.0, salary_max=150000.0, salary_currency="INR",
                               salary_period="year", description=description)], NOW)
        store.set_status(1, "applied", note="referred by Sam", at=NOW)
        store.add_note(1, "recruiter called", at=NOW)
    assert hj(home, "show", "1") == 0
    out = capsys.readouterr().out
    for text in ("Engineer a at Company a", "Pune", "INR 100,000 - 150,000 per year", "https://x/a",
                 "applied since", "referred by Sam", "recruiter called", "line 40", "10 more lines"):
        assert text in out, text
    assert "line 41" not in out


def test_open_launches_the_browser(home, monkeypatch):
    opened = []
    monkeypatch.setattr(track, "open_url", opened.append)
    pick_today(home, 2, 3)
    assert hj(home, "open", "1") == 0
    assert hj(home, "open", "-t", "2") == 0
    assert opened == ["https://x/a", "https://x/c"]


def test_list_shows_tracked_jobs_latest_change_first(home, capsys):
    set_statuses(home, (1, "applied", 5), (2, "skipped", 1))
    assert hj(home, "list") == 0
    out = capsys.readouterr().out
    assert out.index("Engineer b") < out.index("Engineer a")
    assert "Engineer c" not in out


def test_list_filters(home, capsys):
    set_statuses(home, (1, "applied", 10), (2, "applied", 2), (3, "interview", 1))
    assert listed(home, capsys, "--status", "applied", "--since", "7") == ["Engineer b"]
    assert listed(home, capsys, "--status", "applied", "interview", "--company", "company C") == ["Engineer c"]
    assert listed(home, capsys, "-n", "2") == ["Engineer b", "Engineer c"]


def test_list_without_tracked_jobs(home, capsys):
    assert hj(home, "list") == 0
    assert "No matching jobs" in capsys.readouterr().out


def test_per_week_counts_the_last_few_weeks():
    days = [date(2026, 10, 12), date(2026, 10, 17), date(2026, 10, 1), date(2026, 8, 1)]
    assert track.per_week(days, today=date(2026, 10, 17), weeks=3) == [
        (date(2026, 9, 28), 1),
        (date(2026, 10, 5), 0),
        (date(2026, 10, 12), 2),
    ]


def test_stats(home, capsys):
    set_statuses(home, (1, "applied", 3), (1, "interview", 1), (2, "applied", 2), (3, "skipped", 0))
    pick_today(home, 1, 2, 3)
    assert hj(home, "stats") == 0
    out = capsys.readouterr().out
    assert "Response rate: 50% (1 of 2 applications" in out
    assert "Picks shown: 3" in out
    assert "Company a (1)" in out


def test_stats_without_applications(home, capsys):
    assert hj(home, "stats") == 0
    assert "no applications yet" in capsys.readouterr().out


def test_export_writes_csv(home, capsys):
    set_statuses(home, (1, "applied", 2), (2, "skipped", 1))
    with Store(home / "hirejutsu.db") as store:
        store.add_note(1, "referred by Sam")
        store.add_note(1, "call on Monday")
    path = home / "out.csv"
    assert hj(home, "export", "--output", str(path)) == 0
    assert "Saved 2 jobs" in capsys.readouterr().out
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert [(row["id"], row["status"]) for row in rows] == [("2", "skipped"), ("1", "applied")]
    assert rows[1]["notes"] == "referred by Sam; call on Monday"
    assert rows[1]["applied"] == rows[1]["changed"] != ""
    assert rows[0]["applied"] == ""


def test_export_defaults_to_the_data_folder(home):
    set_statuses(home, (1, "applied", 0), (2, "skipped", 0))
    assert hj(home, "export", "--status", "applied") == 0
    [path] = home.glob("tracked-jobs-*.csv")
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert path.read_text(encoding="utf-8-sig").count("https://x/") == 1


def test_export_reports_unwritable_path(home, capsys):
    assert hj(home, "export", "--output", str(home)) == 2
    assert "Cannot write" in capsys.readouterr().out
