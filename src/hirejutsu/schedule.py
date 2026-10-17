"""Running hirejutsu every morning with the Windows Task Scheduler."""

import os
import subprocess
import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from .errors import HirejutsuError

TASK_NAME = "hirejutsu"
NOT_RUN_YET = "267011"

TASK_XML = """\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Fetches new jobs and picks the best matches for your resume.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
{schedule}
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{user}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>{wake}</WakeToRun>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{folder}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

EVERY_DAY = """\
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>"""

WEEKDAYS = """\
      <ScheduleByWeek>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>"""


def interpreter() -> Path:
    """The running Python, as pythonw.exe when there is one so no console window opens."""
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else python


def first_run(at: time, now: datetime) -> datetime:
    # A start time already past would count as a missed run and fire as soon as the task is saved.
    start = datetime.combine(now.date(), at)
    return start if start > now else start + timedelta(days=1)


def task_xml(home: Path, at: time, weekdays: bool = False, wake: bool = False, now: datetime | None = None) -> str:
    """Task Scheduler definition of the daily run."""
    return TASK_XML.format(
        start=first_run(at, now or datetime.now()).isoformat(),
        schedule=WEEKDAYS if weekdays else EVERY_DAY,
        user=escape(f"{os.environ['USERDOMAIN']}\\{os.environ['USERNAME']}"),
        wake="true" if wake else "false",
        command=escape(str(interpreter())),
        arguments=escape(f'-m hirejutsu --home "{home}" run --log'),
        folder=escape(str(home)),
    )


def install(home: Path, at: time, weekdays: bool = False, wake: bool = False) -> None:
    """Register the daily run, replacing an earlier one."""
    # The task cannot start in a working directory that does not exist.
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "hirejutsu.xml"
        path.write_text(task_xml(home, at, weekdays, wake), encoding="utf-16")
        _schtasks("/Create", "/TN", TASK_NAME, "/XML", str(path), "/F")


def remove() -> bool:
    """Unregister the daily run. False when there was none."""
    if _schtasks("/Query", "/TN", TASK_NAME, check=False).returncode:
        return False
    _schtasks("/Delete", "/TN", TASK_NAME, "/F")
    return True


def status() -> list[tuple[str, str]] | None:
    """Next and last run of the daily run, or None when it is not installed."""
    result = _schtasks("/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST", check=False)
    if result.returncode:
        return None
    fields = {}
    for line in result.stdout.splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    rows = [("Next run", fields.get("Next Run Time", "?"))]
    # Before the first run Windows reports a last run in 1999.
    if fields.get("Last Result") == NOT_RUN_YET:
        return rows + [("Last run", "never")]
    return rows + [("Last run", fields.get("Last Run Time", "?")), ("Last result", fields.get("Last Result", "?"))]


def _schtasks(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    # Its messages use the console code page, which differs between PCs.
    result = subprocess.run(["schtasks", *args], capture_output=True, text=True, errors="replace")
    if check and result.returncode:
        raise HirejutsuError(f"schtasks {args[0]} failed: {result.stderr.strip()}")
    return result
