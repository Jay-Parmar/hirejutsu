from datetime import datetime, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.fourdayweek import API_URL, FourDayWeek, plain_text

UTC = timezone.utc


def source(tmp_path, answer=None, locations=(), max_age_days=14, **settings):
    data = {
        "profile": {"locations": list(locations)},
        "search": {"max_age_days": max_age_days},
        "sources": {"fourdayweek": settings},
    }
    return FourDayWeek(Config(data, tmp_path), FakeClient({API_URL: answer or last_page}))


def last_page(params=None):
    page = fixture("fourdayweek.json")
    page["has_more"] = False
    return page


def test_maps_jobs(tmp_path):
    job = source(tmp_path).fetch()[0]
    assert (job.source, job.external_id) == ("fourdayweek", "01a13faf-cf62-7aa9-9d3c-156f35fd9d2c")
    assert (job.title, job.company) == ("Manager, Solutions Consulting", "Nexthink")
    assert job.url == "https://4dayweek.io/job/manager-solutions-consulting-at-nexthink-1b40cc62"
    assert (job.location, job.remote) == ("Boston, Massachusetts, United States", True)
    assert job.posted_at == datetime(2026, 10, 15, 13, 10, 49, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (228000, 280000, "USD", "year")
    assert (job.employment_type, job.department) == ("", "sales")
    assert job.tags[:3] == ["unlimited pto", "Business Acumen", "Coaching"]
    assert job.description.startswith("Company Description\nNexthink is a global leader in Digital Employee Experience.")


def test_hybrid_contract_job(tmp_path):
    job = source(tmp_path).fetch()[2]
    assert (job.location, job.remote, job.employment_type) == ("Edinburgh, United Kingdom", False, "contract")
    assert (job.salary_min, job.salary_max, job.salary_currency) == (41064, 48822, "GBP")
    assert job.tags[0] == "generous pto"
    assert job.tags[-2:] == ["Mass spectrometry", "high throughput seq"]


def test_job_without_salary(tmp_path):
    job = source(tmp_path).fetch()[1]
    assert job.location == "Canada"
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (None, None, "", "")


def test_continent_only_locations(tmp_path):
    page = last_page()
    page["data"][1]["locations"] += [{"continent": "Europe", "work_arrangement": "remote"}, {"work_arrangement": "remote"}]
    assert source(tmp_path, page).fetch()[1].location == "Canada; Europe"


def test_job_without_a_company(tmp_path):
    page = last_page()
    del page["data"][0]["company"]
    assert source(tmp_path, page).fetch()[0].company == ""


def test_plain_text_drops_markdown_marks():
    assert plain_text("#### About\n\n**Location**: Remote\n\n- Python\n") == "About\nLocation: Remote\n- Python"


def test_asks_for_recent_jobs_newest_first(tmp_path):
    fdw = source(tmp_path, max_age_days=10)
    fdw.fetch()
    assert fdw.client.calls[0][2] == {"sort": "date", "limit": 100, "posted_after": 10, "page": 1}


def test_asks_for_remote_jobs_when_you_want_remote(tmp_path):
    fdw = source(tmp_path, locations=["Pune", "remote"])
    fdw.fetch()
    assert fdw.client.calls[0][2]["work_arrangement"] == "remote"


def test_max_age_is_capped_at_a_year(tmp_path):
    fdw = source(tmp_path, max_age_days=5000)
    fdw.fetch()
    assert fdw.client.calls[0][2]["posted_after"] == 365


def test_pages_while_there_is_more(tmp_path):
    fdw = source(tmp_path, lambda params: fixture("fourdayweek.json") if params["page"] < 2 else last_page())
    assert len(fdw.fetch()) == 6
    assert [call[2]["page"] for call in fdw.client.calls] == [1, 2]


def test_stops_at_max_pages(tmp_path):
    fdw = source(tmp_path, lambda params: fixture("fourdayweek.json"), max_pages=2)
    fdw.fetch()
    assert len(fdw.client.calls) == 2
