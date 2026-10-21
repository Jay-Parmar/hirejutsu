"""Log files for scheduled runs, which have no console to write to."""

import sys
from datetime import datetime
from pathlib import Path

KEEP = 30


def start(folder: Path) -> None:
    """Point stdout and stderr at today's run log, so output, log records and crashes all land there."""
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    sys.stdout = sys.stderr = (folder / f"run-{now:%Y-%m-%d}.log").open("a", encoding="utf-8", buffering=1)
    print(f"--- {now:%Y-%m-%d %H:%M:%S} ---")
    for old in run_logs(folder)[:-KEEP]:
        old.unlink()


def run_logs(folder: Path) -> list[Path]:
    """Run logs, oldest first."""
    return sorted(folder.glob("run-*.log"))


def latest(folder: Path) -> Path | None:
    logs = run_logs(folder)
    return logs[-1] if logs else None


def tail(path: Path, count: int = 10) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
