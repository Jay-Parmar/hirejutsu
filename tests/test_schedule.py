import sys
import xml.etree.ElementTree as ET
from datetime import datetime, time
from pathlib import Path

import pytest
from fakes import FakeRun

from hirejutsu import schedule
from hirejutsu.errors import HirejutsuError

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
MORNING = datetime(2026, 10, 17, 8, 0)
MISSING = (1, "", "ERROR: The system cannot find the file specified.\n")


def listing(last_run: str, last_result: str) -> str:
    """The start of schtasks /Query /V /FO LIST output."""
    return rf"""
Folder: \
HostName:                             PC
TaskName:                             \hirejutsu
Next Run Time:                        18-10-2026 09:00:00
Status:                               Ready
Logon Mode:                           Interactive only
Last Run Time:                        {last_run}
Last Result:                          {last_result}
Author:                               PC\jay
"""


@pytest.fixture
def run(monkeypatch):
    fake = FakeRun()
    monkeypatch.setattr(schedule.subprocess, "run", fake)
    return fake


@pytest.fixture
def python(tmp_path, monkeypatch):
    """A fake interpreter for sys.executable, and a fixed Windows user."""
    path = tmp_path / "venv" / "Scripts" / "python.exe"
    path.parent.mkdir(parents=True)
    path.touch()
    monkeypatch.setattr(sys, "executable", str(path))
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "jay")
    return path


def parse(xml: str) -> ET.Element:
    """Read task XML the way schtasks does, from a UTF-16 file."""
    return ET.fromstring(xml.encode("utf-16"))


def find(task: ET.Element, path: str) -> str:
    return task.findtext("/".join(f"t:{part}" for part in path.split("/")), namespaces=NS)


def test_task_runs_every_day_at_the_time(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), now=MORNING))
    assert find(task, "Triggers/CalendarTrigger/StartBoundary") == "2026-10-17T09:00:00"
    assert find(task, "Triggers/CalendarTrigger/ScheduleByDay/DaysInterval") == "1"


def test_task_starts_tomorrow_when_the_time_has_passed(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(7, 30), now=MORNING))
    assert find(task, "Triggers/CalendarTrigger/StartBoundary") == "2026-10-18T07:30:00"


def test_task_on_weekdays(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), weekdays=True, now=MORNING))
    days = task.find("t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek", NS)
    assert [day.tag.split("}")[1] for day in days] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    assert find(task, "Triggers/CalendarTrigger/ScheduleByWeek/WeeksInterval") == "1"


def test_task_settings(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), now=MORNING))
    assert find(task, "Settings/StartWhenAvailable") == "true"
    assert find(task, "Settings/MultipleInstancesPolicy") == "IgnoreNew"
    assert find(task, "Settings/ExecutionTimeLimit") == "PT1H"
    assert find(task, "Settings/DisallowStartIfOnBatteries") == "false"
    assert find(task, "Settings/WakeToRun") == "false"


def test_task_can_wake_the_pc(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), wake=True, now=MORNING))
    assert find(task, "Settings/WakeToRun") == "true"


def test_task_runs_as_the_user_without_admin(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), now=MORNING))
    assert find(task, "Principals/Principal/UserId") == "PC\\jay"
    assert find(task, "Principals/Principal/LogonType") == "InteractiveToken"
    assert find(task, "Principals/Principal/RunLevel") == "LeastPrivilege"


def test_task_runs_pythonw_in_the_data_folder(python, tmp_path):
    pythonw = python.with_name("pythonw.exe")
    pythonw.touch()
    home = tmp_path / "Jobs & Me"
    task = parse(schedule.task_xml(home, time(9, 0), now=MORNING))
    assert find(task, "Actions/Exec/Command") == str(pythonw)
    assert find(task, "Actions/Exec/Arguments") == f'-m hirejutsu --home "{home}" run --log'
    assert find(task, "Actions/Exec/WorkingDirectory") == str(home)


def test_task_uses_python_when_there_is_no_pythonw(python, tmp_path):
    task = parse(schedule.task_xml(tmp_path, time(9, 0), now=MORNING))
    assert find(task, "Actions/Exec/Command") == str(python)


def test_install_registers_the_task_from_a_utf16_file(python, tmp_path, run):
    home = tmp_path / "home"
    schedule.install(home, time(9, 0))
    command = run.calls[0]
    assert command[:5] == ["schtasks", "/Create", "/TN", "hirejutsu", "/XML"]
    assert command[6:] == ["/F"]
    assert not Path(command[5]).exists()
    assert run.task_file.startswith(b"\xff\xfe")
    assert find(ET.fromstring(run.task_file), "Actions/Exec/WorkingDirectory") == str(home)
    assert home.is_dir()


def test_install_reports_schtasks_errors(python, tmp_path, run):
    run.replies["schtasks /Create"] = (1, "", "ERROR: Access is denied.\n")
    with pytest.raises(HirejutsuError, match="Access is denied"):
        schedule.install(tmp_path, time(9, 0))


def test_status_reads_the_task(run):
    run.replies["schtasks /Query"] = (0, listing("17-10-2026 09:00:04", "0"), "")
    assert schedule.status() == [
        ("Next run", "18-10-2026 09:00:00"),
        ("Last run", "17-10-2026 09:00:04"),
        ("Last result", "0"),
    ]
    assert run.calls == [["schtasks", "/Query", "/TN", "hirejutsu", "/V", "/FO", "LIST"]]


def test_status_before_the_first_run(run):
    run.replies["schtasks /Query"] = (0, listing("30-11-1999 00:00:00", "267011"), "")
    assert schedule.status() == [("Next run", "18-10-2026 09:00:00"), ("Last run", "never")]


def test_status_when_not_installed(run):
    run.replies["schtasks /Query"] = MISSING
    assert schedule.status() is None


def test_remove_deletes_the_task(run):
    assert schedule.remove() is True
    assert run.calls[-1] == ["schtasks", "/Delete", "/TN", "hirejutsu", "/F"]


def test_remove_when_not_installed(run):
    run.replies["schtasks /Query"] = MISSING
    assert schedule.remove() is False
    assert [call for call in run.calls if "/Delete" in call] == []
