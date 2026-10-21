from hirejutsu.models import Job


def make_job(**kwargs):
    fields = {"source": "lever", "external_id": "abc", "title": "Backend Engineer", "company": "Acme", "url": "https://x"}
    fields.update(kwargs)
    return Job(**fields)


def test_key_combines_source_and_id():
    assert make_job().key == "lever:abc"


def test_fingerprint_ignores_case_and_punctuation():
    a = make_job(company="Acme, Inc.", title="Senior Backend Engineer (Python)")
    b = make_job(source="remoteok", company="acme inc", title="Senior Backend Engineer - Python")
    assert a.fingerprint == b.fingerprint


def test_fingerprint_differs_by_title():
    assert make_job(title="Backend Engineer").fingerprint != make_job(title="Frontend Engineer").fingerprint
