from datetime import datetime, timezone

from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.personio import Personio

FEED = "https://tado.jobs.personio.de/xml"


def jobs(tmp_path, body, name="Tado"):
    config = board_config(tmp_path, "personio", {"tado": "Tado"}, search={"max_age_days": 100000})
    return Personio(config, FakeClient({FEED: body})).board_jobs(Company("personio", "tado", name))


def test_positions_are_mapped(tmp_path):
    first, second = jobs(tmp_path, fixture("personio.xml"))
    assert first.source == "personio"
    assert first.external_id == "2502124"
    assert first.title == "Team Lead Accounting (m/f/d)"
    assert first.company == "Tado"
    assert first.url == "https://tado.jobs.personio.de/job/2502124"
    assert first.location == "Germany - Munich"
    assert first.remote is None
    assert first.posted_at == datetime(2026, 1, 22, 9, 48, 25, tzinfo=timezone.utc)
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (
        80000.0, 100000.0, "EUR", "year",
    )
    assert first.employment_type == "permanent, full-time"
    assert first.department == "Finance"
    assert first.tags[:4] == ["People & Culture", "experienced", "Accounting", "Finance"]
    assert first.description == ""
    assert second.salary_min is None
    assert second.employment_type == "intern, part-time"


def test_description_sections_keep_their_names(tmp_path):
    second = jobs(tmp_path, fixture("personio.xml"))[1]
    assert second.description.startswith(
        "Was erwartet dich bei uns\nStandort: M\xfcnchen | Start: ab Dezember 2026 | 20 Stunden/Woche\n"
        "- Ein motiviertes Team"
    )
    assert "\nWarum du gut zu uns passt:\n- Laufendes Studium" in second.description


def test_feed_without_charset_is_read_as_utf8(tmp_path):
    body = (
        "<workzag-jobs><position><id>1</id><subcompany>tado GmbH</subcompany><office>M\xfcnchen</office>"
        "<name>Entwickler:in M\xfcnchen</name><createdAt>2026-10-13T09:59:49+00:00</createdAt></position>"
        "</workzag-jobs>"
    ).encode("utf-8")
    job = jobs(tmp_path, body, name="")[0]
    assert job.title == "Entwickler:in M\xfcnchen"
    assert job.location == "M\xfcnchen"
    assert job.company == "tado GmbH"
