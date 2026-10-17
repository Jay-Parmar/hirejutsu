import sys
from datetime import datetime, timezone

import pytest
from fakes import FakeClient, fixture

from hirejutsu.config import Config
from hirejutsu.errors import HirejutsuError
from hirejutsu.sources import available, boards


class FakeJobSpy:
    """Stands in for boards._scrape: records each search and answers with canned rows."""

    def __init__(self):
        self.answers: list = []
        self.searches: list[dict] = []

    def __call__(self, **search):
        self.searches.append(search)
        return self.answers.pop(0) if self.answers else []


@pytest.fixture
def jobspy(monkeypatch):
    fake = FakeJobSpy()
    monkeypatch.setattr(boards, "_scrape", fake)
    return fake


def board(cls, tmp_path, keywords=("python developer",), locations=("Bengaluru",), **sources):
    data = {"search": {"keywords": list(keywords)}, "profile": {"locations": list(locations)}, "sources": sources}
    return cls(Config(data, tmp_path), FakeClient())


def row(**fields):
    """A small jobspy row posted today."""
    base = {
        "id": "in-1",
        "title": "Python Developer",
        "company": "Acme",
        "job_url": "https://in.indeed.com/viewjob?jk=1",
        "date_posted": datetime.now(timezone.utc).date(),
    }
    return {**base, **fields}


@pytest.mark.parametrize("name", ["indeed"])
def test_boards_are_registered_and_off_by_default(tmp_path, name):
    source = board(available()[name], tmp_path)
    assert source.name == name
    assert source.settings["enabled"] is False


def test_indeed_search_arguments(tmp_path, jobspy):
    board(boards.Indeed, tmp_path, locations=["Bengaluru", "remote"]).fetch()
    city, remote = jobspy.searches
    assert city == {
        "site_name": "indeed",
        "search_term": "python developer",
        "location": "Bengaluru",
        "is_remote": False,
        "results_wanted": 50,
        "hours_old": 14 * 24,
        "fetch_description": True,
        "description_format": "html",
        "country_indeed": "India",
    }
    assert (remote["location"], remote["is_remote"]) == (None, True)


def test_one_search_per_keyword_and_place(tmp_path, jobspy):
    board(boards.Indeed, tmp_path, keywords=["python", "django"], locations=["Pune"]).fetch()
    assert [(search["search_term"], search["location"]) for search in jobspy.searches] == [
        ("python", "Pune"),
        ("django", "Pune"),
    ]


def test_no_locations_searches_anywhere(tmp_path, jobspy):
    board(boards.Indeed, tmp_path, locations=[]).fetch()
    assert [(search["location"], search["is_remote"]) for search in jobspy.searches] == [(None, False)]


def test_missing_jobspy_says_how_to_install_it(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jobspy", None)
    with pytest.raises(HirejutsuError, match=r'pip install -e "\.\[jobspy\]"'):
        board(boards.Indeed, tmp_path).fetch()


def test_board_needs_keywords(tmp_path, jobspy):
    with pytest.raises(HirejutsuError, match="keywords"):
        board(boards.Indeed, tmp_path, keywords=[]).fetch()
    assert jobspy.searches == []


def test_indeed_rows_become_jobs(tmp_path, jobspy):
    jobspy.answers = [fixture("jobspy_indeed.json")]
    jobs = board(boards.Indeed, tmp_path).fetch()
    assert len(jobs) == 5
    job = jobs[0]
    assert (job.source, job.external_id, job.title, job.company) == (
        "indeed", "in-34330db3038a4cb7", "Python Developer", "Infopie Business Solutions",
    )
    assert job.url == "https://in.indeed.com/viewjob?jk=34330db3038a4cb7"
    assert job.location == "KA, India"
    assert job.remote is None
    assert job.posted_at == datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (1000000.0, 1800000.0, "INR", "year")
    assert job.employment_type == "fulltime"
    assert job.description.startswith("**Role:** Python Developer\n**Skills:** Python,Django")
    unpaid = jobs[2]
    assert (unpaid.salary_min, unpaid.salary_currency, unpaid.salary_period) == (None, "", "")


def test_description_html_becomes_text(tmp_path, jobspy):
    jobspy.answers = [[row(description="<p>We use <b>Python</b>.</p><ul><li>Django</li><li>SQL</li></ul>")]]
    assert board(boards.Indeed, tmp_path).fetch()[0].description == "We use Python.\n- Django\n- SQL"


def test_remote_flag_true_is_kept_and_false_means_unknown(tmp_path, jobspy):
    jobspy.answers = [[row(id="in-1", is_remote=True), row(id="in-2", is_remote=False)]]
    assert [job.remote for job in board(boards.Indeed, tmp_path).fetch()] == [True, None]


def test_rows_without_title_or_url_are_dropped(tmp_path, jobspy):
    jobspy.answers = [[row(id="in-1", title=None), row(id="in-2", job_url=None), row(id="in-3")]]
    assert [job.external_id for job in board(boards.Indeed, tmp_path).fetch()] == ["in-3"]
