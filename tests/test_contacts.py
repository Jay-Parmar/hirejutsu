import logging

import pytest
import requests
from fakes import FakeClient, fixture

from hirejutsu.contacts import (
    SITE_PAGES, Finder, Person, company_domain, people_in, post_contacts, search_links, site_contacts,
)
from hirejutsu.models import Job


def job(description="", **fields):
    values = {"title": "Backend Engineer", "company": "Acme", "url": "https://jobs.lever.co/acme/1"}
    values.update(fields)
    return Job("lever", "1", description=description, **values)


def addresses(contacts):
    return [contact.address for contact in contacts]


def test_addresses_in_the_post_are_stated():
    found = post_contacts(job("Questions? Write to Jane.Doe@acme.com or jobs@acme.com. Apply below."))
    assert [(contact.address, contact.found, contact.confidence) for contact in found] == [
        ("jane.doe@acme.com", "job post", "stated"),
        ("jobs@acme.com", "job post", "stated"),
    ]


def test_spelled_out_addresses_are_found():
    assert addresses(post_contacts(job("Email hiring [at] acme [dot] com or dan(at)acme.io"))) == [
        "hiring@acme.com", "dan@acme.io",
    ]


def test_addresses_for_other_things_are_skipped():
    text = ("no-reply@acme.com privacy@acme.com security@acme.com legal@acme.com abuse@acme.com "
            "support@acme.com accommodations@acme.com jobs@acme.com")
    assert addresses(post_contacts(job(text))) == ["jobs@acme.com"]


def test_each_address_is_listed_once():
    assert addresses(post_contacts(job("jobs@acme.com, or JOBS@acme.com"))) == ["jobs@acme.com"]


def test_a_post_without_addresses_has_no_contacts():
    assert post_contacts(job("Apply on our site.")) == []


def test_a_job_link_on_the_company_site_gives_its_domain():
    assert company_domain(job(url="https://www.acme.com/careers/123")) == "acme.com"


@pytest.mark.parametrize("url", [
    "https://jobs.lever.co/acme/1",
    "https://job-boards.greenhouse.io/acme/jobs/1",
    "https://acme.wd5.myworkdayjobs.com/External/job/1",
    "https://news.ycombinator.com/item?id=1",
])
def test_ats_and_board_links_are_not_the_company_site(url):
    assert company_domain(job(url=url)) == ""


def test_a_board_named_like_the_company_is_still_not_its_site():
    assert company_domain(job(company="Remote", url="https://remoteok.com/remote-jobs/1")) == ""


def test_an_address_in_the_post_gives_the_domain():
    assert company_domain(job("Questions to privacy@careers.acme.co.uk")) == "acme.co.uk"


def test_a_link_in_the_post_gives_the_domain():
    assert company_domain(job("We are Acme (https://acmehq.io/about). Apply below.")) == "acmehq.io"


def test_links_and_addresses_elsewhere_are_not_the_company_site():
    text = "Apply at https://acme.notion.site/jobs or https://docs.google.com/forms/1, or mail jane@gmail.com"
    assert company_domain(job(text)) == ""


def test_legal_words_in_the_company_name_are_ignored():
    assert company_domain(job(company="Acme Robotics, Inc.", url="https://acme-robotics.ai/jobs/1")) == "acme-robotics.ai"


def test_very_short_names_are_too_vague_to_match():
    assert company_domain(job(company="X", url="https://x.com/jobs/1")) == ""


def acme_site():
    return FakeClient({
        "https://acme.com/": "<footer>hello@acme.com</footer>",
        "https://acme.com/careers": fixture("company_careers.html"),
        "https://acme.com/contact": "<p>HR questions: hr@acme.com</p>",
    })


def test_hiring_addresses_on_the_company_site_are_kept():
    found = site_contacts(acme_site(), "acme.com")
    assert [(contact.address, contact.found, contact.confidence) for contact in found] == [
        ("careers@acme.com", "https://acme.com/careers", "site"),
        ("jobs@acme.com", "https://acme.com/careers", "site"),
        ("people-ops@eu.acme.com", "https://acme.com/careers", "site"),
        ("hr@acme.com", "https://acme.com/contact", "site"),
    ]


def test_a_few_pages_are_read_and_missing_ones_skipped():
    client = acme_site()
    site_contacts(client, "acme.com")
    assert [call[1] for call in client.calls] == [
        "https://acme.com/", "https://acme.com/careers", "https://acme.com/jobs", "https://acme.com/contact",
    ]


def test_a_site_that_does_not_answer_is_left_quietly(caplog):
    client = FakeClient({"https://acme.com/": requests.ConnectionError("timed out")})
    with caplog.at_level(logging.DEBUG, logger="hirejutsu.contacts"):
        assert site_contacts(client, "acme.com") == []
    assert len(client.calls) == 1
    assert "https://acme.com/" in caplog.text


def test_contacts_come_surest_first_and_once():
    found = Finder(acme_site()).contacts(job("Mail careers@acme.com or Jane@acme.com.", url="https://acme.com/jobs/1"))
    assert [(contact.address, contact.confidence) for contact in found] == [
        ("careers@acme.com", "stated"),
        ("jane@acme.com", "stated"),
        ("jobs@acme.com", "site"),
        ("people-ops@eu.acme.com", "site"),
        ("hr@acme.com", "site"),
    ]


def test_each_company_site_is_read_once_a_run():
    client = acme_site()
    finder = Finder(client)
    finder.contacts(job(url="https://acme.com/jobs/1"))
    finder.contacts(job(url="https://www.acme.com/jobs/2"))
    assert len(client.calls) == len(SITE_PAGES)


def test_no_site_is_read_without_the_company_domain():
    client = FakeClient()
    assert [contact.address for contact in Finder(client).contacts(job("Mail jobs@gmail.com"))] == ["jobs@gmail.com"]
    assert client.calls == []


def test_search_links_look_for_recruiters_at_the_company():
    web, people = search_links("Acme & Co")
    assert web == ("Web search", "https://www.google.com/search?q=%22Acme%20%26%20Co%22%20recruiter%20OR"
                                 "%20%22talent%20acquisition%22%20site%3Alinkedin.com%2Fin")
    assert people == ("LinkedIn people search",
                      "https://www.linkedin.com/search/results/people/?keywords=Acme%20%26%20Co%20recruiter")


def test_recruiters_are_read_from_linkedin_result_titles():
    assert people_in(fixture("tavily_people.json")["results"], "Acme") == [
        Person("Jane Doe", "Talent Acquisition Partner", "https://in.linkedin.com/in/jane-doe-4a1b2c"),
        Person("Jos\u00e9 Mart\u00ednez", "Senior Technical Recruiter at Acme Inc.",
               "https://es.linkedin.com/in/josemartinez"),
    ]


@pytest.mark.parametrize("title", [
    "Jane Doe - Software Engineer - Acme Robotics | LinkedIn",
    "Jane - Recruiter - Acme Robotics | LinkedIn",
    "Jane Doe - Recruiter - Acme Logistics | LinkedIn",
    "Acme Robotics 2026 - Recruiter - Acme Robotics | LinkedIn",
])
def test_titles_need_a_name_and_a_recruiting_role_at_the_company(title):
    assert people_in([{"title": title, "url": "https://www.linkedin.com/in/someone"}], "Acme Robotics Inc") == []


def test_the_same_title_with_a_recruiting_role_is_kept():
    title = "Jane Doe - Recruiter - Acme Robotics | LinkedIn"
    assert len(people_in([{"title": title, "url": "https://www.linkedin.com/in/someone"}], "Acme Robotics Inc")) == 1
