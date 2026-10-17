from datetime import datetime, timezone

import pytest
from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.teamtailor import Teamtailor

FEED = "https://quinyx.teamtailor.com/jobs.rss"


def jobs(tmp_path, feed, name="Quinyx AB"):
    config = board_config(tmp_path, "teamtailor", {"quinyx": "Quinyx AB"}, search={"max_age_days": 100000})
    return Teamtailor(config, FakeClient({FEED: feed})).board_jobs(Company("teamtailor", "quinyx", name))


def test_items_are_mapped(tmp_path):
    first, second = jobs(tmp_path, fixture("teamtailor.xml"))
    assert first.source == "teamtailor"
    assert first.external_id == "5f59d943-f382-4428-a894-b0b847b7d392"
    assert first.title == "Product Marketing Director"
    assert first.company == "Quinyx AB"
    assert first.url == "https://careers.quinyx.com/jobs/8505736-product-marketing-director"
    assert first.location == "Stockholm, Sweden"
    assert first.remote is False
    assert first.posted_at == datetime(2026, 10, 6, 12, 24, 47, tzinfo=timezone.utc)
    assert first.description.startswith("\N{DIRECT HIT} About the role\nProduct Marketing at Quinyx")
    assert first.department == "Marketing"
    assert first.tags == []
    assert second.tags == ["Product Manager"]
    assert second.location == "London, United Kingdom"


def test_company_name_from_the_feed(tmp_path):
    assert jobs(tmp_path, fixture("teamtailor.xml"), name="")[0].company == "Quinyx"


@pytest.mark.parametrize("status, expected", [("fully", True), ("onsite", False), ("none", None), ("temporary", None)])
def test_remote_status(tmp_path, status, expected):
    feed = fixture("teamtailor.xml").replace("<remoteStatus>hybrid</remoteStatus>", f"<remoteStatus>{status}</remoteStatus>")
    assert jobs(tmp_path, feed)[0].remote is expected
