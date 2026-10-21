from datetime import datetime, timezone

import pytest

from hirejutsu.models import Job
from hirejutsu.pipeline import fetch_all
from hirejutsu.store import Store

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


class StaticSource:
    def __init__(self, name, jobs=None, error=None, warning=""):
        self.name = name
        self.jobs = jobs or []
        self.error = error
        self.warning = warning

    def fetch(self):
        if self.error:
            raise self.error
        return self.jobs


def job(source, external_id, **kwargs):
    fields = {"title": "Engineer", "company": "Acme", "url": f"https://jobs.example/{external_id}"}
    fields.update(kwargs)
    return Job(source=source, external_id=external_id, **fields)


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.db") as store:
        yield store


def test_fetch_all_saves_jobs(store):
    results = fetch_all([StaticSource("a", [job("a", "1"), job("a", "2")])], store, now=NOW)
    assert [(r.source, r.found, r.added, r.error) for r in results] == [("a", 2, 2, "")]
    assert len(store.find_jobs()) == 2


def test_fetch_all_counts_only_new_jobs(store):
    fetch_all([StaticSource("a", [job("a", "1")])], store, now=NOW)
    results = fetch_all([StaticSource("a", [job("a", "1"), job("a", "2")])], store, now=NOW)
    assert results[0].added == 1


def test_failing_source_does_not_stop_others(store):
    results = fetch_all(
        [StaticSource("bad", error=RuntimeError("boom")), StaticSource("good", [job("good", "1")])],
        store,
        now=NOW,
    )
    by_source = {result.source: result for result in results}
    assert by_source["bad"].error == "RuntimeError: boom"
    assert by_source["good"].added == 1


def test_fetch_all_logs_each_source(store):
    fetch_all([StaticSource("a", [job("a", "1")]), StaticSource("b", error=ValueError("x"))], store, now=NOW)
    rows = {row["source"]: (row["found"], row["error"]) for row in store.last_fetches()}
    assert rows == {"a": (1, ""), "b": (0, "ValueError: x")}


def test_partial_failure_is_kept_as_warning(store):
    results = fetch_all([StaticSource("a", [job("a", "1")], warning="1 of 2 boards failed")], store, now=NOW)
    assert (results[0].added, results[0].error, results[0].warning) == (1, "", "1 of 2 boards failed")
    assert store.last_fetches()[0]["error"] == "1 of 2 boards failed"


def test_fetch_all_drops_duplicates_and_incomplete_jobs(store):
    jobs = [job("a", "1"), job("a", "1", title="Newer"), job("a", "2", title=" "), job("a", "3", url="")]
    results = fetch_all([StaticSource("a", jobs)], store, now=NOW)
    assert results[0].found == 1
    assert [stored.title for stored in store.find_jobs()] == ["Newer"]
