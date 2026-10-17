import logging
import logging.handlers
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from fakes import FakeClient, fixture

from hirejutsu.config import Config, template
from hirejutsu.errors import HirejutsuError
from hirejutsu.sources import available, boards


class FakeJobSpy:
    """Stands in for boards._scrape: records each search and answers with canned rows."""

    def __init__(self):
        self.answers: list = []
        self.searches: list[dict] = []

    def __call__(self, **search):
        self.searches.append(search)
        answer = self.answers.pop(0) if self.answers else []
        return answer() if callable(answer) else answer


def logs(message, level=logging.ERROR, rows=(), board="Indeed"):
    """An answer that logs the way jobspy reports a board's trouble."""

    def answer():
        logging.getLogger(f"JobSpy:{board}").log(level, message)
        return list(rows)

    return answer


@pytest.fixture
def jobspy(monkeypatch):
    fake = FakeJobSpy()
    monkeypatch.setattr(boards, "_scrape", fake)
    return fake


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr("time.sleep", calls.append)
    return calls


def board(cls, tmp_path, keywords=("python developer",), locations=("Bengaluru",), **sources):
    data = {
        "search": {"keywords": list(keywords)},
        "profile": {"locations": list(locations)},
        "sources": sources,
    }
    return cls(Config(data, tmp_path), FakeClient())


class FakeNaT(datetime):
    """Like pandas.NaT, the empty date: a datetime that is not equal to itself."""

    def __ne__(self, other):
        return True


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


BOARDS = ["indeed", "naukri", "linkedin", "glassdoor", "ziprecruiter"]


@pytest.mark.parametrize("name", BOARDS)
def test_boards_are_registered_and_off_by_default(tmp_path, name):
    source = board(available()[name], tmp_path)
    assert source.name == name
    assert source.settings["enabled"] is False


def test_starter_config_shows_how_to_turn_boards_on(tmp_path):
    lines = [re.sub(r"^  # (\w+: \{)", r"  \1", line) for line in template().splitlines()]
    config = Config(yaml.safe_load("\n".join(lines)), tmp_path)
    assert all(available()[name](config, FakeClient()).settings["enabled"] for name in BOARDS)


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


def test_at_most_three_searches_by_default(tmp_path, jobspy):
    board(boards.Indeed, tmp_path, keywords=["python", "django"], locations=["Pune", "Delhi"]).fetch()
    assert [(search["search_term"], search["location"]) for search in jobspy.searches] == [
        ("python", "Pune"),
        ("python", "Delhi"),
        ("django", "Pune"),
    ]


def test_pause_between_searches(tmp_path, jobspy, sleeps):
    board(boards.Indeed, tmp_path, keywords=["python", "django"], indeed={"delay_seconds": 7}).fetch()
    assert len(jobspy.searches) == 2
    assert sleeps == [7]


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
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (
        1000000.0, 1800000.0, "INR", "year",
    )
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


def test_nan_and_nat_cells_count_as_empty(tmp_path, jobspy):
    nan = float("nan")
    jobspy.answers = [[
        row(id="in-1", title=nan),
        row(id="in-2", company=nan, location=nan, description=nan, date_posted=FakeNaT(2026, 1, 1),
            is_remote=nan, min_amount=nan, max_amount=nan, currency=nan, interval=nan, job_type=nan,
            job_function=nan),
    ]]
    [job] = board(boards.Indeed, tmp_path).fetch()
    assert job.external_id == "in-2"
    assert (job.company, job.location, job.description) == ("", "", "")
    assert (job.employment_type, job.department) == ("", "")
    assert (job.posted_at, job.remote) == (None, None)
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (None, None, "", "")


def test_board_error_is_raised_when_nothing_was_found(tmp_path, jobspy):
    jobspy.answers = [logs("Indeed response status code 403")]
    with pytest.raises(HirejutsuError, match="Indeed response status code 403"):
        board(boards.Indeed, tmp_path).fetch()


def test_board_error_after_some_jobs_is_a_warning(tmp_path, jobspy, caplog):
    jobspy.answers = [[row()], logs("Indeed: timed out")]
    assert len(board(boards.Indeed, tmp_path, locations=["Pune", "Delhi"]).fetch()) == 1
    warnings = [record.getMessage() for record in caplog.records
                if record.name == boards.__name__ and record.levelno == logging.WARNING]
    assert warnings == ["Some indeed results may be missing: Indeed: timed out"]


@pytest.mark.parametrize("message, level", [
    ("LinkedIn response status code 429", logging.ERROR),
    ("LinkedIn response status code 429 for job 4477707910", logging.WARNING),
    ("LinkedIn: unexpected page with no jobs (blocked?)", logging.ERROR),
    ("Naukri response status code 406 (recaptcha required): the address is rate limited", logging.ERROR),
    ("Naukri response status code 406 for job 171026015301: rate limited", logging.WARNING),
])
def test_a_block_stops_the_other_searches(tmp_path, jobspy, message, level):
    jobspy.answers = [logs(message, level, rows=[row()])]
    board(boards.Indeed, tmp_path, keywords=["python", "django"]).fetch()
    assert len(jobspy.searches) == 1


def test_other_errors_do_not_stop_the_other_searches(tmp_path, jobspy):
    jobspy.answers = [logs("Indeed: Read timed out"), [row()]]
    assert len(board(boards.Indeed, tmp_path, keywords=["python", "django"]).fetch()) == 1
    assert len(jobspy.searches) == 2


def test_jobspy_handlers_are_muted_during_a_search_and_put_back(tmp_path, jobspy, monkeypatch):
    logger = logging.getLogger("JobSpy:Indeed")
    printer = logging.handlers.BufferingHandler(100)
    monkeypatch.setattr(logger, "handlers", [printer])
    jobspy.answers = [logs("Indeed: timed out", rows=[row()])]
    board(boards.Indeed, tmp_path).fetch()
    assert printer.buffer == []
    assert logger.handlers == [printer]


def test_rows_without_title_or_url_are_dropped(tmp_path, jobspy):
    jobspy.answers = [[row(id="in-1", title=None), row(id="in-2", job_url=None), row(id="in-3")]]
    assert [job.external_id for job in board(boards.Indeed, tmp_path).fetch()] == ["in-3"]


def test_naukri_searches_a_bare_city_without_an_age_limit(tmp_path, jobspy):
    board(boards.Naukri, tmp_path, locations=["Bengaluru, India", "remote"]).fetch()
    city, remote = jobspy.searches
    assert (city["site_name"], city["location"], city["hours_old"], city["results_wanted"]) == (
        "naukri", "Bengaluru", None, 20,
    )
    assert "country_indeed" not in city
    assert (remote["location"], remote["is_remote"]) == (None, True)


def test_naukri_drops_jobs_older_than_max_age(tmp_path, jobspy):
    today = datetime.now(timezone.utc).date()
    jobspy.answers = [[
        row(id="nk-1"),
        row(id="nk-2", date_posted=today - timedelta(days=14)),
        row(id="nk-3", date_posted=today - timedelta(days=15)),
        row(id="nk-4", date_posted=None),
    ]]
    assert [job.external_id for job in board(boards.Naukri, tmp_path).fetch()] == ["nk-1", "nk-2", "nk-4"]


def test_naukri_rows_become_jobs(tmp_path):
    naukri = board(boards.Naukri, tmp_path)
    rows = fixture("jobspy_naukri.json")
    office, hybrid, cities = (naukri.to_job(rows[n]) for n in (0, 2, 3))
    assert (office.source, office.external_id) == ("naukri", "nk-171026015301")
    assert office.title == "Walk-in || Software Developer"
    assert office.tags == [
        "HTML", "Boot", "Fullstack Development", "Spring", "Spring Boot", "Python", "Angular", "React.js",
    ]
    assert office.department == "Engineering - Software & QA"
    assert (office.salary_min, office.salary_max, office.salary_period) == (400000.0, 500000.0, "year")
    assert (office.remote, hybrid.remote) == (False, False)
    assert cities.location == "Bengaluru, Hyderabad, Pune, India"


def test_naukri_says_which_jobs_are_remote(tmp_path):
    assert board(boards.Naukri, tmp_path).to_job(row(work_from_home_type="Remote")).remote is True


def test_linkedin_searches_cities_only_and_skips_descriptions(tmp_path, jobspy, sleeps):
    board(boards.LinkedIn, tmp_path, keywords=["python", "django"], locations=["remote", "Bengaluru"]).fetch()
    first, second = jobspy.searches
    assert (first["site_name"], first["location"], first["is_remote"]) == ("linkedin", "Bengaluru", False)
    assert (first["results_wanted"], first["fetch_description"]) == (25, False)
    assert second["search_term"] == "django"
    assert sleeps == [30]


def test_linkedin_cannot_search_remote_jobs_only(tmp_path, jobspy):
    with pytest.raises(HirejutsuError, match="Add a city"):
        board(boards.LinkedIn, tmp_path, locations=["remote"]).fetch()
    assert jobspy.searches == []


def test_linkedin_rows_become_jobs(tmp_path):
    linkedin = board(boards.LinkedIn, tmp_path)
    rows = fixture("jobspy_linkedin.json")
    plain, junk = linkedin.to_job(rows[0]), linkedin.to_job(rows[1])
    assert (plain.source, plain.external_id) == ("linkedin", "li-4477707910")
    assert plain.url == "https://www.linkedin.com/jobs/view/4477707910"
    assert (plain.location, plain.description) == ("Bengaluru, Karnataka, India", "")
    assert junk.description.startswith("Job Description\nSenior Backend Engineer (Python) - Bengaluru")


def test_class_junk_is_removed_from_html_descriptions(tmp_path):
    html = '<div>\n svg]:w-[18px] [&amp;&gt;svg]:shrink-0"&gt;\n <p>We build tools.</p>\n</div>'
    assert board(boards.LinkedIn, tmp_path).to_job(row(description=html)).description == "We build tools."


def test_glassdoor_searches_in_the_country(tmp_path, jobspy):
    board(boards.Glassdoor, tmp_path, glassdoor={"country": "UK"}).fetch()
    [search] = jobspy.searches
    assert (search["site_name"], search["country_indeed"], search["results_wanted"]) == ("glassdoor", "UK", 30)
    assert search["fetch_description"] is True


def test_ziprecruiter_search_and_hourly_pay(tmp_path, jobspy):
    jobspy.answers = [fixture("jobspy_zip_recruiter.json")]
    job = board(boards.ZipRecruiter, tmp_path, locations=["San Francisco, CA"]).fetch()[0]
    [search] = jobspy.searches
    assert (search["site_name"], search["location"], search["results_wanted"]) == (
        "zip_recruiter", "San Francisco, CA", 20,
    )
    assert "country_indeed" not in search
    assert (job.source, job.external_id) == ("ziprecruiter", "zr-PtcufjKDFxrTJkmmBOz7fQ")
    assert (job.salary_min, job.salary_max, job.salary_currency, job.salary_period) == (52.5, 69.25, "USD", "hour")
