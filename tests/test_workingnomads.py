from datetime import datetime, timedelta, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.base import url_id
from hirejutsu.sources.workingnomads import API_URL, WorkingNomads

UTC = timezone.utc


def fetch(tmp_path, feed, max_age_days=36500):
    config = Config({"search": {"max_age_days": max_age_days}}, tmp_path)
    return WorkingNomads(config, FakeClient({API_URL: feed})).fetch()


def test_maps_jobs(tmp_path):
    job = fetch(tmp_path, fixture("workingnomads.json"))[0]
    url = "https://www.workingnomads.com/job/go/1925654/"
    assert (job.source, job.external_id, job.url) == ("workingnomads", url_id(url), url)
    assert (job.title, job.company) == ("Senior Backend Developer (Node.js / Nest.js)", "Proxify")
    assert (job.location, job.remote) == ("Time zone: CET (+/- 3 hours)", True)
    assert job.posted_at == datetime(2026, 10, 8, 16, 54, 14, tzinfo=UTC)
    assert job.department == "Development"
    assert job.tags == ["back-end", "nodejs", "typescript", "javascript", "graphql"]
    assert job.description.startswith("About us:\nTalent has no borders.")


def test_empty_tags(tmp_path):
    assert fetch(tmp_path, fixture("workingnomads.json"))[2].tags == []


def test_drops_jobs_older_than_max_age(tmp_path):
    feed = fixture("workingnomads.json")
    now = datetime.now(UTC)
    for item, days in zip(feed, (3, 20, 60)):
        item["pub_date"] = (now - timedelta(days=days)).isoformat()
    assert [job.company for job in fetch(tmp_path, feed, max_age_days=14)] == ["Proxify"]
