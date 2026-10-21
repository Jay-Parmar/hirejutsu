from datetime import datetime, timedelta, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.remotive import API_URL, Remotive

UTC = timezone.utc


def source(tmp_path, feed, max_age_days=36500):
    config = Config({"search": {"max_age_days": max_age_days}}, tmp_path)
    return Remotive(config, FakeClient({API_URL: feed}))


def test_maps_jobs(tmp_path):
    jobs = source(tmp_path, fixture("remotive.json")).fetch()
    assert [job.external_id for job in jobs] == ["2069746", "1185979", "2091045"]
    job = jobs[0]
    assert (job.source, job.title, job.company) == ("remotive", "Tech Lead Full-Stack Rails Engineer", "Mitre Media")
    assert job.url == "https://remotive.com/remote-jobs/software-development/tech-lead-full-stack-rails-engineer-2069746"
    assert (job.location, job.remote) == ("USA, Canada, USA timezones", True)
    assert job.posted_at == datetime(2026, 10, 14, 20, 33, 44, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (170000, 200000, "USD", "year")
    assert (job.employment_type, job.department) == ("full-time", "Software Development")
    assert job.tags[:3] == ["api", "CSS", "docker"]
    assert job.description.startswith("About Mitre Media\n")


def test_reads_hourly_and_missing_salaries(tmp_path):
    writer, engineer = source(tmp_path, fixture("remotive.json")).fetch()[1:]
    assert (writer.salary_min, writer.salary_max, writer.salary_period) == (50, 75, "hour")
    assert writer.employment_type == "freelance"
    assert (engineer.salary_min, engineer.salary_max, engineer.salary_currency) == (None, None, "")


def test_strips_company_names(tmp_path):
    feed = fixture("remotive.json")
    feed["jobs"][0]["company_name"] = "Coalition Technologies "
    assert source(tmp_path, feed).fetch()[0].company == "Coalition Technologies"


def test_makes_a_single_call_without_filters(tmp_path):
    remotive = source(tmp_path, fixture("remotive.json"))
    remotive.fetch()
    assert remotive.client.calls == [("GET", API_URL, None, None)]


def test_drops_jobs_older_than_max_age(tmp_path):
    feed = fixture("remotive.json")
    now = datetime.now(UTC).replace(tzinfo=None)
    for item, days in zip(feed["jobs"], (1, 20, 30)):
        item["publication_date"] = (now - timedelta(days=days)).isoformat(timespec="seconds")
    assert [job.external_id for job in source(tmp_path, feed, max_age_days=14).fetch()] == ["2069746"]
