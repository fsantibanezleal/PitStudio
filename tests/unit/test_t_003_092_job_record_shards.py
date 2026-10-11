# ruff: noqa: E501, PT018
"""T-003-092: a job record with more shards done than total is refused by the API (G5 review).

Requirement: FR-003-31.

Expected behaviour: when the runner returns a job record whose `shards.done` is greater than `shards.total`, the console does not
serve it: `GET /jobs/{job_id}` and `GET /queue` answer 500 with the problem type/title `job-record-invalid` (the problem `title` or
`type` ends in or contains `job-record-invalid`) whose `detail` names the job id, and the console logs the record's SHA-256 (the
logger of the `pitstudio_api` package, any level, the 64-hex digest of the record's canonical JSON); a record with done == total or
done < total is served. (This is the only 5xx the console may produce, and only for a corrupt runner record; the record is read through
`pitstudio.runner.queue.job(job_id)` / `jobs()` looked up as module attributes.)
Oracle: hand-built records (done 5 / total 4 refused; 4 / 4 and 0 / 4 served) and the SHA-256 of their sorted compact JSON computed
with hashlib.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import console_world as cw
import runner_world as rw
import schemas

JOB_ID = "20261012T101500Z-0badf00d"


@pytest.fixture
def cons(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    c = cw.make_console_world(monkeypatch, tmp_path)
    yield c
    rw.cleanup_world(c.w)


def record(done: int, total: int) -> dict[str, Any]:
    return {
        "job_id": JOB_ID, "recipe": "a2-haulage", "state": "running", "run_id": "20261012T101500Z-a2-haulage", "created": "2026-10-12T10:15:00Z",
        "stage": {"id": "st10_terrain"}, "shards": {"done": done, "total": total}, "exit_code": None, "reason": None,
    }  # fmt: skip


def digest(rec: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def patch_queue(monkeypatch: pytest.MonkeyPatch, rec: dict[str, Any]) -> None:
    from pitstudio.runner import queue

    monkeypatch.setattr(
        queue,
        "job",
        lambda job_id, *a, **k: rec if job_id == rec["job_id"] else (_ for _ in ()).throw(KeyError(job_id)),
    )
    monkeypatch.setattr(queue, "jobs", lambda *a, **k: [rec])


@pytest.mark.req("FR-003-31")
@pytest.mark.parametrize(("done", "total"), [(5, 4), (1, 0), (10000, 9999), (2, 1)])
def test_fr_003_31_done_greater_than_total_is_never_served(
    cons, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, done: int, total: int
) -> None:
    rec = record(done, total)
    patch_queue(monkeypatch, rec)
    caplog.set_level(logging.DEBUG)
    r = cons.client.get(f"/jobs/{JOB_ID}")
    assert r.status == 500, f"{r.status} {r.text[:150]}"
    body = r.json()
    assert schemas.errors("console", body, "#/$defs/problem") == [] and body["status"] == 500
    assert "job-record-invalid" in body["type"] + " " + body["title"]
    assert JOB_ID in body["detail"]
    assert JOB_ID in r.text and '"shards"' not in r.text, "the invalid record itself is not served"
    logged = " ".join(rec_.getMessage() for rec_ in caplog.records)
    assert digest(rec) in logged, "the record's SHA-256 must be logged"
    listing = cons.client.get("/queue")
    assert listing.status == 500 and "job-record-invalid" in listing.text


@pytest.mark.req("FR-003-31")
@pytest.mark.parametrize(("done", "total"), [(4, 4), (0, 4), (3, 4), (0, 1), (10000, 10000)])
def test_fr_003_31_done_up_to_total_is_served(cons, monkeypatch: pytest.MonkeyPatch, done: int, total: int) -> None:
    rec = record(done, total)
    patch_queue(monkeypatch, rec)
    r = cons.client.get(f"/jobs/{JOB_ID}")
    assert r.status == 200, r.text
    assert r.json() == rec and schemas.errors("console", r.json(), "#/$defs/job") == []
    assert cons.client.get("/queue").json() == {"jobs": [rec]}


@pytest.mark.req("FR-003-31")
def test_fr_003_31_jobs_without_shards_are_served(cons, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = {**record(0, 1), "shards": None, "stage": None}
    patch_queue(monkeypatch, rec)
    assert cons.client.get(f"/jobs/{JOB_ID}").status == 200


@pytest.mark.req("FR-003-31")
def test_fr_003_31_one_bad_record_in_the_queue_does_not_leak_the_good_ones_nor_crash_the_console(
    cons, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pitstudio.runner import queue

    bad = record(5, 4)
    good = {**record(1, 4), "job_id": "20261012T101600Z-cafebabe"}
    monkeypatch.setattr(queue, "jobs", lambda *a, **k: [good, bad])
    r = cons.client.get("/queue")
    assert r.status == 500 and JOB_ID in r.json()["detail"]
    assert cons.client.get("/health").status == 200, "the console stays up"
