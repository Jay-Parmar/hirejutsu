import pytest
from fakes import FakeRun

from hirejutsu import schedule
from hirejutsu.cli import main

MISSING = (1, "", "ERROR: The system cannot find the file specified.\n")
LISTING = """\
Next Run Time:                        18-10-2026 09:00:00
Last Run Time:                        17-10-2026 09:00:04
Last Result:                          0
"""


@pytest.fixture
def run(monkeypatch):
    """A Windows PC whose commands are recorded instead of run."""
    fake = FakeRun()
    monkeypatch.setattr(schedule.subprocess, "run", fake)
    monkeypatch.setattr(schedule, "WINDOWS", True)
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "jay")
    return fake


def test_install_defaults_to_nine_every_day(tmp_path, run, capsys):
    assert main(["--home", str(tmp_path), "schedule", "install"]) == 0
    xml = run.task_file.decode("utf-16")
    assert "T09:00:00</StartBoundary>" in xml
    assert "<ScheduleByDay>" in xml
    assert "every day at 09:00" in capsys.readouterr().out


def test_install_at_a_time_on_weekdays(tmp_path, run, capsys):
    assert main(["--home", str(tmp_path), "schedule", "install", "--time", "7:30", "--weekdays"]) == 0
    xml = run.task_file.decode("utf-16")
    assert "T07:30:00</StartBoundary>" in xml
    assert "<Friday />" in xml
    assert "every weekday at 07:30" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["25:00", "09:60", "9am", ""])
def test_install_rejects_a_bad_time(tmp_path, run, capsys, value):
    with pytest.raises(SystemExit) as exc:
        main(["--home", str(tmp_path), "schedule", "install", "--time", value])
    assert exc.value.code == 2
    assert "HH:MM" in capsys.readouterr().err
    assert run.calls == []


def test_install_failure_is_reported(tmp_path, run, capsys):
    run.replies["schtasks /Create"] = (1, "", "ERROR: Access is denied.\n")
    assert main(["--home", str(tmp_path), "schedule", "install"]) == 2
    assert "Access is denied" in capsys.readouterr().out


def test_show_prints_the_task_without_registering_it(tmp_path, run, capsys):
    assert main(["--home", str(tmp_path), "schedule", "show", "--wake"]) == 0
    assert "<WakeToRun>true</WakeToRun>" in capsys.readouterr().out
    assert run.calls == []


def test_show_prints_the_cron_line_on_macos_and_linux(tmp_path, run, capsys, monkeypatch):
    monkeypatch.setattr(schedule, "WINDOWS", False)
    assert main(["--home", str(tmp_path), "schedule", "show", "--weekdays"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("0 9 * * 1-5 ")
    assert out.rstrip().endswith("run --log # hirejutsu")
    assert run.calls == []


def test_status_shows_the_next_and_last_run(tmp_path, run, capsys):
    run.replies["schtasks /Query"] = (0, LISTING, "")
    assert main(["--home", str(tmp_path), "schedule", "status"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Next run    18-10-2026 09:00:00",
        "Last run    17-10-2026 09:00:04",
        "Last result 0",
    ]


def test_status_shows_the_end_of_the_latest_run_log(tmp_path, run, capsys):
    run.replies["schtasks /Query"] = (0, LISTING, "")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "run-2026-10-16.log").write_text("older run\n", encoding="utf-8")
    (logs / "run-2026-10-17.log").write_text(
        "--- 2026-10-17 09:00:04 ---\nWARNING hirejutsu.pipeline: lever failed: [Errno 11001] getaddrinfo failed\n",
        encoding="utf-8",
    )
    assert main(["--home", str(tmp_path), "schedule", "status"]) == 0
    out = capsys.readouterr().out
    assert "run-2026-10-17.log" in out
    assert "lever failed: [Errno 11001] getaddrinfo failed" in out
    assert "older run" not in out


def test_status_when_not_installed(tmp_path, run, capsys):
    run.replies["schtasks /Query"] = MISSING
    assert main(["--home", str(tmp_path), "schedule", "status"]) == 1
    assert "not scheduled" in capsys.readouterr().out


def test_remove(tmp_path, run, capsys):
    assert main(["--home", str(tmp_path), "schedule", "remove"]) == 0
    assert run.calls[-1][:2] == ["schtasks", "/Delete"]
    assert "no longer" in capsys.readouterr().out


def test_remove_when_not_installed(tmp_path, run, capsys):
    run.replies["schtasks /Query"] = MISSING
    assert main(["--home", str(tmp_path), "schedule", "remove"]) == 0
    assert "not scheduled" in capsys.readouterr().out
