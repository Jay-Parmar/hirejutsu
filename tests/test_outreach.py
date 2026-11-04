import html
from datetime import date
from pathlib import Path

import pytest

from hirejutsu import outreach
from hirejutsu.applicant import Applicant
from hirejutsu.config import Config
from hirejutsu.contacts import Contact, Person, guesses
from hirejutsu.models import Job, Match, Profile

DAY = date(2026, 11, 4)
SKILLS = "Skills: Python, Django, PostgreSQL (5 of 20)"
ASHA = Applicant(
    first_name="Asha", last_name="Rao", phone="9876543210", phone_code="+91",
    links={"linkedin": "https://www.linkedin.com/in/asha", "github": "https://github.com/asha"},
)


def settings(**values):
    return outreach.load_settings(Config({"outreach": values}, Path(".")))


def pick(source="greenhouse", reasons=(SKILLS,), **fields):
    values = {"title": "Backend Engineer", "company": "Acme", "url": "https://jobs.acme.com/1"}
    values.update(fields)
    return Match(Job(source, "1", **values, id=12), 0.8, list(reasons))


def draft(match=None, years=6, applicant=ASHA, contacts=(), **values):
    return outreach.draft(match or pick(), list(contacts), Profile(years=years), applicant, settings(**values))


def test_board_picks_are_left_out_by_default():
    picks = [pick("greenhouse"), pick("remoteok"), pick("hackernews"), pick("linkedin"), pick("workday")]
    kept = outreach.picks_to_write(picks, settings())
    assert [match.job.source for match in kept] == ["greenhouse", "hackernews", "workday"]


def test_sources_setting_changes_the_list():
    kept = outreach.picks_to_write([pick("greenhouse"), pick("remoteok")], settings(sources=["remoteok"]))
    assert [match.job.source for match in kept] == ["remoteok"]


def test_the_draft_says_where_you_saw_the_role_and_why_you_fit():
    email = draft()
    assert email.subject == "Backend Engineer role at Acme"
    assert outreach.email_text(email) == (
        "Hi Acme team,\n"
        "\n"
        "I saw the Backend Engineer role at Acme (https://jobs.acme.com/1) and wanted to write to you directly.\n"
        "I have 6 years of experience, much of it with Python, Django and PostgreSQL, which the role asks for.\n"
        "Could you pass my profile to the hiring manager, or would you have time for a short call?\n"
        "Thank you for your time.\n"
        "\n"
        "Best regards,\n"
        "Asha Rao\n"
        "+91 9876543210\n"
        "https://www.linkedin.com/in/asha\n"
        "https://github.com/asha"
    )


def test_the_pitch_gets_a_line_of_its_own():
    email = draft(pitch="Last year I cut our API response times in half.")
    assert "which the role asks for.\nLast year I cut our API response times in half.\nCould you" in email.body


@pytest.mark.parametrize("reasons, years, line", [
    ([SKILLS], 1, "I have 1 year of experience, much of it with Python, Django and PostgreSQL, which"),
    (["Skills: Go (1 of 9)"], 4.5, "I have 4.5 years of experience, much of it with Go, which the role asks for."),
    ([SKILLS], None, "I work with Python, Django and PostgreSQL, which the role asks for."),
    (["AI: Strong fit", "Posted today"], 6, "I have 6 years of experience and would like to bring it to Acme."),
])
def test_the_fit_line_uses_what_is_known(reasons, years, line):
    assert line in draft(pick(reasons=reasons), years=years).body


def test_without_skills_or_years_the_fit_line_is_left_out():
    assert draft(pick(reasons=[]), years=None).body.splitlines()[1].startswith("Could you pass my profile")


def test_a_title_that_already_says_roles_is_not_doubled():
    email = draft(pick(title="Open roles"))
    assert email.subject == "Open roles at Acme"
    assert email.body.startswith("I saw the Open roles at Acme (")


def test_the_sign_off_has_what_the_applicant_details_have():
    assert draft(applicant=Applicant(first_name="Asha", phone="9876543210")).signature == "Best regards,\nAsha\n9876543210"
    assert draft(applicant=Applicant()).signature == "Best regards,"


def test_mailto_link_fills_in_the_address_subject_and_text():
    link = outreach.mailto("jobs@acme.com", "Backend Engineer role at Acme", "Hi Acme team,\n\nYes & no")
    assert link == (
        "mailto:jobs@acme.com?subject=Backend%20Engineer%20role%20at%20Acme"
        "&body=Hi%20Acme%20team%2C%0D%0A%0D%0AYes%20%26%20no"
    )


def test_mailto_link_without_an_address_leaves_the_to_line_empty():
    assert outreach.mailto("", "Hello", "Hi") == "mailto:?subject=Hello&body=Hi"


def test_markdown_lists_each_job_with_its_contacts_and_draft():
    email = draft(contacts=[Contact("jobs@acme.com", "job post", "stated"),
                            Contact("careers@acme.com", "https://acme.com/careers", "site")])
    text = outreach.markdown([email], DAY)
    assert text.startswith("# Recruiter emails for 2026-11-04\n")
    assert "## 1. Backend Engineer at Acme\nhttps://jobs.acme.com/1 | via Greenhouse career pages | id 12\n" in text
    assert "- jobs@acme.com (stated): job post\n- careers@acme.com (site): https://acme.com/careers\n" in text
    assert "```\nSubject: Backend Engineer role at Acme\n\nHi Acme team,\n\nI saw the Backend Engineer role" in text
    assert f"[Write email]({outreach.mailto('jobs@acme.com', email.subject, outreach.email_text(email))})" in text
    assert "After sending it: `hirejutsu outreach sent 12 jobs@acme.com`" in text


def test_markdown_without_contacts_leaves_the_address_to_you():
    text = outreach.markdown([draft()], DAY)
    assert "- Nobody found." in text
    assert "[Write email](mailto:?subject=" in text
    assert "`hirejutsu outreach sent 12 <address>`" in text


def test_html_page_shows_each_job_with_its_contacts_and_draft():
    email = draft(contacts=[Contact("jobs@acme.com", "job post", "stated"),
                            Contact("careers@acme.com", "https://acme.com/careers", "site")])
    page = outreach.html_page([email], DAY)
    assert "<title>Recruiter emails for 2026-11-04</title>" in page
    assert "Wednesday, 4 November 2026" in page
    assert "1 job to write about" in page
    assert '<a href="https://jobs.acme.com/1" target="_blank" rel="noopener noreferrer">Backend Engineer</a>' in page
    assert ">Acme</p>" in page
    assert "<span>via Greenhouse career pages</span><span>id 12</span>" in page
    assert '<span class="sure">stated</span> <span class="found">job post</span>' in page
    assert '<span class="sure">site</span> <span class="found">https://acme.com/careers</span>' in page
    assert '<pre class="draft">Subject: Backend Engineer role at Acme' in page
    write = html.escape(outreach.mailto("jobs@acme.com", email.subject, outreach.email_text(email)))
    assert f'<a class="open" href="{write}">Write email</a>' in page
    other = html.escape(outreach.mailto("careers@acme.com", email.subject, outreach.email_text(email)))
    assert f'<a href="{other}">careers@acme.com</a>' in page
    assert 'data-command="hirejutsu outreach sent 12 jobs@acme.com"' in page


def test_html_page_counts_the_jobs():
    assert "2 jobs to write about" in outreach.html_page([draft(), draft()], DAY)


def test_html_page_without_contacts_says_so():
    assert "<li>Nobody found.</li>" in outreach.html_page([draft()], DAY)


def test_html_page_escapes_job_text():
    nasty = pick(title='<script>alert("hi")</script>', company="Fish & Chips", url='https://x/a?b=1&c="2"')
    page = outreach.html_page([draft(nasty, contacts=[Contact("a@b.com", "<b>post</b>", "stated")])], DAY)
    assert "<script>alert" not in page
    assert "&lt;script&gt;alert(&quot;hi&quot;)&lt;/script&gt;" in page
    assert "Fish &amp; Chips" in page
    assert "&lt;b&gt;post&lt;/b&gt;" in page
    assert 'href="https://x/a?b=1&amp;c=&quot;2&quot;"' in page


def test_html_page_loads_nothing_from_the_internet():
    page = outreach.html_page([draft()], DAY)
    for loads in ("src=", "url(", "<link", "@import"):
        assert loads not in page


def test_html_page_links_jobs_only_to_web_addresses():
    assert 'href="javascript:' not in outreach.html_page([draft(pick(url="javascript:alert(1)"))], DAY)


def test_drafts_are_saved_next_to_the_daily_reports(tmp_path):
    paths = outreach.save_drafts([draft()], Config({}, tmp_path), DAY)
    assert paths == [tmp_path / "reports" / "outreach-2026-11-04.md", tmp_path / "reports" / "outreach-2026-11-04.html"]
    assert paths[0].read_text(encoding="utf-8").startswith("# Recruiter emails for 2026-11-04")
    assert paths[1].read_text(encoding="utf-8").startswith("<!doctype html>")


def test_both_pages_link_to_searches_for_finding_someone_yourself():
    text = outreach.markdown([draft()], DAY)
    assert "Find someone yourself: [Web search](https://www.google.com/search?q=%22Acme%22%20recruiter" in text
    assert " | [LinkedIn people search](https://www.linkedin.com/search/results/people/?keywords=Acme%20recruiter)" in text
    page = outreach.html_page([draft()], DAY)
    assert ('<a href="https://www.linkedin.com/search/results/people/?keywords=Acme%20recruiter" target="_blank" '
            'rel="noopener noreferrer">LinkedIn people search</a>') in page


def test_a_known_person_is_greeted_by_first_name():
    careers = Contact("careers@acme.com", "https://acme.com/careers", "site")
    jane = Contact("jane.doe@acme.com", "Jane Doe, Talent Acquisition Partner", "guess", "Jane Doe")
    assert outreach.email_text(draft(contacts=[jane])).startswith("Hi Jane,\n\nI saw the")
    email = draft(contacts=[careers, jane])
    assert outreach.email_text(email).startswith("Hi Acme team,\n")
    assert outreach.email_text(email, jane).startswith("Hi Jane,\n")
    page = outreach.html_page([email], DAY)
    assert 'href="mailto:jane.doe@acme.com?subject=Backend%20Engineer%20role%20at%20Acme&amp;body=Hi%20Jane%2C' in page


def test_contacts_found_together_share_a_line():
    contacts = [Contact("careers@acme.com", "https://acme.com/careers", "site"),
                Contact("jobs@acme.com", "https://acme.com/careers", "site"),
                *guesses(Person("Jane Doe", "Recruiter", "https://www.linkedin.com/in/jane"), "acme.com")]
    text = outreach.markdown([draft(contacts=contacts)], DAY)
    assert "\n- careers@acme.com, jobs@acme.com (site): https://acme.com/careers\n" in text
    assert "\n- jane.doe@acme.com, jane@acme.com, janedoe@acme.com, jdoe@acme.com (guess): Jane Doe, Recruiter\n" in text
    page = outreach.html_page([draft(contacts=contacts)], DAY)
    assert page.count('<li><a href="mailto:') == 2
    assert page.count('href="mailto:') == len(contacts) + 1
