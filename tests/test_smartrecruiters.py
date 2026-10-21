from datetime import datetime, timedelta, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.models import Job
from hirejutsu.sources.smartrecruiters import SmartRecruiters
from hirejutsu.text import parse_date

LIST = "https://api.smartrecruiters.com/v1/companies/ServiceNow/postings"
SERVICENOW = Company("smartrecruiters", "ServiceNow", "ServiceNow")


def source(tmp_path, client, **search):
    config = board_config(tmp_path, "smartrecruiters", {"ServiceNow": "ServiceNow"}, search=search)
    return SmartRecruiters(config, client)


def test_list_maps_postings(tmp_path):
    first, second, _ = source(tmp_path, FakeClient({LIST: fixture("smartrecruiters.json")})).board_jobs(SERVICENOW)
    assert first.source == "smartrecruiters"
    assert first.external_id == "744000156043929"
    assert first.title == "Sr Staff Inbound Product Manager - Partner Relationship Management(PRM)"
    assert first.company == "ServiceNow"
    assert first.url == "https://jobs.smartrecruiters.com/ServiceNow/744000156043929"
    assert first.location == "Hyderabad, Telangana, India"
    assert first.remote is False
    assert first.posted_at == datetime(2026, 10, 16, 16, 28, 12, 166000, tzinfo=timezone.utc)
    assert first.employment_type == "Full-time"
    assert first.department == "Product"
    assert first.tags == ["Engineering", "Information Technology And Services"]
    assert second.remote is True


def test_list_asks_only_for_recent_postings_page_by_page(tmp_path):
    item = fixture("smartrecruiters.json")["content"][0]

    def page(params):
        count = min(100, 250 - params["offset"])
        return {"totalFound": 250, "content": [{**item, "id": str(params["offset"] + n)} for n in range(count)]}

    client = FakeClient({LIST: page})
    jobs = source(tmp_path, client, max_age_days=7).board_jobs(SERVICENOW)
    assert len(jobs) == 250
    assert [call[2]["offset"] for call in client.calls] == [0, 100, 200]
    assert client.calls[0][2]["limit"] == 100
    since = parse_date(client.calls[0][2]["releasedAfter"])
    assert abs(since - (datetime.now(timezone.utc) - timedelta(days=7))) < timedelta(minutes=5)


def test_details_add_the_job_ad(tmp_path):
    client = FakeClient({f"{LIST}/744000156093019": fixture("smartrecruiters_posting.json")})
    listed = Job("smartrecruiters", "744000156093019", "Principal Software Engineer - Veza", "ServiceNow", "https://x")
    job = source(tmp_path, client).job_details(SERVICENOW, listed)
    assert job.description.startswith("Company Description\nIt all started when engineer Fred Luddy")
    assert "Qualifications\nWhat you bring\nCore\n- 15+ years in software engineering" in job.description
    assert job.url == "https://jobs.smartrecruiters.com/ServiceNow/744000156093019-principal-software-engineer-veza"
    assert job.department == "Engineering, Infrastructure and Operations"


def test_probe_counts_all_postings(tmp_path):
    client = FakeClient({LIST: fixture("smartrecruiters.json")})
    assert source(tmp_path, client).probe(Company("smartrecruiters", "ServiceNow")) == (3, "ServiceNow")
    assert client.calls[0][2] == {"limit": 1}


def test_unknown_company_has_no_postings(tmp_path):
    client = FakeClient({LIST: {"offset": 0, "limit": 100, "totalFound": 0, "content": []}})
    assert source(tmp_path, client).board_jobs(SERVICENOW) == []
    assert source(tmp_path, client).probe(SERVICENOW) == (0, "")
