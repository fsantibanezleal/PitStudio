"""The job queue: one SQLite file per store, WAL mode, shared by the command line and the console (FR-002-39..41)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from typing import Any

from pitstudio.runner.recipe import Usage, store_root

FIELDS = ("job_id", "recipe", "state", "run_id", "created", "stage", "shards", "exit_code", "reason")
SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT UNIQUE NOT NULL,
recipe TEXT, profile TEXT, request TEXT, state TEXT, run_id TEXT, created TEXT, stage TEXT, shards TEXT,
exit_code INTEGER, reason TEXT, pid INTEGER, pid_start REAL, cancel INTEGER DEFAULT 0)"""


def _connect() -> sqlite3.Connection:
    store_root().mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(store_root() / "queue.db", timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    for sql in ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL", SCHEMA):
        con.execute(sql)
    return con


def _record(row: sqlite3.Row) -> dict[str, Any]:
    d = {k: row[k] for k in FIELDS}
    return {**d, **{k: json.loads(d[k]) if d[k] else None for k in ("stage", "shards")}}


def _one(sql: str, *args: Any) -> sqlite3.Row | None:
    with closing(_connect()) as con:
        return con.execute(sql, args).fetchone()


def enqueue(request: dict) -> str:
    job_id = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{uuid.uuid4().hex[:8]}"
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    row = (job_id, request["recipe"], request.get("profile"), json.dumps(request), created)
    with closing(_connect()) as con:
        con.execute(
            "INSERT INTO jobs (job_id, recipe, profile, request, state, created) VALUES (?, ?, ?, ?, 'queued', ?)", row
        )
    return job_id


def jobs() -> list[dict]:
    if not (store_root() / "queue.db").exists():
        return []
    with closing(_connect()) as con:
        return [_record(r) for r in con.execute("SELECT * FROM jobs ORDER BY seq")]


def job(job_id: str) -> dict | None:
    row = _one("SELECT * FROM jobs WHERE job_id = ?", job_id)
    return _record(row) if row else None


def request_of(job_id: str) -> dict:
    return json.loads(_one("SELECT request FROM jobs WHERE job_id = ?", job_id)["request"])


def update(job_id: str, **cols: Any) -> None:
    cols = {k: json.dumps(v) if k in ("stage", "shards") and v is not None else v for k, v in cols.items()}
    sets = ", ".join(f"{k} = ?" for k in cols)
    with closing(_connect()) as con:
        con.execute(f"UPDATE jobs SET {sets} WHERE job_id = ?", (*cols.values(), job_id))


def cancel_requested(job_id: str) -> bool:
    return bool(_one("SELECT cancel FROM jobs WHERE job_id = ?", job_id)["cancel"])


def cancel(job_id: str) -> str:
    """A queued job is cancelled at once; a running one is flagged and its worker ends it (FR-002-41)."""
    row = _one("SELECT state FROM jobs WHERE job_id = ?", job_id)
    if row is None or row["state"] not in ("queued", "running"):
        raise Usage(f"job {job_id} is unknown or already finished")
    with closing(_connect()) as con:
        if row["state"] == "queued":
            con.execute(
                "UPDATE jobs SET state = 'cancelled', exit_code = 6, reason = 'cancelled' WHERE job_id = ?", (job_id,)
            )
        else:
            con.execute("UPDATE jobs SET cancel = 1 WHERE job_id = ?", (job_id,))
    return "cancelled" if row["state"] == "queued" else "requested"


def claim() -> dict | None:
    """The oldest queued job, now `running` and owned by this process; None when the queue is empty."""
    import psutil

    with closing(_connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM jobs WHERE state = 'queued' ORDER BY seq LIMIT 1").fetchone()
        me = psutil.Process()
        if row:
            con.execute(
                "UPDATE jobs SET state = 'running', pid = ?, pid_start = ? WHERE job_id = ?",
                (me.pid, me.create_time(), row["job_id"]),
            )
        con.execute("COMMIT")
    return _record(row) if row else None


def settle_stale() -> None:
    """Jobs left `running` by a worker that no longer exists become `interrupted` (FR-002-37)."""
    import psutil

    with closing(_connect()) as con:
        for r in con.execute("SELECT job_id, pid, pid_start FROM jobs WHERE state = 'running'").fetchall():
            if not (psutil.pid_exists(r["pid"]) and abs(psutil.Process(r["pid"]).create_time() - r["pid_start"]) < 1):
                con.execute(
                    "UPDATE jobs SET state = 'interrupted', exit_code = 6, reason = 'worker-restart' WHERE job_id = ?",
                    (r["job_id"],),
                )
