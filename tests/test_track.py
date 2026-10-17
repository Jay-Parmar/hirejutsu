from datetime import datetime, timezone

import pytest

from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.store import Store

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def job(external_id, **kwargs):
    fields = {"title": f"Engineer {external_id}", "company": f"Company {external_id}", "url": f"https://x/{external_id}"}
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
