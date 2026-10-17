from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.models import Job
from hirejutsu.sources.greenhouse import Greenhouse

LIST = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
STRIPE = Company("greenhouse", "stripe", "Stripe")


def source(tmp_path, client, **search):
    search = {"max_age_days": 100000, **search}
    return Greenhouse(board_config(tmp_path, "greenhouse", {"stripe": "Stripe"}, search=search), client)


def test_list_maps_jobs(tmp_path):
    first, second, _ = source(tmp_path, FakeClient({LIST: fixture("greenhouse_jobs.json")})).board_jobs(STRIPE)
    assert first.source == "greenhouse"
    assert first.external_id == "8262032"
    assert first.title == "Bridge Product Accountant"
    assert first.company == "Stripe"
    assert first.url == "https://stripe.com/jobs/search?gh_jid=8262032"
    assert first.location == "Bengaluru"
    assert first.posted_at == datetime(2026, 10, 9, 5, 54, 16, tzinfo=timezone.utc)
    assert first.remote is None
    assert first.description == ""
    assert second.location == "Remote from the US"
    assert second.remote is True


def test_details_add_description_department_and_pay(tmp_path):
    detail = "https://boards-api.greenhouse.io/v1/boards/coinbase/jobs/8175363"
    listed = Job("greenhouse", "8175363", "Accelerations Programs Intern", "Coinbase", "https://example.com/8175363")
    client = FakeClient({detail: fixture("greenhouse_job.json")})
    job = source(tmp_path, client).job_details(Company("greenhouse", "coinbase", "Coinbase"), listed)
    assert job.description.startswith("Ready to do the most impactful work of your career? At Coinbase,")
    assert "&lt;" not in job.description and "<p>" not in job.description
    assert job.department == "Internships & Emerging Talent Positions"
    assert "US - Remote Zone 1 (Job Requisitions Only)" in job.tags
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (40.0, 40.0, "USD", "hour")
    assert job.location == "Hybrid - New York, NY"
    assert job.remote is False
    assert client.calls[0][2] == {"pay_transparency": "true"}


def test_workplace_type_field_wins_over_location(tmp_path):
    item = {**fixture("greenhouse_jobs.json")["jobs"][0], "metadata": [
        {"id": 1, "name": "Workplace Type", "value": "Remote", "value_type": "single_select"},
        {"id": 2, "name": "Employment Type", "value": "Full-time", "value_type": "single_select"},
    ]}
    job = source(tmp_path, FakeClient()).to_job(STRIPE, item)
    assert job.remote is True
    assert job.employment_type == "Full-time"


def test_fetch_reads_details_only_for_matching_titles(tmp_path):
    listing = fixture("greenhouse_jobs.json")
    wanted = listing["jobs"][1]
    detail = {**wanted, "content": "&lt;p&gt;Python &amp;amp; SQL&lt;/p&gt;", "departments": [{"id": 1, "name": "Security"}]}
    client = FakeClient({LIST: listing, f"{LIST}/{wanted['id']}": detail})
    jobs = source(tmp_path, client, keywords=["Research Engineer"]).fetch()
    assert [(job.title, job.description, job.department) for job in jobs] == [
        ("Abuse Research Engineer", "Python & SQL", "Security"),
    ]
    assert [call[1] for call in client.calls] == [LIST, f"{LIST}/{wanted['id']}"]
