from pathlib import Path

import pytest

from hirejutsu import outreach
from hirejutsu.applicant import Applicant
from hirejutsu.config import Config
from hirejutsu.models import Job, Match, Profile

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


def draft(match=None, years=6, applicant=ASHA, **values):
    return outreach.draft(match or pick(), [], Profile(years=years), applicant, settings(**values))


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
