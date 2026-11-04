from hirejutsu.contacts import post_contacts
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
