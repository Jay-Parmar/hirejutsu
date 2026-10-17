from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.recruitee import Recruitee

API = "https://channable.recruitee.com/api/offers/"
CHANNABLE = Company("recruitee", "channable", "Channable")


def jobs(tmp_path, data):
    config = board_config(tmp_path, "recruitee", {"channable": "Channable"}, search={"max_age_days": 100000})
    return Recruitee(config, FakeClient({API: data})).board_jobs(CHANNABLE)


def test_offers_are_mapped(tmp_path):
    first, second, _ = jobs(tmp_path, fixture("recruitee.json"))
    assert first.source == "recruitee"
    assert first.external_id == "2786321"
    assert first.title == "Senior Customer Success Manager Benelux"
    assert first.company == "Channable"
    assert first.url == "https://jobs.channable.com/o/senior-customer-success-manager-benelux-9"
    assert first.location == "Utrecht, Utrecht, Netherlands"
    assert first.remote is False
    assert first.posted_at == datetime(2026, 10, 16, 11, 35, tzinfo=timezone.utc)
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (
        3650.0, 5000.0, "EUR", "month",
    )
    assert first.employment_type == "fulltime_fixed_term"
    assert first.department == "Customer Success"
    assert first.description.startswith("Channable is a fast-growing B2B SaaS platform")
    assert "Here's what that looks like day-to-day:" in first.description
    assert first.tags == ["consulting", "experienced"]
    assert second.location == "Remote job"
    assert second.remote is True


def test_placeholder_salary_and_default_url(tmp_path):
    data = fixture("recruitee.json")
    offer = data["offers"][0]
    offer["salary"] = {"min": "1", "max": "5825040", "period": "year", "currency": "INR"}
    offer["careers_url"] = None
    job = jobs(tmp_path, data)[0]
    assert (job.salary_min, job.salary_max, job.salary_currency) == (None, 5825040.0, "INR")
    assert job.url == "https://channable.recruitee.com/o/senior-customer-success-manager-benelux-9"
