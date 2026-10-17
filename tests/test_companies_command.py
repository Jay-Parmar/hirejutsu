from datetime import datetime, timezone

import pytest
import yaml
from fakes import FakeClient, fixture, http_error

from hirejutsu.app import App
from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.store import Store

LEVER = "https://jobs.lever.co/v0/postings"
GREENHOUSE = "https://boards-api.greenhouse.io/v1/boards"


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(App, "client", property(lambda app: fake))
    return fake


def run(home, *args):
    return main(["--home", str(home), "companies", *args])


def user_file(home):
    return yaml.safe_load((home / "companies.yaml").read_text(encoding="utf-8"))


def test_list_counts_companies_per_ats(tmp_path, client, capsys):
    assert run(tmp_path) == 0
    out = capsys.readouterr().out
    assert "448 companies" in out
    assert "greenhouse" in out and "160" in out
    assert "Stripe" in out


def test_list_filters_by_ats_and_text(tmp_path, client, capsys):
    assert run(tmp_path, "list", "--ats", "lever", "--search", "cred") == 0
    out = capsys.readouterr().out
    assert "CRED" in out
    assert "Stripe" not in out


def test_list_shows_companies_added_by_the_user(tmp_path, client, capsys):
    (tmp_path / "config.yaml").write_text("companies:\n  builtin: false\n", encoding="utf-8")
    (tmp_path / "companies.yaml").write_text("personio:\n  tado: tado GmbH\n", encoding="utf-8")
    assert run(tmp_path, "list") == 0
    out = capsys.readouterr().out
    assert "1 company" in out
    assert "tado GmbH" in out and "Stripe" not in out


def test_add_from_a_job_url(tmp_path, client, capsys):
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    assert run(tmp_path, "add", "https://jobs.lever.co/zoox/e8a190f0-7a89-4c11-a6a0-452ff6234749", "--name", "Zoox") == 0
    assert "Added Zoox (lever:zoox) with 3 open jobs" in capsys.readouterr().out
    assert user_file(tmp_path)["lever"] == {"zoox": "Zoox"}


def test_add_takes_the_name_from_the_board(tmp_path, client):
    client.routes[f"{GREENHOUSE}/acme/jobs"] = fixture("greenhouse_jobs.json")
    assert run(tmp_path, "add", "greenhouse:acme") == 0
    assert user_file(tmp_path)["greenhouse"] == {"acme": "Stripe"}


def test_add_without_a_name_uses_the_board(tmp_path, client):
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    assert run(tmp_path, "add", "jobs.lever.co/zoox") == 0
    assert user_file(tmp_path)["lever"] == {"zoox": "zoox"}


def test_add_workday_board_is_named_after_its_tenant(tmp_path, client):
    client.routes["https://acme.wd3.myworkdayjobs.com/wday/cxs/acme/External/jobs"] = fixture("workday.json")
    assert run(tmp_path, "add", "https://acme.wd3.myworkdayjobs.com/en-US/External/job/x_R1") == 0
    assert user_file(tmp_path)["workday"] == [{"name": "acme", "url": "https://acme.wd3.myworkdayjobs.com/External"}]


def test_add_refuses_a_dead_board(tmp_path, client, capsys):
    assert run(tmp_path, "add", "https://jobs.lever.co/nobody") == 2
    assert "lever:nobody is not a live job board" in capsys.readouterr().out
    assert not (tmp_path / "companies.yaml").exists()


def test_add_needs_a_board(tmp_path, client, capsys):
    assert run(tmp_path, "add", "https://example.com/careers") == 2
    assert "greenhouse:stripe" in capsys.readouterr().out


def test_remove_a_builtin_company(tmp_path, client, capsys):
    assert run(tmp_path, "remove", "https://job-boards.greenhouse.io/stripe") == 0
    assert "Removed Stripe (greenhouse:stripe)" in capsys.readouterr().out
    assert user_file(tmp_path)["removed"] == ["greenhouse:stripe"]
    run(tmp_path, "list", "--search", "stripe")
    assert "Stripe" not in capsys.readouterr().out


def test_remove_an_added_company(tmp_path, client):
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    run(tmp_path, "add", "lever:zoox")
    assert run(tmp_path, "remove", "lever:ZOOX") == 0
    assert user_file(tmp_path) == {"removed": ["lever:zoox"]}


def test_remove_unknown_company(tmp_path, client, capsys):
    assert run(tmp_path, "remove", "greenhouse:nobody") == 2
    assert "not in the list" in capsys.readouterr().out


def own_companies_only(home, text):
    (home / "config.yaml").write_text("companies:\n  builtin: false\n", encoding="utf-8")
    (home / "companies.yaml").write_text(text, encoding="utf-8")


def three_lever_boards(home, client):
    own_companies_only(home, "lever:\n  zoox: Zoox\n  gone: Gone\n  flaky: Flaky\n")
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    client.routes[f"{LEVER}/flaky"] = http_error(503)


def test_check_lists_dead_boards(tmp_path, client, capsys):
    three_lever_boards(tmp_path, client)
    assert run(tmp_path, "check") == 1
    out = capsys.readouterr().out
    assert "1 live, 1 dead, 1 could not be checked" in out
    assert "lever:gone" in out and "lever:flaky" in out
    assert "check --prune" in out


def test_check_prune_removes_only_dead_boards(tmp_path, client, capsys):
    three_lever_boards(tmp_path, client)
    assert run(tmp_path, "check", "--ats", "lever", "--prune") == 0
    assert "Stopped fetching 1 dead board" in capsys.readouterr().out
    assert user_file(tmp_path) == {"lever": {"flaky": "Flaky", "zoox": "Zoox"}, "removed": ["lever:gone"]}


def test_check_counts_an_empty_board_as_dead(tmp_path, client, capsys):
    own_companies_only(tmp_path, "smartrecruiters:\n  Nobody: Nobody\n")
    client.routes["https://api.smartrecruiters.com/v1/companies/Nobody/postings"] = {"totalFound": 0, "content": []}
    assert run(tmp_path, "check") == 1
    assert "no open jobs" in capsys.readouterr().out


def test_check_with_every_board_live(tmp_path, client, capsys):
    own_companies_only(tmp_path, "lever:\n  zoox: Zoox\n")
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    assert run(tmp_path, "check") == 0
    assert "1 live, 0 dead, 0 could not be checked" in capsys.readouterr().out


def save_jobs(home, *jobs):
    with Store(home / "hirejutsu.db") as store:
        store.upsert_jobs(jobs, datetime(2026, 10, 17, tzinfo=timezone.utc))


def test_discover_adds_live_boards_linked_from_saved_jobs(tmp_path, client, capsys):
    save_jobs(
        tmp_path,
        Job("remoteok", "1", "Engineer", "Zoox", "https://jobs.lever.co/zoox/e8a190f0-7a89-4c11-a6a0-452ff6234749"),
        Job("remoteok", "2", "Engineer", "Ghost", "https://example.com/2",
            description="Apply at https://jobs.lever.co/ghost/123 or https://job-boards.greenhouse.io/stripe."),
        Job("remoteok", "3", "Engineer", "Acme", "https://example.com/3", description="See https://jobs.lever.co/gone"),
    )
    (tmp_path / "companies.yaml").write_text("removed:\n  - lever:gone\n", encoding="utf-8")
    client.routes[f"{LEVER}/zoox"] = fixture("lever.json")
    assert run(tmp_path, "discover") == 0
    out = capsys.readouterr().out
    assert "Added 1 company" in out
    assert "Zoox (lever:zoox), 3 open jobs" in out
    assert "Skipped lever:ghost" in out
    assert user_file(tmp_path) == {"lever": {"zoox": "Zoox"}, "removed": ["lever:gone"]}
    assert sorted(call[1] for call in client.calls) == [
        "https://jobs.eu.lever.co/v0/postings/ghost", f"{LEVER}/ghost", f"{LEVER}/zoox",
    ]


def test_discover_without_new_boards(tmp_path, client, capsys):
    save_jobs(tmp_path, Job("greenhouse", "1", "Engineer", "Stripe", "https://job-boards.greenhouse.io/stripe/jobs/1"))
    assert run(tmp_path, "discover") == 0
    assert "No new company boards" in capsys.readouterr().out
    assert client.calls == []
