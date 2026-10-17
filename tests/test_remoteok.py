from datetime import datetime, timedelta, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.remoteok import API_URL, RemoteOK, fix_text

UTC = timezone.utc


def fetch(tmp_path, feed, max_age_days=36500):
    config = Config({"search": {"max_age_days": max_age_days}}, tmp_path)
    return RemoteOK(config, FakeClient({API_URL: feed})).fetch()


def test_maps_jobs_and_skips_the_legal_notice(tmp_path):
    jobs = fetch(tmp_path, fixture("remoteok.json"))
    assert [job.external_id for job in jobs] == ["1137512", "1137506", "1137482"]
    job = jobs[0]
    assert (job.source, job.title, job.company) == ("remoteok", "Customer Support Specialist", "Ultimate Marketing")
    assert job.url == "https://remoteok.com/remote-jobs/remote-customer-support-specialist-ultimate-marketing-1137512"
    assert job.remote is True
    assert job.location == ""
    assert job.posted_at == datetime(2026, 10, 14, 1, 31, 49, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (50000, 90000, "USD", "year")
    assert job.tags == ["customer support"]
    assert job.description.startswith("Join Our Global Customer Engagement Network\nCompany: Ultimate Marketing LLC\n")


def test_repairs_double_encoded_text(tmp_path):
    jobs = {job.external_id: job for job in fetch(tmp_path, fixture("remoteok.json"))}
    assert "Inbox rotation\N{TRADE MARK SIGN} and deliverability AI\N{TRADE MARK SIGN}." in jobs["1137506"].description
    assert jobs["1137482"].location == "Ciudad de M\xe9xico, Mexico"


def test_fix_text_leaves_good_text_alone():
    assert fix_text("caf\xe9") == "caf\xe9"
    assert fix_text("don\N{RIGHT SINGLE QUOTATION MARK}t") == "don\N{RIGHT SINGLE QUOTATION MARK}t"
    assert fix_text("Attribute\xe2\x84") == "Attribute\xe2\x84"


def test_zero_salary_means_unknown(tmp_path):
    job = fetch(tmp_path, fixture("remoteok.json"))[2]
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (None, None, "", "")


def test_small_salaries_are_hourly(tmp_path):
    feed = fixture("remoteok.json")
    feed[1].update(salary_min=40, salary_max=48)
    assert fetch(tmp_path, feed)[0].salary_period == "hour"


def test_drops_jobs_older_than_max_age(tmp_path):
    feed = fixture("remoteok.json")
    now = datetime.now(UTC)
    for item, days in zip(feed[1:], (2, 30, 40)):
        item["date"] = (now - timedelta(days=days)).isoformat()
    assert [job.external_id for job in fetch(tmp_path, feed, max_age_days=14)] == ["1137512"]
