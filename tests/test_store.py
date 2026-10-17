from datetime import date, datetime, timedelta, timezone

import pytest

from hirejutsu import store as store_module
from hirejutsu.errors import HirejutsuError
from hirejutsu.models import Job, Match
from hirejutsu.store import Store

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def make_job(external_id="1", **kwargs):
    fields = {
        "source": "greenhouse",
        "external_id": external_id,
        "title": "Backend Engineer",
        "company": "Acme",
        "url": f"https://boards.greenhouse.io/acme/jobs/{external_id}",
    }
    fields.update(kwargs)
    return Job(**fields)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as store:
        yield store


def test_upsert_counts_new_jobs(store):
    assert store.upsert_jobs([make_job("1"), make_job("2")], NOW) == 2
    jobs = store.find_jobs()
    assert sorted(job.external_id for job in jobs) == ["1", "2"]
    assert all(job.id for job in jobs)


def test_upsert_updates_existing_job(store):
    store.upsert_jobs([make_job("1")], NOW)
    job_id = store.find_jobs()[0].id
    store.set_status(job_id, "applied", at=NOW)
    later = NOW + timedelta(days=1)
    assert store.upsert_jobs([make_job("1", title="Senior Backend Engineer")], later) == 0
    job = store.get_job(job_id)
    assert job.title == "Senior Backend Engineer"
    assert job.status == "applied"
    assert job.first_seen == NOW
    assert job.last_seen == later


def test_job_fields_round_trip(store):
    posted = datetime(2026, 10, 15, 12, 30, tzinfo=timezone.utc)
    original = make_job(
        location="Remote, India",
        remote=True,
        description="Python and Django",
        posted_at=posted,
        salary_min=100000.0,
        salary_max=150000.0,
        salary_currency="USD",
        salary_period="year",
        employment_type="Full-time",
        department="Engineering",
        tags=["python", "django"],
    )
    store.upsert_jobs([original], NOW)
    job = store.find_jobs()[0]
    for name in ("location", "remote", "description", "posted_at", "salary_min", "salary_max",
                 "salary_currency", "salary_period", "employment_type", "department", "tags"):
        assert getattr(job, name) == getattr(original, name), name


def test_remote_unknown_stays_none(store):
    store.upsert_jobs([make_job(remote=None)], NOW)
    assert store.find_jobs()[0].remote is None


def test_find_jobs_filters(store):
    store.upsert_jobs([make_job("old")], NOW - timedelta(days=10))
    store.upsert_jobs([make_job("new"), make_job("done")], NOW)
    done = next(job for job in store.find_jobs() if job.external_id == "done")
    store.set_status(done.id, "skipped")
    recent = store.find_jobs(statuses=["new"], seen_since=NOW - timedelta(days=1))
    assert [job.external_id for job in recent] == ["new"]


def test_set_status_rejects_unknown_status(store):
    store.upsert_jobs([make_job()], NOW)
    with pytest.raises(HirejutsuError):
        store.set_status(store.find_jobs()[0].id, "maybe")


def test_set_status_rejects_unknown_job(store):
    with pytest.raises(HirejutsuError):
        store.set_status(999, "applied")


def test_set_status_keeps_note(store):
    store.upsert_jobs([make_job()], NOW)
    job_id = store.find_jobs()[0].id
    store.set_status(job_id, "applied", note="referred by Sam")
    assert store.get_job(job_id).note == "referred by Sam"


def test_set_status_remembers_when(store):
    store.upsert_jobs([make_job()], NOW)
    job_id = store.find_jobs()[0].id
    assert store.get_job(job_id).status_at is None
    store.set_status(job_id, "saved", at=NOW)
    assert store.get_job(job_id).status_at == NOW


def test_set_status_records_history(store):
    store.upsert_jobs([make_job()], NOW)
    job_id = store.find_jobs()[0].id
    store.set_status(job_id, "applied", note="referred by Sam", at=NOW)
    store.set_status(job_id, "interview", at=NOW + timedelta(days=3))
    assert store.history(job_id) == [
        ("applied", NOW, "referred by Sam"),
        ("interview", NOW + timedelta(days=3), ""),
    ]


def test_add_note_keeps_status(store):
    store.upsert_jobs([make_job()], NOW)
    job_id = store.find_jobs()[0].id
    store.set_status(job_id, "applied", at=NOW)
    store.add_note(job_id, "recruiter called", at=NOW + timedelta(hours=2))
    job = store.get_job(job_id)
    assert (job.status, job.note) == ("applied", "recruiter called")
    assert store.history(job_id)[-1] == (None, NOW + timedelta(hours=2), "recruiter called")


def test_add_note_rejects_unknown_job(store):
    with pytest.raises(HirejutsuError):
        store.add_note(999, "hello")


def test_upgrade_turns_existing_status_into_history(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    monkeypatch.setattr(store_module, "MIGRATIONS", store_module.MIGRATIONS[:1])
    with Store(path) as old:
        old.upsert_jobs([make_job()], NOW)
        with old.conn:
            old.conn.execute("UPDATE jobs SET status = 'applied', status_at = ?, note = 'by email'", (NOW.isoformat(),))
    monkeypatch.undo()
    with Store(path) as store:
        assert store.history(store.find_jobs()[0].id) == [("applied", NOW, "by email")]


def test_status_counts(store):
    store.upsert_jobs([make_job("1"), make_job("2"), make_job("3")], NOW)
    first, second, _ = store.find_jobs()
    store.set_status(first.id, "applied")
    store.set_status(second.id, "applied")
    assert store.status_counts() == {"new": 1, "applied": 2}


def test_applications_count_each_job_applied_to_once(store):
    store.upsert_jobs([make_job(name, company=name) for name in ("a", "b", "c", "d")], NOW)
    ids = {job.external_id: job.id for job in store.find_jobs()}
    store.set_status(ids["a"], "saved", at=NOW - timedelta(days=9))
    store.set_status(ids["a"], "applied", at=NOW - timedelta(days=8))
    store.set_status(ids["a"], "interview", at=NOW - timedelta(days=2))
    store.set_status(ids["a"], "rejected", at=NOW - timedelta(days=1))
    store.set_status(ids["b"], "applied", at=NOW - timedelta(days=3))
    store.set_status(ids["c"], "applied", at=NOW - timedelta(days=4))
    store.set_status(ids["c"], "new", at=NOW - timedelta(days=4))
    store.set_status(ids["d"], "skipped", at=NOW)
    assert sorted(store.applications()) == [
        ("a", NOW - timedelta(days=8), True),
        ("b", NOW - timedelta(days=3), False),
    ]


def test_pick_count(store):
    store.upsert_jobs([make_job("1"), make_job("2")], NOW)
    first, second = store.find_jobs()
    store.record_picks(date(2026, 10, 16), [Match(first, 0.5)])
    store.record_picks(date(2026, 10, 17), [Match(second, 0.4)])
    assert store.pick_count() == 2


def test_picks_round_trip(store):
    store.upsert_jobs([make_job("1"), make_job("2")], NOW)
    first, second = sorted(store.find_jobs(), key=lambda job: job.external_id)
    day = date(2026, 10, 17)
    store.record_picks(day, [Match(second, 0.9, ["python"]), Match(first, 0.5, [])])
    picks = store.picks(day)
    assert [(match.job.id, match.score, match.reasons) for match in picks] == [
        (second.id, 0.9, ["python"]),
        (first.id, 0.5, []),
    ]
    assert store.picked_job_ids() == {first.id, second.id}
    assert store.picked_job_ids(before=day) == set()


def test_record_picks_replaces_same_day(store):
    store.upsert_jobs([make_job("1"), make_job("2")], NOW)
    first, second = store.find_jobs()
    day = date(2026, 10, 17)
    store.record_picks(day, [Match(first, 0.5)])
    store.record_picks(day, [Match(second, 0.7)])
    assert [match.job.id for match in store.picks(day)] == [second.id]


def test_log_fetch(store):
    store.log_fetch("lever", NOW, 1.5, found=10, added=3)
    store.log_fetch("ashby", NOW, 0.2, found=0, added=0, error="timeout")
    rows = store.last_fetches()
    assert {row["source"]: row["error"] for row in rows} == {"lever": "", "ashby": "timeout"}


def test_prune_drops_stale_untouched_jobs(store):
    store.upsert_jobs([make_job("stale"), make_job("kept"), make_job("picked")], NOW - timedelta(days=60))
    jobs = {job.external_id: job for job in store.find_jobs()}
    store.set_status(jobs["kept"].id, "applied")
    store.record_picks(date(2026, 8, 1), [Match(jobs["picked"], 0.5)])
    assert store.prune(NOW - timedelta(days=30)) == 1
    assert sorted(job.external_id for job in store.find_jobs()) == ["kept", "picked"]


def test_prune_drops_history_of_jobs_set_back_to_new(store):
    store.upsert_jobs([make_job()], NOW - timedelta(days=60))
    job_id = store.find_jobs()[0].id
    store.set_status(job_id, "applied")
    store.set_status(job_id, "new")
    assert store.prune(NOW - timedelta(days=30)) == 1
    assert store.history(job_id) == []


def test_reopening_keeps_data(tmp_path):
    path = tmp_path / "test.db"
    with Store(path) as store:
        store.upsert_jobs([make_job()], NOW)
    with Store(path) as store:
        assert len(store.find_jobs()) == 1
