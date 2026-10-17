from datetime import datetime, timezone

import pytest
from fakes import FakeClient, board_config, fixture

from hirejutsu.companies import Company
from hirejutsu.sources.breezy import Breezy, salary

API = "https://akt.breezy.hr/json"


def jobs(tmp_path, data, name="AKT"):
    config = board_config(tmp_path, "breezy", {"akt": "AKT"}, search={"max_age_days": 100000})
    client = FakeClient({API: data})
    found = Breezy(config, client).board_jobs(Company("breezy", "akt", name))
    assert client.calls[0][2] == {"verbose": "true"}
    return found


def test_positions_are_mapped(tmp_path):
    first = jobs(tmp_path, fixture("breezy.json"))[0]
    assert first.source == "breezy"
    assert first.external_id == "87f791942b9c"
    assert first.title == "Pick, Pack, Ship, Receiving Warehouse"
    assert first.company == "AKT"
    assert first.url == "https://akt.breezy.hr/p/87f791942b9c-pick-pack-ship-receiving-warehouse"
    assert first.location == "Orlando, FL"
    assert first.remote is False
    assert first.posted_at == datetime(2026, 9, 11, 14, 3, 12, 252000, tzinfo=timezone.utc)
    assert first.description.startswith("Compensation:\n$14-17/hr depending on relevant experience\nJob Description:")
    assert (first.salary_min, first.salary_max, first.salary_currency, first.salary_period) == (15.0, 17.0, "USD", "hour")
    assert first.employment_type == "Full-Time"
    assert first.department == "Production"


def test_company_name_from_the_board(tmp_path):
    assert jobs(tmp_path, fixture("breezy.json"), name="")[0].company == "AKT Enterprises"


@pytest.mark.parametrize("details, flag, expected", [
    ({"value": "hybrid", "label": "Hybrid (Some remote, some in person)"}, True, False),
    ({"value": "remote", "label": "Fully remote, no location restrictions"}, True, True),
    (None, True, True),
    (None, None, None),
])
def test_remote_details_win_over_the_remote_flag(tmp_path, details, flag, expected):
    data = fixture("breezy.json")
    data[0]["location"].update(is_remote=flag, remote_details=details)
    assert jobs(tmp_path, data)[0].remote is expected


@pytest.mark.parametrize("text, expected", [
    ("$75,000 \u2013 $100,000 / year", {"salary_min": 75000.0, "salary_max": 100000.0, "salary_currency": "USD",
                                       "salary_period": "year"}),
    ("\N{EURO SIGN}4,000 / month", {"salary_min": 4000.0, "salary_max": 4000.0, "salary_currency": "EUR",
                                    "salary_period": "month"}),
    ("", {}),
])
def test_salary_text(text, expected):
    assert salary(text) == expected
