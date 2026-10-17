from datetime import datetime, timezone

import pytest
import requests
from fakes import FakeClient, board_config, fixture, http_error

from hirejutsu.companies import Company
from hirejutsu.sources.lever import Lever

US = "https://api.lever.co/v0/postings/zoox"
EU = "https://api.eu.lever.co/v0/postings/zoox"
ZOOX = Company("lever", "zoox", "Zoox")


def source(tmp_path, routes):
    config = board_config(tmp_path, "lever", {"zoox": "Zoox"}, search={"max_age_days": 100000})
    return Lever(config, FakeClient(routes))


def test_postings_are_mapped(tmp_path):
    first, second, third = source(tmp_path, {US: fixture("lever.json")}).board_jobs(ZOOX)
    assert first.source == "lever"
    assert first.external_id == "e8a190f0-7a89-4c11-a6a0-452ff6234749"
    assert first.title == "Administrative Business Partner, Floater"
    assert first.company == "Zoox"
    assert first.url == "https://jobs.lever.co/zoox/e8a190f0-7a89-4c11-a6a0-452ff6234749"
    assert first.location == "Foster City, CA"
    assert first.remote is False
    assert first.posted_at == datetime(2026, 10, 6, 17, 27, 44, 932000, tzinfo=timezone.utc)
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (
        123000, 168000, "USD", "year",
    )
    assert first.employment_type == "Full-time"
    assert first.department == "Executive Office"
    assert first.tags == ["Executive Office", "hybrid", "US"]
    assert third.remote is False
    assert third.tags == ["Body, Closures and Chassis", "Vehicle Development", "onsite", "US"]


def test_description_joins_the_sections(tmp_path):
    job = source(tmp_path, {US: fixture("lever.json")}).board_jobs(ZOOX)[0]
    assert job.description.startswith("Zoox is building the future of transportation.")
    assert "Responsibilities\n- Scheduling team and cross-functional meetings\n" in job.description
    assert "Bonus Qualifications\n- Comfortable working in a dynamic environment" in job.description
    assert job.description.endswith("between 3-5 days per week.")


def test_eu_accounts_are_read_from_the_eu_host(tmp_path):
    jobs = source(tmp_path, {US: http_error(404, US), EU: fixture("lever.json")}).board_jobs(ZOOX)
    assert len(jobs) == 3


def test_other_errors_do_not_try_the_eu_host(tmp_path):
    with pytest.raises(requests.HTTPError):
        source(tmp_path, {US: http_error(500, US), EU: fixture("lever.json")}).board_jobs(ZOOX)
