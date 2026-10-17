from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import requests
from fakes import FakeClient

from hirejutsu.companies import Company
from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.models import Job
from hirejutsu.sources.ats import AtsSource, DetailSource, likely_match, pay_period, remote_from, tags, title_words
from hirejutsu.store import Store

NOW = datetime.now(timezone.utc)


def job(source, board, number, title="Backend Engineer", days_old=1, **fields):
    return Job(source, f"{board}-{number}", title, board.title(), f"https://ats.test/{board}/{number}",
               posted_at=NOW - timedelta(days=days_old), **fields)


class Listing(AtsSource):
    name = "listing"

    def __init__(self, config, client, listings):
        super().__init__(config, client)
        self.listings = listings

    def boards(self):
        return [Company(self.name, slug, slug.title()) for slug in self.listings]

    def board_jobs(self, board):
        found = self.listings[board.slug]
        if isinstance(found, Exception):
            raise found
        return found


class Detailed(Listing, DetailSource):
    name = "detailed"

    def job_details(self, board, job):
        return replace(job, description=self.client.get_json(job.url)["text"])


def config(tmp_path, name, keywords=(), max_age_days=14, **settings):
    data = {"search": {"keywords": list(keywords), "max_age_days": max_age_days}, "sources": {name: settings}}
    return Config(data, tmp_path)


def test_title_words_skip_common_words():
    assert title_words(["Head of Data", "Backend Engineer"]) == ("backend", "data", "engineer", "head")


def test_title_filter_never_drops_a_title_with_a_keyword_word():
    keywords = ["Senior Backend Engineer", "Head of Data", "C++ developer", "Node.js", "Ingeniero de datos"]
    words = title_words(keywords)
    for word in words:
        for title in (word, word.upper(), f"Staff {word.title()} II (Remote)", f"x-{word}/y", f"[{word}]"):
            assert likely_match(title, words), title


def test_title_filter_matches_longer_forms():
    words = title_words(["Backend Engineer"])
    assert likely_match("Engineering Manager", words)
    assert likely_match("Senior Backend-Platform Developer", words)
    assert not likely_match("Account Executive", words)
    assert not likely_match("Director of Sales", title_words(["Head of Data"]))


@pytest.mark.parametrize("text, expected", [
    ("Remote from the US", True),
    ("remote", True),
    ("Hybrid - New York, NY", False),
    ("OnSite", False),
    ("on_site", False),
    ("Office - Flexible", False),
    ("Seattle, San Francisco", None),
    ("unspecified", None),
    (None, None),
])
def test_remote_from(text, expected):
    assert remote_from(text) is expected


def test_pay_period():
    values = ("per-year-salary", "1 MONTH", "per-hour-wage", "yearly", "daily", "NONE", None)
    assert [pay_period(value) for value in values] == ["year", "month", "hour", "year", "day", "", ""]


def test_tags_drop_blanks_and_repeats():
    assert tags("Data", None, "", " Data ", "remote") == ["Data", "remote"]


def test_fetch_keeps_jobs_titled_like_the_keywords(tmp_path):
    listings = {"acme": [
        job("listing", "acme", 1, "Senior Backend Engineer"),
        job("listing", "acme", 2, "Python Developer"),
        job("listing", "acme", 3, "Account Executive"),
        job("listing", "acme", 4, "ENGINEERING MANAGER"),
    ]}
    source = Listing(config(tmp_path, "listing", keywords=["Backend Engineer", "python"]), FakeClient(), listings)
    assert [found.title for found in source.fetch()] == [
        "Senior Backend Engineer", "Python Developer", "ENGINEERING MANAGER",
    ]


def test_fetch_keeps_everything_without_keywords(tmp_path):
    listings = {"acme": [job("listing", "acme", 1, "Account Executive"), job("listing", "acme", 2, "Chef")]}
    assert len(Listing(config(tmp_path, "listing"), FakeClient(), listings).fetch()) == 2


def test_title_filter_can_be_turned_off(tmp_path):
    listings = {"acme": [job("listing", "acme", 1, "Account Executive")]}
    settings = config(tmp_path, "listing", keywords=["python"], title_filter=False)
    assert len(Listing(settings, FakeClient(), listings).fetch()) == 1


def test_fetch_skips_jobs_older_than_max_age(tmp_path):
    listings = {"acme": [
        job("listing", "acme", 1, days_old=3),
        job("listing", "acme", 2, days_old=30),
        replace(job("listing", "acme", 3), posted_at=None),
    ]}
    found = Listing(config(tmp_path, "listing", max_age_days=7), FakeClient(), listings).fetch()
    assert [item.external_id for item in found] == ["acme-1", "acme-3"]


def test_failed_board_is_reported_and_skipped(tmp_path, caplog):
    listings = {"acme": [job("listing", "acme", 1)], "gone": requests.HTTPError("404 Client Error")}
    source = Listing(config(tmp_path, "listing"), FakeClient(), listings)
    assert [item.external_id for item in source.fetch()] == ["acme-1"]
    assert source.warning == "1 of 2 boards failed"
    assert "gone" in caplog.text


def test_source_fails_when_every_board_fails(tmp_path):
    listings = {"gone": requests.ConnectionError("no network"), "down": ValueError("bad json")}
    with pytest.raises(HirejutsuError, match="all 2 boards failed"):
        Listing(config(tmp_path, "listing"), FakeClient(), listings).fetch()


def test_no_boards_means_no_jobs(tmp_path):
    source = Listing(config(tmp_path, "listing"), FakeClient(), {})
    assert source.fetch() == []
    assert source.warning == ""


def test_probe_counts_jobs_and_reads_the_name(tmp_path):
    listings = {"acme": [job("listing", "acme", 1, days_old=400)]}
    source = Listing(config(tmp_path, "listing", keywords=["chef"]), FakeClient(), listings)
    assert source.probe(Company("listing", "acme")) == (1, "Acme")


def test_details_only_for_wanted_jobs(tmp_path):
    listings = {"acme": [job("detailed", "acme", 1, "Backend Engineer"), job("detailed", "acme", 2, "Chef")]}
    client = FakeClient({"https://ats.test/acme/1": {"text": "Python and SQL"}})
    found = Detailed(config(tmp_path, "detailed", keywords=["engineer"]), client, listings).fetch()
    assert [(item.title, item.description) for item in found] == [("Backend Engineer", "Python and SQL")]
    assert [call[1] for call in client.calls] == ["https://ats.test/acme/1"]


def test_details_skip_jobs_already_saved(tmp_path):
    with Store(tmp_path / "hirejutsu.db") as store:
        store.upsert_jobs([job("detailed", "acme", 1, description="Saved before")], NOW)
    listings = {"acme": [job("detailed", "acme", 1), job("detailed", "acme", 2)]}
    client = FakeClient({"https://ats.test/acme/2": {"text": "New one"}})
    found = Detailed(config(tmp_path, "detailed"), client, listings).fetch()
    assert sorted((item.external_id, item.description) for item in found) == [
        ("acme-1", "Saved before"), ("acme-2", "New one"),
    ]
    assert [call[1] for call in client.calls] == ["https://ats.test/acme/2"]


def test_details_are_capped_newest_first(tmp_path):
    listings = {"acme": [job("detailed", "acme", number, days_old=number) for number in (3, 1, 2)]}
    client = FakeClient({f"https://ats.test/acme/{n}": {"text": f"Job {n}"} for n in (1, 2, 3)})
    found = Detailed(config(tmp_path, "detailed", max_details=2), client, listings).fetch()
    assert {item.external_id: item.description for item in found} == {"acme-1": "Job 1", "acme-2": "Job 2", "acme-3": ""}


def test_failed_details_keep_the_listed_job(tmp_path):
    listings = {"acme": [job("detailed", "acme", 1), job("detailed", "acme", 2)]}
    client = FakeClient({"https://ats.test/acme/1": {"text": "Fine"}})
    source = Detailed(config(tmp_path, "detailed"), client, listings)
    found = source.fetch()
    assert sorted((item.external_id, item.description) for item in found) == [("acme-1", "Fine"), ("acme-2", "")]
    assert source.warning == "1 of 2 job pages failed"
