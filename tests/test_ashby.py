from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.ashby import Ashby

API = "https://api.ashbyhq.com/posting-api/job-board"
RAMP = Company("ashby", "ramp", "Ramp")


def source(tmp_path, client):
    return Ashby(board_config(tmp_path, "ashby", {"ramp": "Ramp"}, search={"max_age_days": 100000}), client)


def test_jobs_are_mapped(tmp_path):
    client = FakeClient({f"{API}/ramp": fixture("ashby.json")})
    first, second, third = source(tmp_path, client).board_jobs(RAMP)
    assert client.calls[0][2] == {"includeCompensation": "true"}
    assert first.source == "ashby"
    assert first.external_id == "d84bbf19-572a-499c-9c87-0c154ce85caf"
    assert first.title == "Account Manager | Mid-Market"
    assert first.company == "Ramp"
    assert first.url == "https://jobs.ashbyhq.com/ramp/d84bbf19-572a-499c-9c87-0c154ce85caf"
    assert first.location == "New York, NY (HQ); San Francisco, CA; Remote (US)"
    assert first.remote is True
    assert first.description.startswith("ABOUT RAMP\n\nRamp is building the smart infrastructure")
    assert first.posted_at == datetime(2026, 9, 23, 16, 15, 40, 412000, tzinfo=timezone.utc)
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (
        190000, 330000, "USD", "year",
    )
    assert first.employment_type == "FullTime"
    assert first.department == "Sales"
    assert first.tags == ["Sales", "Account Manager", "Remote"]
    assert second.title == "Security Engineer, Cloud"
    assert (third.salary_min, third.salary_period, third.employment_type) == (12500, "month", "Intern")


def test_hybrid_jobs_are_not_remote_even_when_flagged(tmp_path):
    second = source(tmp_path, FakeClient({f"{API}/ramp": fixture("ashby.json")})).board_jobs(RAMP)[1]
    assert second.remote is False


def test_board_names_with_spaces_and_unlisted_jobs(tmp_path):
    data = fixture("ashby.json")
    data["jobs"][0]["isListed"] = False
    client = FakeClient({f"{API}/hippocratic%20ai": data})
    jobs = source(tmp_path, client).board_jobs(Company("ashby", "hippocratic ai", "Hippocratic AI"))
    assert len(jobs) == 2
    assert jobs[0].company == "Hippocratic AI"
