"""SQLite storage for jobs, daily picks and fetch history."""

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from .errors import HirejutsuError
from .models import Job, Match

STATUSES = ("new", "saved", "applied", "interview", "offer", "rejected", "skipped")

JOB_FIELDS = (
    "source", "external_id", "title", "company", "url", "location", "remote", "description",
    "posted_at", "salary_min", "salary_max", "salary_currency", "salary_period",
    "employment_type", "department", "tags",
)

MIGRATIONS = [
    """
    CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        source TEXT NOT NULL,
        external_id TEXT NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        url TEXT NOT NULL,
        location TEXT NOT NULL DEFAULT '',
        remote INTEGER,
        description TEXT NOT NULL DEFAULT '',
        posted_at TEXT,
        salary_min REAL,
        salary_max REAL,
        salary_currency TEXT NOT NULL DEFAULT '',
        salary_period TEXT NOT NULL DEFAULT '',
        employment_type TEXT NOT NULL DEFAULT '',
        department TEXT NOT NULL DEFAULT '',
        tags TEXT NOT NULL DEFAULT '[]',
        fingerprint TEXT NOT NULL,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        status_at TEXT,
        note TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX jobs_fingerprint ON jobs (fingerprint);
    CREATE INDEX jobs_last_seen ON jobs (last_seen);
    CREATE TABLE picks (
        day TEXT NOT NULL,
        job_id INTEGER NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
        rank INTEGER NOT NULL,
        score REAL NOT NULL,
        reasons TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (day, job_id)
    );
    CREATE TABLE fetches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        started_at TEXT NOT NULL,
        seconds REAL NOT NULL,
        found INTEGER NOT NULL,
        added INTEGER NOT NULL,
        error TEXT NOT NULL DEFAULT ''
    );
    """,
    """
    -- One row per status change or note. status is NULL for a note on its own.
    CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
        status TEXT,
        at TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX events_job_id ON events (job_id);
    INSERT INTO events (job_id, status, at, note)
        SELECT id, status, status_at, note FROM jobs WHERE status_at IS NOT NULL;
    """,
]


def _to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _to_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.conn:
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version = {number}")

    def upsert_jobs(self, jobs: Iterable[Job], seen_at: datetime) -> int:
        """Insert new jobs and refresh known ones. Returns how many were new."""
        seen = _to_text(seen_at)
        added = 0
        with self.conn:
            for job in jobs:
                values = self._job_values(job)
                cursor = self.conn.execute(
                    f"UPDATE jobs SET {', '.join(f'{name} = ?' for name in values)}, last_seen = ? WHERE key = ?",
                    [*values.values(), seen, job.key],
                )
                if cursor.rowcount:
                    continue
                self.conn.execute(
                    f"INSERT INTO jobs (key, {', '.join(values)}, first_seen, last_seen) "
                    f"VALUES (?, {', '.join('?' for _ in values)}, ?, ?)",
                    [job.key, *values.values(), seen, seen],
                )
                added += 1
        return added

    @staticmethod
    def _job_values(job: Job) -> dict:
        values = {name: getattr(job, name) for name in JOB_FIELDS}
        values["posted_at"] = _to_text(job.posted_at)
        values["remote"] = None if job.remote is None else int(job.remote)
        values["tags"] = json.dumps(job.tags)
        values["fingerprint"] = job.fingerprint
        return values

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        values = {name: row[name] for name in JOB_FIELDS}
        values["posted_at"] = _to_datetime(row["posted_at"])
        values["remote"] = None if row["remote"] is None else bool(row["remote"])
        values["tags"] = json.loads(row["tags"])
        return Job(
            **values,
            id=row["id"],
            status=row["status"],
            status_at=_to_datetime(row["status_at"]),
            note=row["note"],
            first_seen=_to_datetime(row["first_seen"]),
            last_seen=_to_datetime(row["last_seen"]),
        )

    def get_job(self, job_id: int) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def find_jobs(self, statuses: Iterable[str] | None = None, seen_since: datetime | None = None) -> list[Job]:
        query = "SELECT * FROM jobs WHERE 1 = 1"
        params: list = []
        if statuses is not None:
            statuses = list(statuses)
            query += f" AND status IN ({', '.join('?' for _ in statuses)})"
            params += statuses
        if seen_since is not None:
            query += " AND last_seen >= ?"
            params.append(_to_text(seen_since))
        rows = self.conn.execute(query + " ORDER BY id", params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def set_status(self, job_id: int, status: str, note: str | None = None, at: datetime | None = None) -> None:
        if status not in STATUSES:
            raise HirejutsuError(f"Unknown status '{status}'. Use one of: {', '.join(STATUSES)}")
        at = _to_text(at or datetime.now(timezone.utc))
        with self.conn:
            cursor = self.conn.execute(
                "UPDATE jobs SET status = ?, status_at = ?, note = COALESCE(?, note) WHERE id = ?",
                (status, at, note, job_id),
            )
            if not cursor.rowcount:
                raise HirejutsuError(f"No job with id {job_id}")
            self.conn.execute(
                "INSERT INTO events (job_id, status, at, note) VALUES (?, ?, ?, ?)",
                (job_id, status, at, note or ""),
            )

    def add_note(self, job_id: int, note: str, at: datetime | None = None) -> None:
        """Note something about a job without changing its status."""
        at = _to_text(at or datetime.now(timezone.utc))
        with self.conn:
            cursor = self.conn.execute("UPDATE jobs SET note = ? WHERE id = ?", (note, job_id))
            if not cursor.rowcount:
                raise HirejutsuError(f"No job with id {job_id}")
            self.conn.execute("INSERT INTO events (job_id, at, note) VALUES (?, ?, ?)", (job_id, at, note))

    def history(self, job_id: int) -> list[tuple[str | None, datetime, str]]:
        """(status, at, note) for each change to a job, oldest first. status is None for a plain note."""
        rows = self.conn.execute(
            "SELECT status, at, note FROM events WHERE job_id = ? ORDER BY at, id", (job_id,)
        ).fetchall()
        return [(row["status"], _to_datetime(row["at"]), row["note"]) for row in rows]

    def status_counts(self) -> dict[str, int]:
        return dict(self.conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall())

    def applications(self) -> list[tuple[str, datetime, bool]]:
        """(company, first applied, got an interview or offer) for each job that is applied or past it."""
        rows = self.conn.execute(
            """
            SELECT jobs.company, MIN(events.at), MAX(events.status IN ('interview', 'offer'))
            FROM jobs JOIN events ON events.job_id = jobs.id
            WHERE jobs.status IN ('applied', 'interview', 'offer', 'rejected')
              AND events.status IN ('applied', 'interview', 'offer', 'rejected')
            GROUP BY jobs.id
            """
        ).fetchall()
        return [(company, _to_datetime(at), bool(answered)) for company, at, answered in rows]

    def record_picks(self, day: date, matches: list[Match]) -> None:
        """Save the jobs picked for a day, replacing any earlier picks for that day."""
        with self.conn:
            self.conn.execute("DELETE FROM picks WHERE day = ?", (day.isoformat(),))
            self.conn.executemany(
                "INSERT INTO picks (day, job_id, rank, score, reasons) VALUES (?, ?, ?, ?, ?)",
                [
                    (day.isoformat(), match.job.id, rank, match.score, json.dumps(match.reasons))
                    for rank, match in enumerate(matches, start=1)
                ],
            )

    def picks(self, day: date) -> list[Match]:
        rows = self.conn.execute(
            "SELECT jobs.*, picks.score AS pick_score, picks.reasons AS pick_reasons FROM picks "
            "JOIN jobs ON jobs.id = picks.job_id WHERE picks.day = ? ORDER BY picks.rank",
            (day.isoformat(),),
        ).fetchall()
        return [Match(self._row_to_job(row), row["pick_score"], json.loads(row["pick_reasons"])) for row in rows]

    def picked_job_ids(self, before: date | None = None) -> set[int]:
        query, params = "SELECT DISTINCT job_id FROM picks", ()
        if before is not None:
            query, params = query + " WHERE day < ?", (before.isoformat(),)
        return {row[0] for row in self.conn.execute(query, params)}

    def pick_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0]

    def log_fetch(self, source: str, started_at: datetime, seconds: float, found: int, added: int, error: str = "") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO fetches (source, started_at, seconds, found, added, error) VALUES (?, ?, ?, ?, ?, ?)",
                (source, _to_text(started_at), seconds, found, added, error),
            )

    def last_fetches(self) -> list[sqlite3.Row]:
        """Latest fetch of every source."""
        return self.conn.execute(
            "SELECT * FROM fetches WHERE id IN (SELECT MAX(id) FROM fetches GROUP BY source) ORDER BY source"
        ).fetchall()

    def prune(self, not_seen_since: datetime) -> int:
        """Delete untouched jobs that were never picked and have not been seen lately."""
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM jobs WHERE status = 'new' AND last_seen < ? AND id NOT IN (SELECT job_id FROM picks)",
                (_to_text(not_seen_since),),
            )
        return cursor.rowcount
