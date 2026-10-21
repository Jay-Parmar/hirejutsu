from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.workable import Workable

API = "https://apply.workable.com/api/v1/widget/accounts/huggingface"


def source(tmp_path, client):
    config = board_config(tmp_path, "workable", {"huggingface": "Hugging Face"}, search={"max_age_days": 100000})
    return Workable(config, client)


def test_jobs_are_mapped(tmp_path):
    client = FakeClient({API: fixture("workable.json")})
    first, _, third = source(tmp_path, client).board_jobs(Company("workable", "huggingface", "Hugging Face"))
    assert client.calls[0][2] == {"details": "true"}
    assert first.source == "workable"
    assert first.external_id == "81B46579FE"
    assert first.title == "Open-Source Machine Learning Engineer - EMEA Remote"
    assert first.company == "Hugging Face"
    assert first.url == "https://apply.workable.com/huggingface/j/81B46579FE/"
    assert first.location == "Paris, \xcele-de-France, France"
    assert first.remote is True
    assert first.posted_at == datetime(2026, 5, 29, tzinfo=timezone.utc)
    assert first.description.startswith("At Hugging Face, we're on a journey to democratize good AI.")
    assert "About the Role\nAs an Open-Source Machine Learning Engineer" in first.description
    assert first.employment_type == "Full-time"
    assert first.department == "Open Source"
    assert first.tags == ["Engineering", "Computer Software"]
    assert third.tags == ["Science", "Computer Software", "Mid-Senior level", "Master's Degree"]


def test_company_name_comes_from_the_account(tmp_path):
    client = FakeClient({API: fixture("workable.json")})
    jobs = source(tmp_path, client).board_jobs(Company("workable", "huggingface"))
    assert jobs[0].company == "Hugging Face"
