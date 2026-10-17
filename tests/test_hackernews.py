from datetime import datetime, timedelta, timezone

from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.sources.hackernews import ITEM_URL, SEARCH_URL, HackerNews, read_header

UTC = timezone.utc
OCTOBER = ITEM_URL.format("49922569")
SEPTEMBER = ITEM_URL.format("49522897")


def source(tmp_path, routes=None, max_age_days=36500, **settings):
    routes = routes or {SEARCH_URL: fixture("hn_search.json"), OCTOBER: fixture("hn_whoishiring.json")}
    config = Config({"search": {"max_age_days": max_age_days}, "sources": {"hackernews": settings}}, tmp_path)
    return HackerNews(config, FakeClient(routes))


def test_reads_job_posts_from_the_latest_thread(tmp_path):
    hn = source(tmp_path)
    assert [job.company for job in hn.fetch()] == ["River", "OpenRent", "PrairieLearn"]
    search, thread = hn.client.calls
    assert search[1:3] == (SEARCH_URL, {
        "query": '"who is hiring"',
        "tags": "story,author_whoishiring",
        "restrictSearchableAttributes": "title",
        "hitsPerPage": 2,
    })
    assert thread[1] == OCTOBER


def test_maps_a_comment(tmp_path):
    job = source(tmp_path).fetch()[0]
    assert (job.source, job.external_id) == ("hackernews", "49923010")
    assert (job.title, job.company) == ("Staff Engineers (Elixir)", "River")
    assert (job.location, job.remote) == ("NYC or REMOTE (US, Europe, South America)", True)
    assert job.url == "https://jobs.ashbyhq.com/river?utm_source=Zp9nJyqvd4"
    assert job.posted_at == datetime(2026, 10, 1, 15, 30, 44, tzinfo=UTC)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (200000, 250000, "USD", "year")
    assert job.employment_type == "Full-Time"
    assert job.description.startswith("River | Staff Engineers (Elixir) | NYC or REMOTE")
    assert "\nI'm Alex, founder and CEO of River." in job.description


def test_comment_without_a_link_points_at_hacker_news(tmp_path):
    thread = fixture("hn_whoishiring.json")
    thread["children"][1]["text"] = "OpenRent | London, UK | Full-Time | ONSITE<p>Come and fix renting."
    routes = {SEARCH_URL: fixture("hn_search.json"), OCTOBER: thread}
    assert source(tmp_path, routes).fetch()[1].url == "https://news.ycombinator.com/item?id=49922695"


def test_dash_separated_headers(tmp_path):
    job = source(tmp_path).fetch()[2]
    assert (job.title, job.company, job.remote) == ("Full-Stack Software Engineer", "PrairieLearn", True)
    assert job.url == "https://www.prairielearn.com"


def test_months_setting_reads_older_threads(tmp_path):
    routes = {SEARCH_URL: fixture("hn_search.json"), OCTOBER: fixture("hn_whoishiring.json"),
              SEPTEMBER: fixture("hn_whoishiring.json")}
    hn = source(tmp_path, routes, months=2)
    hn.fetch()
    assert [call[1] for call in hn.client.calls[1:]] == [OCTOBER, SEPTEMBER]


def test_skips_threads_with_other_titles(tmp_path):
    search = fixture("hn_search.json")
    search["hits"][0]["title"] = "Ask HN: Who wants to be hired? (October 2026)"
    hn = source(tmp_path, {SEARCH_URL: search, SEPTEMBER: fixture("hn_whoishiring.json")})
    hn.fetch()
    assert hn.client.calls[1][1] == SEPTEMBER


def test_drops_comments_older_than_max_age(tmp_path):
    thread = fixture("hn_whoishiring.json")
    now = datetime.now(UTC)
    for comment, days in zip(thread["children"], (2, 20, 20, 20)):
        comment["created_at"] = (now - timedelta(days=days)).isoformat()
    hn = source(tmp_path, {SEARCH_URL: fixture("hn_search.json"), OCTOBER: thread}, max_age_days=14)
    assert [job.company for job in hn.fetch()] == ["River"]


def test_read_header():
    fields = read_header(
        "Sidekick Labs | Senior SWE, R&D Engineer, Intelligence Engineer | REMOTE (US Timezones) | Full-time"
        " | $170k to $230k Base + Equity + Health"
    )
    assert fields == {
        "company": "Sidekick Labs",
        "title": "Senior SWE, R&D Engineer, Intelligence Engineer",
        "location": "REMOTE (US Timezones)",
        "remote": True,
        "employment_type": "Full-time",
        "salary_min": 170000,
        "salary_max": 230000,
        "salary_currency": "USD",
        "salary_period": "year",
    }


def test_read_header_without_a_role():
    fields = read_header("Shepherd (Series B) | ONSITE | San Francisco, CA & New York City, NY")
    assert (fields["company"], fields["title"]) == ("Shepherd", "Open roles")
    assert (fields["location"], fields["remote"]) == ("ONSITE; San Francisco, CA & New York City, NY", False)


def test_read_header_drops_links():
    fields = read_header("Smarkets (https://www.smarkets.com) | Full Time | Hybrid - Onsite (London, UK)")
    assert (fields["company"], fields["employment_type"]) == ("Smarkets", "Full Time")
    assert (fields["location"], fields["remote"]) == ("Hybrid - Onsite (London, UK)", False)
    assert read_header("Snout https://snout.com/ | Multiple Engineering + Product Roles")["company"] == "Snout"


def test_read_header_remote_flag():
    assert read_header("Spade | Ops Roles | ONSITE NYC or REMOTE (US/Can)")["remote"] is True
    assert read_header("OpenRent | London, UK | ONSITE+PART REMOTE")["remote"] is False
    assert read_header("Diffusion | All | SF Bay (Redwood City) | On site (office!), full-time")["remote"] is False
    assert read_header("Reactor | https://reactor.inc | San Francisco, CA, USA | Full Time")["remote"] is None


def test_read_header_skips_chat():
    assert read_header("there used to be 800+ posts here :(") is None
    assert read_header("At Tether (https://tether.io/) we're hiring! All of our roles are fully remote.") is None
    assert read_header("") is None
