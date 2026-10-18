import pytest

from hirejutsu import sources
from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.sources import Source
from hirejutsu.store import Store


class Demo(Source):
    name = "demo"

    def fetch(self):
        return [Job("demo", str(n), f"Engineer {n}", "Acme", f"https://x/{n}") for n in range(3)]


class Broken(Source):
    name = "broken"
    defaults = {"enabled": False}

    def fetch(self):
        raise RuntimeError("site is down")


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(sources, "SOURCES", {"demo": Demo, "broken": Broken})
    monkeypatch.setattr(sources.pkgutil, "iter_modules", lambda path: [])


def test_fetch_saves_jobs(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "fetch"]) == 0
    out = capsys.readouterr().out
    assert "demo" in out
    with Store(tmp_path / "hirejutsu.db") as store:
        assert len(store.find_jobs()) == 3


def test_fetch_named_source_reports_error(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "fetch", "--source", "broken"]) == 1
    assert "site is down" in capsys.readouterr().out


def test_fetch_unknown_source(tmp_path, capsys):
    assert main(["--home", str(tmp_path), "fetch", "-s", "nope"]) == 2
    assert "Unknown source" in capsys.readouterr().out


def test_sources_lists_enabled_state_and_last_fetch(tmp_path, capsys):
    main(["--home", str(tmp_path), "fetch"])
    capsys.readouterr()
    assert main(["--home", str(tmp_path), "sources"]) == 0
    lines = capsys.readouterr().out.splitlines()
    demo = next(line for line in lines if "demo" in line)
    broken = next(line for line in lines if "broken" in line)
    assert "yes" in demo and "3" in demo
    assert "no" in broken
