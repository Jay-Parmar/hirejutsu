from datetime import datetime, timedelta, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.jobicy import API_URL, Jobicy

UTC = timezone.utc


def source(tmp_path, answer, max_age_days=36500, **settings):
    config = Config({"search": {"max_age_days": max_age_days}, "sources": {"jobicy": settings}}, tmp_path)
    return Jobicy(config, FakeClient({API_URL: answer}))


def last_page(params=None):
    page = fixture("jobicy.json")
    page.update(nextCursor=None, hasMore=False)
    return page


def test_maps_jobs(tmp_path):
    job = source(tmp_path, last_page).fetch()[0]
    assert (job.source, job.external_id) == ("jobicy", "155586")
    assert (job.title, job.company) == ("Director of Product Design", "Monzo")
    assert job.url == "https://jobicy.com/jobs/155586-director-of-product-design-2"
    assert (job.location, job.remote) == ("UK", True)
    assert job.posted_at == datetime(2026, 10, 17, 8, 33, 8, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (140000, 165000, "GBP", "year")
    assert (job.employment_type, job.department) == ("Full-Time", "Web, UI & UX Design")
    assert job.tags == ["Web, UI & UX Design"]
    assert job.description.startswith("We\N{RIGHT SINGLE QUOTATION MARK}re on a mission to make money work for everyone.\n")


def test_salary_is_optional_and_can_be_monthly(tmp_path):
    _, coach, lead = source(tmp_path, last_page).fetch()
    assert (coach.salary_min, coach.salary_max, coach.salary_currency, coach.salary_period) == (None, None, "", "")
    assert coach.location == "Czechia, Hungary, Poland, Romania, Slovakia"
    assert (lead.salary_min, lead.salary_max, lead.salary_currency, lead.salary_period) == (2000, 3000, "USD", "month")
    assert lead.employment_type == "Contract"


def test_unescapes_company_names(tmp_path):
    page = last_page()
    page["jobs"][0]["companyName"] = "Zone &#038; Co"
    assert source(tmp_path, page).fetch()[0].company == "Zone & Co"


def test_follows_the_cursor_until_there_is_no_more(tmp_path):
    pages = [fixture("jobicy.json"), last_page()]
    jobicy = source(tmp_path, lambda params: pages.pop(0))
    assert len(jobicy.fetch()) == 6
    cursor = fixture("jobicy.json")["nextCursor"]
    assert [call[2] for call in jobicy.client.calls] == [{"count": 200}, {"count": 200, "cursor": cursor}]


def test_stops_at_max_pages(tmp_path):
    jobicy = source(tmp_path, lambda params: fixture("jobicy.json"), max_pages=2)
    jobicy.fetch()
    assert len(jobicy.client.calls) == 2


def test_stops_at_pages_older_than_max_age(tmp_path):
    def answer(params):
        page = fixture("jobicy.json")
        age = 30 if "cursor" in params else 1
        for item in page["jobs"]:
            item["pubDate"] = (datetime.now(UTC) - timedelta(days=age)).isoformat()
        return page

    jobicy = source(tmp_path, answer, max_age_days=14)
    assert len(jobicy.fetch()) == 3
    assert len(jobicy.client.calls) == 2
