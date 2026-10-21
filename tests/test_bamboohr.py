from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.bamboohr import BambooHR

LIST = "https://nomadic.bamboohr.com/careers/list"
DETAIL = "https://nomadic.bamboohr.com/careers/27/detail"
NOMADIC = Company("bamboohr", "nomadic", "Nomadic")


def source(tmp_path, client, **search):
    search = {"max_age_days": 100000, **search}
    return BambooHR(board_config(tmp_path, "bamboohr", {"nomadic": "Nomadic"}, search=search), client)


def test_list_maps_openings(tmp_path):
    job = source(tmp_path, FakeClient({LIST: fixture("bamboohr.json")})).board_jobs(NOMADIC)[0]
    assert job.source == "bamboohr"
    assert job.external_id == "nomadic:27"
    assert job.title == "Clerical Support Specialist"
    assert job.company == "Nomadic"
    assert job.url == "https://nomadic.bamboohr.com/careers/27"
    assert job.location == "Pocatello, Idaho"
    assert job.remote is False
    assert job.employment_type == "Part-Time"
    assert job.department == "Clerical"
    assert job.posted_at is None


def test_remote_openings_use_the_hiring_area(tmp_path):
    data = fixture("bamboohr.json")
    data["result"][0].update(
        locationType="1", location={"city": None, "state": None},
        atsLocation={"country": "United States", "state": "New York", "province": None, "city": "Yonkers"},
    )
    job = source(tmp_path, FakeClient({LIST: data})).board_jobs(NOMADIC)[0]
    assert job.remote is True
    assert job.location == "Yonkers, New York, United States"


def test_details_add_description_date_and_pay(tmp_path):
    client = FakeClient({LIST: fixture("bamboohr.json"), DETAIL: fixture("bamboohr_job.json")})
    job = source(tmp_path, client).fetch()[0]
    assert job.description.startswith("Are you ready to turn up the heat on your career?")
    assert job.description.endswith("\nCompensation: Up to $28.25 per hour DOE")
    assert job.posted_at == datetime(2026, 8, 12, tzinfo=timezone.utc)
    assert job.location == "Pocatello, Idaho, United States"
    assert job.external_id == "nomadic:27"
    assert job.url == "https://nomadic.bamboohr.com/careers/27"
