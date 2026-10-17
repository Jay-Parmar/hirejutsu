from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.base import url_id
from hirejutsu.sources.weworkremotely import CATEGORIES, FEED_URL, WeWorkRemotely, split_skills

UTC = timezone.utc
FULL_STACK = FEED_URL.format("remote-full-stack-programming-jobs")


def source(tmp_path, routes, max_age_days=36500, **settings):
    config = Config({"search": {"max_age_days": max_age_days}, "sources": {"weworkremotely": settings}}, tmp_path)
    return WeWorkRemotely(config, FakeClient(routes))


def fetch(tmp_path, feed=None, **kwargs):
    routes = {FULL_STACK: feed or fixture("weworkremotely.xml")}
    return source(tmp_path, routes, categories=["remote-full-stack-programming-jobs"], **kwargs).fetch()


def test_maps_items(tmp_path):
    job = fetch(tmp_path)[1]
    url = "https://weworkremotely.com/remote-jobs/medify-engineering-manager"
    assert (job.source, job.external_id, job.url) == ("weworkremotely", url_id(url), url)
    assert (job.title, job.company) == ("Engineering Manager", "Medify")
    assert (job.location, job.remote) == ("United Kingdom of Great Britain and Northern Ireland", True)
    assert job.posted_at == datetime(2026, 10, 15, 13, 59, 7, tzinfo=UTC)
    assert (job.employment_type, job.department) == ("Full-Time", "Full-Stack Programming")
    assert job.tags == ["React", "Ruby on Rails", "Performance Management"]
    assert job.description.startswith("Headquarters: London\nURL: http://www.medify.co.uk\n")


def test_splits_company_from_title(tmp_path):
    sales, _, askable = fetch(tmp_path)
    assert sales.company == "UCM Practice Growth Systems"
    assert sales.title == "70-100K Potential for Practice Growth Advisor Sales Position (Central or Eastern Time Zone)"
    assert (askable.company, askable.title) == ("Askable", "Software Engineer, AI Coding Tasks (Contract)")


def test_title_without_company(tmp_path):
    feed = fixture("weworkremotely.xml").replace("<title>Medify: Engineering Manager", "<title>Engineering Manager")
    job = fetch(tmp_path, feed)[1]
    assert (job.company, job.title) == ("", "Engineering Manager")


def test_location_falls_back_to_region(tmp_path):
    assert fetch(tmp_path)[0].location == "Anywhere in the World"


def test_split_skills():
    assert split_skills("C++, Java, Python, TypeScript, Go, and Rust") == ["C++", "Java", "Python", "TypeScript", "Go", "Rust"]
    assert split_skills("Client Relations, and  Relationship Building") == ["Client Relations", "Relationship Building"]
    assert split_skills("TypeScript and Go") == ["TypeScript", "Go"]
    assert split_skills("") == []
    assert split_skills(None) == []


def test_reads_every_category_feed_by_default(tmp_path):
    wwr = source(tmp_path, {FEED_URL.format(name): fixture("weworkremotely.xml") for name in CATEGORIES})
    assert len(wwr.fetch()) == 3 * len(CATEGORIES)
    assert len(wwr.client.calls) == len(CATEGORIES) == 11


def test_categories_setting(tmp_path):
    routes = {FEED_URL.format("remote-design-jobs"): fixture("weworkremotely.xml")}
    wwr = source(tmp_path, routes, categories=["remote-design-jobs"])
    assert len(wwr.fetch()) == 3
    assert [call[1] for call in wwr.client.calls] == ["https://weworkremotely.com/categories/remote-design-jobs.rss"]


def test_drops_jobs_older_than_max_age(tmp_path):
    feed = fixture("weworkremotely.xml")
    now = datetime.now(UTC)
    dates = ["Sat, 17 Oct 2026 00:53:30 +0000", "Thu, 15 Oct 2026 13:59:07 +0000", "Fri, 16 Oct 2026 00:50:53 +0000"]
    for date, days in zip(dates, (1, 30, 400)):
        feed = feed.replace(date, format_datetime(now - timedelta(days=days)))
    assert [job.company for job in fetch(tmp_path, feed, max_age_days=14)] == ["UCM Practice Growth Systems"]
