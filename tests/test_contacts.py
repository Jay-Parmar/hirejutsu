import pytest

from hirejutsu.contacts import company_domain, post_contacts
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
