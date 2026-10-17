import pytest
from fakes import FakeClient

from hirejutsu.app import App
from hirejutsu.cli import main


@pytest.fixture
def client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(App, "client", property(lambda app: fake))
    return fake


def run(home, *args):
    return main(["--home", str(home), "companies", *args])


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
