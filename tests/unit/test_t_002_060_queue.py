# ruff: noqa: E501, PT018
"""T-002-060: the SQLite job queue, its Python API, `run`/`worker`/`queue`/`status` commands (US-002-6).

Requirements: FR-002-39, FR-002-40, FR-002-41, FR-002-58.

Expected API (module `pitstudio.runner.queue`, store = PITSTUDIO_STORE; stated for the implementer):
  * `enqueue(job_request: dict) -> str`: `job_request` = {"recipe": <recipe id>, "profile": <profile id>, "stages"?: [stage_key],
    "force"?: bool, "rerun_check"?: bool} (contracts/recipe.schema.json#/$defs/job_request); returns a job id
    `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`; state `queued`;
  * `jobs() -> list[dict]`, `job(job_id) -> dict`: records with `job_id`, `recipe`, `state`, `run_id`, `created`, `stage`
    (current stage key object or null), `shards` ({done, total} or null), `exit_code`, `reason`;
  * `cancel(job_id)`: a queued job becomes `cancelled` at once;
  * `queue.db` is an SQLite file in WAL mode with a busy timeout of at least 5 s; one worker per store through
    `locks/worker.lock` (a second `worker` exits 3);
  * commands: `run <recipe> --profile <id> [--detach]` (enqueue, then a foreground worker until that job ends unless
    `--detach` or another worker holds the lock; returns the job's exit code), `worker` (drain the queue; exit 3 when
    another worker holds the lock), `queue ls [--json]`, `queue cancel <job_id>`, `status [--json]`; `queue ls` and
    `status` read without taking the worker lock and list every job with id, recipe, state, run id, current stage and
    shard progress (JSON: a list, or an object whose `jobs` is the list), `status` also shows active locks and the hold
    reason; both answer within 1 s for 1,000 jobs.
Oracles: sqlite3 (reference reader of the file), filelock (reference lock implementation), distinct-id counting for
concurrent enqueues, wall-clock bounds from the requirement.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage

JOB_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(
        monkeypatch,
        tmp_path,
        recipes=[
            recipe("one", [stage("s10_preprocess")]),
            recipe("two", [stage("st10_terrain")]),
            recipe("bad", [stage("s10_preprocess", params={"mode": "fail"})]),
        ],
    )
    yield w
    rw.cleanup_world(w)


def request(rid: str = "one", **extra: Any) -> dict[str, Any]:
    return {"recipe": rid, "profile": "test-profile", **extra}


def jobs_of(doc: Any) -> list[dict[str, Any]]:
    return doc["jobs"] if isinstance(doc, dict) else doc


# ---- FR-002-39: queue API ------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-39")
def test_fr_002_39_enqueue_returns_a_job_id_and_the_job_is_listed_queued(world) -> None:
    from pitstudio.runner import queue

    jid = queue.enqueue(request("one", force=True, rerun_check=True, stages=[{"id": "s10_preprocess"}]))
    assert JOB_ID.fullmatch(jid)
    rec = queue.job(jid)
    assert rec["job_id"] == jid and rec["recipe"] == "one" and rec["state"] == "queued"
    assert rec["run_id"] is None and rec["exit_code"] is None and rec["stage"] is None
    assert [j["job_id"] for j in queue.jobs()] == [jid]
    assert world.ledger_rows() == [], "enqueue launches nothing"
    for k in ("job_id", "recipe", "state", "run_id", "created", "stage", "shards", "exit_code", "reason"):
        assert k in rec


@pytest.mark.req("FR-002-39")
def test_fr_002_39_the_queue_file_is_sqlite_in_wal_mode_in_the_store(world) -> None:
    from pitstudio.runner import queue

    queue.enqueue(request())
    db = world.store / "queue.db"
    assert db.is_file()
    con = sqlite3.connect(db)
    try:
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] >= 1
    finally:
        con.close()


@pytest.mark.req("FR-002-39")
def test_fr_002_39_a_write_lock_held_for_a_few_seconds_makes_enqueue_wait_not_fail(world) -> None:
    from pitstudio.runner import queue

    queue.enqueue(request())  # create the schema
    con = sqlite3.connect(world.store / "queue.db", isolation_level=None)
    con.execute("BEGIN IMMEDIATE")
    result: list[Any] = []

    def go() -> None:
        try:
            result.append(queue.enqueue(request("two")))
        except Exception as e:
            result.append(e)

    t0 = time.monotonic()
    t = threading.Thread(target=go)
    t.start()
    time.sleep(2.0)
    con.execute("COMMIT")
    con.close()
    t.join(15)
    assert result and isinstance(result[0], str), f"enqueue must wait for the lock (busy timeout >= 5 s), got {result}"
    assert time.monotonic() - t0 >= 1.9
    assert len(queue.jobs()) == 2


@pytest.mark.req("FR-002-39")
def test_fr_002_39_concurrent_enqueues_from_several_processes_make_distinct_jobs(world) -> None:
    from pitstudio.runner import queue

    k, m = 4, 6
    code = f"import json, sys\nfrom pitstudio.runner import queue\nprint(json.dumps([queue.enqueue({{'recipe': 'one', 'profile': 'test-profile'}}) for _ in range({m})]))\n"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", code], env=world.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        for _ in range(k)
    ]
    ids: list[str] = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
        ids += json.loads(out.strip().splitlines()[-1])
    assert len(ids) == k * m and len(set(ids)) == k * m and all(JOB_ID.fullmatch(i) for i in ids)
    assert {j["job_id"] for j in queue.jobs()} == set(ids)


@pytest.mark.req("FR-002-39")
def test_fr_002_39_one_worker_per_store_a_second_worker_exits_3(world) -> None:
    from filelock import FileLock
    from pitstudio.runner import queue

    queue.enqueue(request())
    (world.store / "locks").mkdir(exist_ok=True)
    with FileLock(world.store / "locks" / "worker.lock", timeout=0):
        r = world.cli("worker")
        assert r.code == 3, r.text
        assert world.ledger_rows() == []
        assert queue.jobs()[0]["state"] == "queued"
    assert world.cli("worker").code == 0
    assert queue.jobs()[0]["state"] == "succeeded"


# ---- FR-002-40: run / --detach -----------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-40")
def test_fr_002_40_run_enqueues_one_job_runs_it_in_the_foreground_and_returns_its_exit_code(world) -> None:
    from pitstudio.runner import queue

    assert world.run("one").code == 0
    (j,) = queue.jobs()
    assert (j["state"], j["exit_code"], j["recipe"]) == ("succeeded", 0, "one") and j["run_id"] == world.last_run().name
    time.sleep(1.1)
    assert world.run("bad").code == 1
    states = {x["recipe"]: (x["state"], x["exit_code"]) for x in queue.jobs()}
    assert states == {"one": ("succeeded", 0), "bad": ("failed", 1)}


@pytest.mark.req("FR-002-40")
def test_fr_002_40_detach_only_enqueues_and_a_later_worker_runs_the_job(world) -> None:
    from pitstudio.runner import queue

    r = world.run("one", "--detach")
    assert r.code == 0, r.text
    assert world.ledger_rows() == [] and [j["state"] for j in queue.jobs()] == ["queued"]
    assert world.run_dirs() == []
    assert world.cli("worker").code == 0
    assert [j["state"] for j in queue.jobs()] == ["succeeded"] and len(world.starts()) == 1


@pytest.mark.req("FR-002-40")
def test_fr_002_40_when_another_worker_holds_the_lock_run_enqueues_and_returns_without_running(world) -> None:
    from filelock import FileLock
    from pitstudio.runner import queue

    (world.store / "locks").mkdir(exist_ok=True)
    with FileLock(world.store / "locks" / "worker.lock", timeout=0):
        t0 = time.monotonic()
        r = world.run("one")
        assert r.code == 0, r.text
        assert time.monotonic() - t0 < 10
        assert world.ledger_rows() == []
        assert [j["state"] for j in queue.jobs()] == ["queued"]


@pytest.mark.req("FR-002-40")
def test_fr_002_40_stage_selection_force_and_rerun_check_travel_in_the_job(world) -> None:
    from pitstudio.runner import queue

    world.write_recipe(recipe("sel", [stage("s10_preprocess"), stage("st10_terrain")]))
    assert world.run("sel", "--stage", "st10_terrain", "--force", "--rerun-check", "--detach").code == 0
    (j,) = queue.jobs()
    assert j["recipe"] == "sel" and j["state"] == "queued"
    assert world.cli("worker").code == 0
    assert [x["stage"]["id"] for x in world.starts() if not x["rerun"]] == ["st10_terrain"], (
        "only the selected stage runs"
    )
    assert any(x["rerun"] for x in world.starts()), "--rerun-check reached the worker"


# ---- FR-002-41: cancel -------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-41")
def test_fr_002_41_a_queued_job_is_cancelled_at_once_and_never_runs(world) -> None:
    from pitstudio.runner import queue

    jid = queue.enqueue(request("one"))
    t0 = time.monotonic()
    r = world.cli("queue", "cancel", jid)
    assert r.code == 0, r.text
    assert time.monotonic() - t0 < 5
    assert queue.job(jid)["state"] == "cancelled"
    assert world.cli("worker").code == 0
    assert world.ledger_rows() == [] and queue.job(jid)["state"] == "cancelled"


@pytest.mark.req("FR-002-41")
@pytest.mark.parametrize(
    "bad",
    ["nonsense", "20250101T000000Z-deadbeef", "", "20261007T120000Z-DEADBEEF", "../x", "20261007T120000Z-deadbeef\n"],
)
def test_fr_002_41_cancelling_an_unknown_or_malformed_job_fails_without_changes(world, bad: str) -> None:
    from pitstudio.runner import queue

    jid = queue.enqueue(request("one"))
    before = [j for j in queue.jobs()]
    r = world.cli("queue", "cancel", bad)
    assert r.code != 0 and "Traceback" not in r.text
    assert queue.jobs() == before and queue.job(jid)["state"] == "queued"


@pytest.mark.req("FR-002-41")
def test_fr_002_41_a_finished_job_cannot_be_cancelled(world) -> None:
    from pitstudio.runner import queue

    assert world.run("one").code == 0
    (j,) = queue.jobs()
    r = world.cli("queue", "cancel", j["job_id"])
    assert r.code != 0
    assert queue.job(j["job_id"])["state"] == "succeeded"


# ---- FR-002-58: listing and status ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-58")
def test_fr_002_58_queue_ls_lists_every_job_with_the_documented_fields_in_text_and_json(world) -> None:
    from pitstudio.runner import queue

    assert world.run("one").code == 0
    j2 = queue.enqueue(request("two"))
    r = world.cli("queue", "ls", "--json")
    assert r.code == 0, r.text
    rows = jobs_of(json.loads(r.out))
    by = {x["job_id"]: x for x in rows}
    assert len(rows) == 2 and by[j2]["state"] == "queued" and by[j2]["recipe"] == "two"
    done = next(x for x in rows if x["recipe"] == "one")
    assert done["state"] == "succeeded" and done["run_id"] == world.last_run().name
    for k in ("job_id", "recipe", "state", "run_id", "stage", "shards"):
        assert k in done
    text = world.cli("queue", "ls")
    assert (
        text.code == 0 and j2 in text.out and "two" in text.out and "queued" in text.out and done["run_id"] in text.out
    )


@pytest.mark.req("FR-002-58")
def test_fr_002_58_shard_progress_and_current_stage_of_a_running_job_are_visible(world) -> None:
    from pitstudio.runner import queue

    world.write_recipe(
        recipe("slowshards", [stage("st10_terrain", shardable=(1, 4), params={"mode": "sleep", "sleep_s": 1.5})])
    )
    p = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pitstudio.runner",
            "run",
            str(world.recipes["slowshards"]),
            "--profile",
            "test-profile",
        ],
        env=world.env(),
        cwd=str(world.base),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert rw.wait_until(
            lambda: any(j["state"] == "running" and j["shards"] and j["shards"]["done"] >= 1 for j in queue.jobs()),
            90,
            proc=p,
        ), "no progress visible"
        r = world.cli("queue", "ls", "--json")
        (row,) = jobs_of(json.loads(r.out))
        assert (
            row["state"] == "running"
            and row["stage"]["id"] == "st10_terrain"
            and row["shards"]["total"] == 4
            and 1 <= row["shards"]["done"] <= 3
        )
        s = world.cli("status", "--json")
        assert s.code == 0 and "st10_terrain" in s.out
    finally:
        p.kill()
        p.wait(30)


@pytest.mark.req("FR-002-58")
def test_fr_002_58_listing_does_not_take_the_worker_lock_and_status_shows_locks_and_hold(world) -> None:
    from filelock import FileLock
    from pitstudio.runner import queue

    queue.enqueue(request("one"))
    (world.store / "locks").mkdir(exist_ok=True)
    gpu = FileLock(world.lock_dir / "gpu0.compute")
    with FileLock(world.store / "locks" / "worker.lock", timeout=0), gpu:
        assert world.cli("queue", "ls").code == 0
        world.hold("gpu under maintenance")
        s = world.cli("status")
        assert s.code == 0, s.text
        assert "gpu under maintenance" in s.text and "gpu0.compute" in s.text
        sj = world.cli("status", "--json")
        assert sj.code == 0 and "gpu under maintenance" in sj.out
        json.loads(sj.out)


@pytest.mark.req("FR-002-58")
def test_fr_002_58_listing_1000_jobs_takes_at_most_one_second(world) -> None:
    from pitstudio.runner import queue

    for i in range(1000):
        queue.enqueue(request("one" if i % 2 else "two"))
    assert world.cli("queue", "ls", "--json").code == 0  # warm-up
    for argv in (("queue", "ls", "--json"), ("queue", "ls"), ("status", "--json"), ("status",)):
        t0 = time.perf_counter()
        r = world.cli(*argv)
        took = time.perf_counter() - t0
        assert r.code == 0 and took <= 1.0, f"{' '.join(argv)} took {took:.2f}s"
    assert len(jobs_of(json.loads(world.cli("queue", "ls", "--json").out))) == 1000


@pytest.mark.req("FR-002-58")
def test_fr_002_58_an_empty_queue_lists_nothing_and_exits_0(world) -> None:
    r = world.cli("queue", "ls", "--json")
    assert r.code == 0 and jobs_of(json.loads(r.out)) == []
    assert world.cli("status").code == 0
