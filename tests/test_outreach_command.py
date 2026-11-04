from datetime import date, datetime, timezone

import pytest
from fakes import CLAUDE_URL, FakeClient, claude_reply, fixture

from hirejutsu import ai
from hirejutsu.app import App
from hirejutsu.cli import main
from hirejutsu.commands import report as report_command
from hirejutsu.models import Job, Match
from hirejutsu.store import Store

DAY = date(2026, 11, 4)
ACME = Job("greenhouse", "1", "Backend Engineer", "Acme", "https://acme.com/jobs/1", description="Mail jobs@acme.com")
GLOBEX = Job("remoteok", "2", "Python Developer", "Globex", "https://remoteok.com/remote-jobs/2")
INITECH = Job("lever", "3", "Platform Engineer", "Initech", "https://jobs.lever.co/initech/3")
TAVILY = "https://api.tavily.com/search"


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(App, "client", property(lambda app: fake))
    return fake


@pytest.fixture
def home(tmp_path):
    (tmp_path / "resume.txt").write_text("Backend Engineer, Acme, 2018 - 2024\nPython developer", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\n", encoding="utf-8")
    (tmp_path / "applicant.yaml").write_text("first_name: Asha\nlast_name: Rao\nphone: 9876543210\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(report_command, "open_url", urls.append)
    return urls


def save_picks(home, day, *jobs):
    with Store(home / "hirejutsu.db") as store:
        store.upsert_jobs(jobs, datetime.now(timezone.utc))
        store.record_picks(day, [Match(job, 0.5, ["Skills: Python (1 of 3)"]) for job in store.find_jobs()])


def run(home, *args):
    return main(["--home", str(home), "outreach", *args])


def saved(home, day, suffix="md"):
    return (home / "reports" / f"outreach-{day.isoformat()}.{suffix}").read_text(encoding="utf-8")


def test_outreach_drafts_emails_about_todays_career_page_picks(home, client, capsys):
    today = datetime.now().astimezone().date()
    save_picks(home, today, ACME, GLOBEX)
    assert run(home) == 0
    out = capsys.readouterr().out
    assert "Left out 1 of 2 picks" in out
    assert "jobs@acme.com" in out
    assert f"outreach-{today.isoformat()}.html" in out
    text = saved(home, today)
    assert "## 1. Backend Engineer at Acme" in text
    assert "Globex" not in text
    assert "Hi Acme team," in text
    assert "Asha Rao\n9876543210" in text
    page = saved(home, today, "html")
    assert 'href="mailto:jobs@acme.com?subject=Backend%20Engineer%20role%20at%20Acme' in page
    assert "Globex" not in page


def test_outreach_reads_the_company_site(home, client):
    client.routes["https://acme.com/careers"] = "<a href='mailto:careers@acme.com'>Write to us</a>"
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert "- careers@acme.com (site): https://acme.com/careers" in saved(home, DAY)


def test_outreach_for_a_day_without_picks(home, client, capsys):
    assert run(home, "--day", "2026-11-04") == 1
    assert "No picks for 2026-11-04" in capsys.readouterr().out


def test_outreach_when_every_pick_is_from_a_job_board(home, client, capsys):
    save_picks(home, DAY, GLOBEX)
    assert run(home, "--day", "2026-11-04") == 0
    assert "No picks to write about" in capsys.readouterr().out
    assert not (home / "reports").exists()


def test_n_limits_the_drafts(home, client):
    save_picks(home, DAY, ACME, INITECH)
    assert run(home, "--day", "2026-11-04", "-n", "1") == 0
    text = saved(home, DAY)
    assert "Acme" in text
    assert "Initech" not in text


def test_open_shows_the_html_page(home, client, opened):
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04", "--open") == 0
    assert opened == [(home / "reports" / "outreach-2026-11-04.html").as_uri()]


def test_missing_applicant_details_are_pointed_out(home, client, capsys):
    (home / "applicant.yaml").unlink()
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert "hirejutsu applicant --edit" in capsys.readouterr().out


def notes(home, job_id):
    with Store(home / "hirejutsu.db") as store:
        return [note for _, _, note in store.history(job_id)]


def test_sent_records_the_email_with_the_job(home, capsys):
    save_picks(home, DAY, ACME)
    assert run(home, "sent", "1", "jobs@acme.com") == 0
    assert "Noted that you emailed jobs@acme.com about job 1: Backend Engineer at Acme" in capsys.readouterr().out
    assert notes(home, 1) == ["Emailed jobs@acme.com"]
    with Store(home / "hirejutsu.db") as store:
        assert store.get_job(1).status == "new"


def test_sent_takes_todays_pick_numbers_and_several_addresses(home):
    save_picks(home, datetime.now().astimezone().date(), ACME, INITECH)
    assert run(home, "sent", "-t", "2", "jane@initech.com", "jobs@initech.com") == 0
    assert notes(home, 2) == ["Emailed jane@initech.com, jobs@initech.com"]


def test_sent_needs_email_addresses(home, capsys):
    save_picks(home, DAY, ACME)
    assert run(home, "sent", "1", "Jane") == 2
    assert "Jane is not an email address" in capsys.readouterr().out
    assert notes(home, 1) == []


def test_sent_for_an_unknown_job(home, capsys):
    assert run(home, "sent", "99", "jobs@acme.com") == 1
    assert "No job with id 99" in capsys.readouterr().out


def test_jobs_you_emailed_about_are_left_out_next_time(home, client, capsys):
    save_picks(home, DAY, ACME, INITECH)
    assert run(home, "sent", "1", "jobs@acme.com") == 0
    assert run(home, "--day", "2026-11-04") == 0
    assert "Left out 1 you already emailed about" in capsys.readouterr().out
    text = saved(home, DAY)
    assert "Backend Engineer at Acme" not in text
    assert "## 1. Platform Engineer at Initech" in text


def search_with_tavily(home):
    (home / "config.yaml").write_text("resume: resume.txt\noutreach:\n  search: tavily\n", encoding="utf-8")


def searched(client):
    return [call for call in client.calls if call[1] == TAVILY]


def test_recruiter_search_uses_the_key_from_the_environment(home, client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    search_with_tavily(home)
    client.routes[TAVILY] = fixture("tavily_people.json")
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    text = saved(home, DAY)
    assert "jane.doe@acme.com, jane@acme.com, janedoe@acme.com, jdoe@acme.com (guess)" in text
    assert "Recruiters found: [Jane Doe, Talent Acquisition Partner](https://in.linkedin.com/in/jane-doe-4a1b2c)" in text


def test_recruiter_search_without_its_key_is_skipped(home, client, monkeypatch, capsys):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    search_with_tavily(home)
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert "TAVILY_API_KEY is not set" in capsys.readouterr().out
    assert searched(client) == []


def test_recruiter_search_is_off_by_default(home, client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert searched(client) == []


def test_an_unknown_search_api_is_an_error(home, client, capsys):
    (home / "config.yaml").write_text("resume: resume.txt\noutreach:\n  search: bing\n", encoding="utf-8")
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 2
    assert "Unknown outreach.search 'bing'" in capsys.readouterr().out


def fake_ai(monkeypatch, answer=None):
    client = FakeClient({CLAUDE_URL: answer} if answer else {})
    monkeypatch.setattr(ai, "make_client", lambda settings: client)
    return client


def test_the_ai_rewrites_the_drafts_when_outreach_ai_is_on(home, client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (home / "config.yaml").write_text("resume: resume.txt\noutreach:\n  ai: true\n", encoding="utf-8")
    ai_client = fake_ai(monkeypatch, claude_reply("I saw your Backend Engineer role. My Python work fits it."))
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert "Hi Acme team,\n\nI saw your Backend Engineer role. My Python work fits it.\n\nBest regards," in saved(home, DAY)
    prompt = ai_client.calls[0][3]["messages"][0]["content"]
    assert "Python developer" in prompt
    assert "Could you pass my profile to the hiring manager" in prompt


def test_the_drafts_keep_the_template_when_the_ai_fails(home, client, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (home / "config.yaml").write_text("resume: resume.txt\noutreach:\n  ai: true\n", encoding="utf-8")
    fake_ai(monkeypatch)
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out
    assert "Could you pass my profile to the hiring manager" in saved(home, DAY)


def test_the_ai_is_not_asked_by_default(home, client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    ai_client = fake_ai(monkeypatch, claude_reply("Rewritten."))
    save_picks(home, DAY, ACME)
    assert run(home, "--day", "2026-11-04") == 0
    assert ai_client.calls == []


def test_the_table_shows_whole_addresses_in_a_narrow_terminal(home, client, capsys):
    long = Job("greenhouse", "4", "Senior Staff Backend Platform Engineer, Payments Infrastructure", "BrowserStack",
               "https://www.browserstack.com/careers/4", description="Mail talent.acquisition@browserstack.com")
    save_picks(home, DAY, long)
    assert run(home, "--day", "2026-11-04") == 0
    assert "talent.acquisition@browserstack.com" in capsys.readouterr().out
