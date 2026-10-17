from datetime import date, datetime, timedelta, timezone

import pytest

from hirejutsu.config import Config
from hirejutsu.daily import candidates, pick_today
from hirejutsu.models import Job, Match, Profile
from hirejutsu.store import Store

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def job(external_id, **kwargs):
    fields = {"title": f"Python Engineer {external_id}", "company": external_id, "url": f"https://x/{external_id}",
              "description": "python"}
    fields.update(kwargs)
    return Job("demo", external_id, **fields)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as store:
        yield store


def test_candidates_skip_tracked_stale_and_already_picked(store):
    store.upsert_jobs([job("fresh"), job("applied"), job("picked")], NOW)
    store.upsert_jobs([job("stale")], NOW - timedelta(days=10))
    ids = {stored.external_id: stored.id for stored in store.find_jobs()}
    store.set_status(ids["applied"], "applied")
    store.record_picks(date(2026, 10, 16), [Match(store.get_job(ids["picked"]), 0.5)])
    assert [found.external_id for found in candidates(store, NOW)] == ["fresh"]


def test_candidates_keep_todays_picks(store):
    store.upsert_jobs([job("a")], NOW)
    store.record_picks(NOW.date(), [Match(store.find_jobs()[0], 0.5)])
    assert len(candidates(store, NOW)) == 1


def test_pick_today_records_picks(store, tmp_path):
    store.upsert_jobs([job("a"), job("b", title="Java Engineer", description="java")], NOW)
    matches = pick_today(store, Config({}, tmp_path), Profile(skills=["python"]), NOW)
    assert [match.job.external_id for match in matches] == ["a"]
    assert [match.job.external_id for match in store.picks(NOW.date())] == ["a"]
