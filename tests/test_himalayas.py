import time
from datetime import datetime, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.base import url_id
from hirejutsu.sources.himalayas import BROWSE_URL, SEARCH_URL, Himalayas

UTC = timezone.utc
CURSOR = "MjAyNi0xMC0xN1QxMTowMDowOS41NTY3MTNafDI0MjEwOTY"


def source(tmp_path, routes, keywords=(), max_age_days=36500, **settings):
    data = {"search": {"keywords": list(keywords), "max_age_days": max_age_days}, "sources": {"himalayas": settings}}
    return Himalayas(Config(data, tmp_path), FakeClient(routes))


def search_page(params):
    """Search answers: the fixture jobs on page 1, nothing after it."""
    page = fixture("himalayas.json")
    del page["nextCursor"]
    if params["page"] > 1:
        page["jobs"] = []
    return page


def test_maps_jobs(tmp_path):
    job = source(tmp_path, {BROWSE_URL: fixture("himalayas.json")}, max_pages=1).fetch()[0]
    link = "https://himalayas.app/companies/xperteez-technology/jobs/software-engineer-github-contributor-remote-contract"
    assert (job.source, job.external_id, job.url) == ("himalayas", url_id(link), link)
    assert job.title == "\N{EARTH GLOBE AMERICAS} Software Engineer (GitHub Contributor), Remote- Contract"
    assert (job.company, job.location, job.remote) == ("Xperteez Technology", "Worldwide", True)
    assert job.posted_at == datetime(2026, 10, 17, 11, 3, 3, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (50, 100, "USD", "hour")
    assert (job.employment_type, job.department) == ("Contractor", "Developer")
    assert job.tags[:2] == ["Software Engineer", "Backend Engineer"]
    assert job.description.startswith("Role Title: Software Engineer (GitHub Contributor)\n")


def test_jobs_without_salary_or_with_country_limits(tmp_path):
    job = source(tmp_path, {BROWSE_URL: fixture("himalayas.json")}, max_pages=1).fetch()[1]
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (None, None, "", "")
    assert job.location == "Spain"


def test_browses_newest_jobs_by_cursor_without_keywords(tmp_path):
    himalayas = source(tmp_path, {BROWSE_URL: fixture("himalayas.json")}, max_pages=2)
    assert len(himalayas.fetch()) == 6
    assert [call[2] for call in himalayas.client.calls] == [{}, {"cursor": CURSOR}]


def test_browsing_stops_without_a_next_cursor(tmp_path):
    page = fixture("himalayas.json")
    del page["nextCursor"]
    himalayas = source(tmp_path, {BROWSE_URL: page})
    himalayas.fetch()
    assert len(himalayas.client.calls) == 1


def test_searches_each_keyword_until_an_empty_page(tmp_path):
    himalayas = source(tmp_path, {SEARCH_URL: search_page}, keywords=["python developer", "rust"])
    assert len(himalayas.fetch()) == 6
    assert [call[2] for call in himalayas.client.calls] == [
        {"q": "python developer", "sort": "recent", "page": 1},
        {"q": "python developer", "sort": "recent", "page": 2},
        {"q": "rust", "sort": "recent", "page": 1},
        {"q": "rust", "sort": "recent", "page": 2},
    ]


def test_search_stops_at_max_pages(tmp_path):
    himalayas = source(tmp_path, {SEARCH_URL: lambda params: fixture("himalayas.json")}, keywords=["python"], max_pages=3)
    himalayas.fetch()
    assert len(himalayas.client.calls) == 3


def test_stops_at_pages_older_than_max_age(tmp_path):
    def answer(params):
        page = fixture("himalayas.json")
        age = 2 if params["page"] == 1 else 30
        for item in page["jobs"]:
            item["pubDate"] = int(time.time()) - age * 86400
        return page

    himalayas = source(tmp_path, {SEARCH_URL: answer}, keywords=["python"], max_age_days=14, max_pages=5)
    assert len(himalayas.fetch()) == 3
    assert len(himalayas.client.calls) == 2
