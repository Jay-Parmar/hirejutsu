import logging
import sys
from datetime import date

import pytest

from hirejutsu import runlog, sources
from hirejutsu.cli import main
from hirejutsu.models import Job
from hirejutsu.sources import Source


class Demo(Source):
    name = "demo"

    def fetch(self):
        return [Job("demo", "1", "Python Engineer", "Acme", "https://x/1", description="python")]


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(sources, "SOURCES", {"demo": Demo})
    monkeypatch.setattr(sources.pkgutil, "iter_modules", lambda path: [])


@pytest.fixture
def home(tmp_path):
    (tmp_path / "resume.txt").write_text("Python developer", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("resume: resume.txt\nprofile:\n  skills: [python]\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def headless(monkeypatch):
    """No stdout or stderr, like pythonw.exe started by the Task Scheduler."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)


def todays_log(folder):
    return folder / f"run-{date.today().isoformat()}.log"


def log_text(folder):
    """Close the run log, as the end of the process would, and read it."""
    sys.stdout.close()
    return todays_log(folder).read_text(encoding="utf-8")


def test_run_log_gets_the_console_output(home, headless):
    assert main(["--home", str(home), "run", "--log"]) == 0
    assert "Python Engineer" in log_text(home / "logs")


def test_run_log_is_appended(home, headless):
    log = todays_log(home / "logs")
    log.parent.mkdir()
    log.write_text("earlier run\n", encoding="utf-8")
    main(["--home", str(home), "run", "--log"])
    text = log_text(home / "logs")
    assert text.startswith("earlier run\n")
    assert "Python Engineer" in text


def test_run_log_gets_config_errors(tmp_path, headless):
    (tmp_path / "config.yaml").write_text("- not a mapping\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "run", "--log"]) == 2
    assert "must contain a mapping" in log_text(tmp_path / "logs")


def test_logging_set_up_after_start_writes_to_the_log(tmp_path, headless):
    runlog.start(tmp_path)
    logging.StreamHandler().handle(logging.makeLogRecord({"msg": "source failed"}))
    sys.stderr.write("Traceback\n")
    text = log_text(tmp_path)
    assert "source failed" in text
    assert "Traceback" in text


def test_run_without_console_or_log(home, headless):
    assert main(["--home", str(home), "run"]) == 0
