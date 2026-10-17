import time
from datetime import datetime, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.arbeitnow import API_URL, Arbeitnow

UTC = timezone.utc
FOOTER = '<p>Find <a href="https://www.arbeitnow.com">Jobs in Germany</a> on Arbeitnow</a>'


def source(tmp_path, answer, max_age_days=36500, **settings):
    config = Config({"search": {"max_age_days": max_age_days}, "sources": {"arbeitnow": settings}}, tmp_path)
    return Arbeitnow(config, FakeClient({API_URL: answer}))


def last_page(params=None):
    page = fixture("arbeitnow.json")
    page["links"]["next"] = None
    return page


def test_is_off_by_default(tmp_path):
    assert Arbeitnow(Config({}, tmp_path), FakeClient()).settings["enabled"] is False


def test_maps_jobs(tmp_path):
    job = source(tmp_path, last_page).fetch()[0]
    slug = "remote-account-executive-enterprise-sports-specialist-3930"
    assert (job.source, job.external_id) == ("arbeitnow", slug)
    assert (job.title, job.company) == ("Account Executive - Enterprise - Sports Specialist", "ElevenLabs")
    assert job.url == f"https://www.arbeitnow.com/jobs/companies/elevenlabs/{slug}"
    assert (job.location, job.remote) == ("Remote", True)
    assert job.posted_at == datetime(2026, 10, 17, 11, 40, 17, tzinfo=UTC)
    assert (job.employment_type, job.tags) == ("Full Time", ["Revenue"])
    assert job.description.startswith("About ElevenLabs\nElevenLabs is an AI research and product company")


def test_onsite_jobs(tmp_path):
    job = source(tmp_path, last_page).fetch()[2]
    assert (job.location, job.remote) == ("Cologne", False)
    assert job.employment_type == "Internship (praktikum), internship, no experience required / student"


def test_remote_location_means_remote(tmp_path):
    page = last_page()
    page["data"][2]["location"] = "Remote"
    assert source(tmp_path, page).fetch()[2].remote is True


def test_reads_double_escaped_descriptions(tmp_path):
    page = last_page()
    page["data"][1]["description"] += FOOTER
    text = source(tmp_path, page).fetch()[1].description
    assert text.startswith("A career that\N{RIGHT SINGLE QUOTATION MARK}s the whole package!\nAt Conga")
    assert "<" not in text and "&lt;" not in text
    assert text.endswith("Find Jobs in Germany on Arbeitnow")


def test_pages_until_there_is_no_next_page(tmp_path):
    arbeitnow = source(tmp_path, lambda params: fixture("arbeitnow.json") if params["page"] < 2 else last_page())
    assert len(arbeitnow.fetch()) == 6
    assert [call[2] for call in arbeitnow.client.calls] == [{"page": 1}, {"page": 2}]


def test_stops_at_max_pages(tmp_path):
    arbeitnow = source(tmp_path, lambda params: fixture("arbeitnow.json"))
    arbeitnow.fetch()
    assert len(arbeitnow.client.calls) == 3


def test_stops_at_a_page_with_only_old_jobs(tmp_path):
    def answer(params):
        page = fixture("arbeitnow.json")
        page["data"][0]["created_at"] = int(time.time()) - (86400 if params["page"] == 1 else 30 * 86400)
        for item in page["data"][1:]:
            item["created_at"] = int(time.time()) - 30 * 86400
        return page

    arbeitnow = source(tmp_path, answer, max_age_days=14, max_pages=5)
    assert [job.company for job in arbeitnow.fetch()] == ["ElevenLabs"]
    assert len(arbeitnow.client.calls) == 2
