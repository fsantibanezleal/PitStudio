# ruff: noqa: E501, PT018
"""T-002-045: shards as executions, resume, stale-job recovery, resume equivalence (US-002-4).

Requirements: FR-002-35, FR-002-36, FR-002-37, P-002-07.

Expected behaviour (stated for the implementer):
  * a stage with `shardable: {shard_size, total}` runs as ceil(total / shard_size) executions; execution i gets the
    job spec `shard {index: i, size, total}`, the seed derive_seed(recipe seed, stage key, i), its own cache key, its own
    promotion (one index entry per shard); the manifest stage record has `shards: {total: n, done: <promoted>}`;
  * `studio run --resume <run_id> --profile <id>` reuses the run id and its manifest, executes only executions without a
    promoted index entry, and appends to `events.jsonl` (strictly increasing `seq`, earlier lines unchanged) and
    `telemetry.jsonl`;
  * when a worker starts and finds a job in state `running` whose recorded process no longer exists, it sets that job to
    `interrupted` with reason `worker-restart` before taking a new job.
Oracles: ledger of stage launches (each fake stage process appends one line), hand-derived shard digests
(documented content rule + FR-002-09 seeds recomputed with hashlib), psutil to kill a runner.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import contextlib

import runner_world as rw
from runner_world import recipe, stage

SEED0 = 20261004


def ref_seed(seed0: int, key: str, i: int) -> int:
    return int.from_bytes(hashlib.sha256(rw.jcs_simple([seed0, key, i])).digest()[:8], "big") & (2**63 - 1)


def shard_digest(stage_id: str, i: int, payload: str = "x") -> str:
    seed = ref_seed(SEED0, stage_id, i)
    return hashlib.sha256(f"{stage_id}|None|{seed}|{i}|out.bin|{payload}\n".encode()).hexdigest()


def sharded(n: int, *, gpu: bool = True, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if gpu:
        st = stage("st50_physics", gpu="exclusive", vram=2.0, shardable=(1, n), params=params)
    else:
        st = stage("st10_terrain", shardable=(1, n), params=params)
    return recipe("sharded", [st], seed=SEED0)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def index_digests(world: rw.World) -> list[str]:
    out = []
    for p in sorted((world.store / "index").rglob("*.json")):
        out += [o["sha256"] for o in json.loads(p.read_text(encoding="utf-8"))["outputs"]]
    return out


# ---- FR-002-35 ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-35")
def test_fr_002_35_a_sharded_stage_runs_ceil_total_over_size_executions_each_with_its_own_seed_and_promotion(
    world,
) -> None:
    world.write_recipe(recipe("sharded", [stage("st10_terrain", shardable=(10, 35))], seed=SEED0))
    r = world.run("sharded")
    assert r.code == 0, r.text
    rows = sorted(world.starts(), key=lambda x: x["shard"])
    assert [x["shard"] for x in rows] == [0, 1, 2, 3], "ceil(35 / 10) = 4 executions"
    assert [x["job"]["shard"] for x in rows] == [{"index": i, "size": 10, "total": 35} for i in range(4)]
    assert [x["seed"] for x in rows] == [ref_seed(SEED0, "st10_terrain", i) for i in range(4)]
    assert len({x["seed"] for x in rows}) == 4
    entries = list((world.store / "index").rglob("*.json"))
    assert len(entries) == 4 and len({p.stem for p in entries}) == 4, "one index entry and one key per shard"
    digests = index_digests(world)
    assert sorted(digests) == sorted(shard_digest("st10_terrain", i) for i in range(4))
    assert world.stage_record("st10_terrain")["shards"] == {"total": 4, "done": 4}
    assert rw.cas_violations(world.store) == []


@pytest.mark.req("FR-002-35")
def test_fr_002_35_completed_shards_are_cache_hits_for_a_later_run(world) -> None:
    world.write_recipe(sharded(3, gpu=False))
    assert world.run("sharded").code == 0
    assert len(world.starts()) == 3
    time.sleep(1.1)
    assert world.run("sharded").code == 0
    assert len(world.starts()) == 3, "every completed shard is a hit"
    # remove the index entry of shard 1 only: exactly that shard runs again
    victim = next(
        p
        for p in (world.store / "index").rglob("*.json")
        if json.loads(p.read_text(encoding="utf-8"))["outputs"][0]["sha256"] == shard_digest("st10_terrain", 1)
    )
    victim.unlink()
    time.sleep(1.1)
    assert world.run("sharded").code == 0
    assert [x["shard"] for x in world.starts()][3:] == [1]


# ---- FR-002-36: resume after a failure ---------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-36")
def test_fr_002_36_resume_of_a_failed_run_executes_only_the_missing_shards_and_appends_to_the_logs(world) -> None:
    world.write_recipe(sharded(4))
    world.monkeypatch.setenv("PS_FAKE_FAIL_SHARD", "2")
    r = world.run("sharded")
    assert r.code == 1, r.text
    assert [x["shard"] for x in world.starts()] == [0, 1, 2], "a failed shard stops the stage"
    run_id = world.last_run().name
    events_before = world.events()
    tele_before = (
        (world.last_run() / "telemetry.jsonl").read_text(encoding="utf-8")
        if (world.last_run() / "telemetry.jsonl").exists()
        else ""
    )
    manifest_before = world.manifest()
    world.monkeypatch.delenv("PS_FAKE_FAIL_SHARD")
    r2 = world.cli("run", "--resume", run_id, "--profile", "test-profile")
    assert r2.code == 0, r2.text
    assert [x["shard"] for x in world.starts()] == [0, 1, 2, 2, 3], (
        "shards 0 and 1 are promoted already: only 2 and 3 run"
    )
    assert len(world.run_dirs()) == 1 and world.last_run().name == run_id
    m = world.manifest()
    assert (
        m["run_id"] == manifest_before["run_id"]
        and m["created"] == manifest_before["created"]
        and m["seed"] == manifest_before["seed"]
    )
    assert world.stage_record("st50_physics")["status"] == "succeeded" and world.stage_record("st50_physics")[
        "shards"
    ] == {"total": 4, "done": 4}
    events_after = world.events()
    assert events_after[: len(events_before)] == events_before, "events.jsonl is appended to, never rewritten"
    assert len(events_after) > len(events_before)
    seqs = [e["seq"] for e in events_after]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs), "seq strictly increases across the resume"
    tele_after = (world.last_run() / "telemetry.jsonl").read_text(encoding="utf-8")
    assert tele_after.startswith(tele_before) and len(tele_after) >= len(tele_before)
    assert sorted(index_digests(world)) == sorted(shard_digest("st50_physics", i) for i in range(4))


@pytest.mark.req("FR-002-36")
@pytest.mark.parametrize(
    "bad",
    ["20250101T000000Z-nope", "../etc/passwd", "", "a" * 200, "20261004T120000Z-sharded\n"],
    ids=["unknown", "traversal", "empty", "overlong", "trailing-newline"],
)
def test_fr_002_36_resume_of_an_unknown_or_malformed_run_is_a_usage_error(world, bad: str) -> None:
    world.write_recipe(sharded(2))
    before = world.snapshot_store()
    r = world.cli("run", "--resume", bad, "--profile", "test-profile")
    assert r.code == 2, r.text
    assert world.snapshot_store() == before and world.ledger_rows() == []


@pytest.mark.req("FR-002-36")
def test_fr_002_36_resume_of_a_succeeded_run_launches_nothing(world) -> None:
    world.write_recipe(sharded(2, gpu=False))
    assert world.run("sharded").code == 0
    run_id = world.last_run().name
    r = world.cli("run", "--resume", run_id, "--profile", "test-profile")
    assert r.code in (0, 2)
    assert len(world.starts()) == 2


# ---- P-002-07: resume equivalence -------------------------------------------------------------------------------------------------------------
def reset(world: rw.World) -> None:
    world.release_hold()
    shutil.rmtree(world.store, ignore_errors=True)
    world.store.mkdir(parents=True)
    if world.ledger.exists():
        world.ledger.unlink()


CASES = [(n, k) for n in (1, 2, 3, 5, 8) for k in range(n)] + [(20, 0), (20, 10), (20, 19)]


@pytest.mark.req("P-002-07")
def test_p_002_07_interrupting_a_sharded_stage_at_any_shard_and_resuming_gives_the_uninterrupted_digests(world) -> None:
    for n, k in CASES:
        reset(world)
        world.write_recipe(sharded(n, params={"mode": "hold_after", "hold_dir": str(world.lock_dir), "hold_shard": k}))
        r = world.run("sharded")
        assert r.code == (4 if k < n - 1 else 0), f"n={n} k={k}: exit {r.code}\n{r.text}"
        done_first = sorted(x["shard"] for x in world.starts())
        assert done_first == list(range(k + 1)), f"n={n} k={k}: shards started before the interruption: {done_first}"
        if k < n - 1:
            run_id = world.last_run().name
            world.release_hold()
            r2 = world.cli("run", "--resume", run_id, "--profile", "test-profile")
            assert r2.code == 0, f"n={n} k={k}: resume exit {r2.code}\n{r2.text}"
        shards = sorted(x["shard"] for x in world.starts())
        assert shards == list(range(n)), f"n={n} k={k}: every shard executed exactly once, saw {shards}"
        assert sorted(index_digests(world)) == sorted(shard_digest("st50_physics", i) for i in range(n)), (
            f"n={n} k={k}: digests differ from an uninterrupted run"
        )
        assert world.stage_record("st50_physics")["shards"] == {"total": n, "done": n}
        assert rw.cas_violations(world.store) == []


# ---- FR-002-37: a killed worker leaves a stale `running` job ---------------------------------------------------------------------------------------
def start_runner(world: rw.World, *argv: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "pitstudio.runner", *argv],
        env=world.env(),
        cwd=str(world.base),
        stdout=(world.base / "runner.out").open("w"),
        stderr=subprocess.STDOUT,
        text=True,
    )


@pytest.mark.req("FR-002-37")
@pytest.mark.req("FR-002-36")
def test_fr_002_37_a_worker_killed_mid_shard_leaves_a_job_that_the_next_worker_marks_interrupted_and_resume_redoes_only_that_shard(
    world,
) -> None:
    world.write_recipe(sharded(4, params={"mode": "sleep", "sleep_s": 1.5}))
    p = start_runner(world, "run", str(world.recipes["sharded"]), "--profile", "test-profile")
    try:
        assert rw.wait_until(
            lambda: len([x for x in world.ledger_rows() if x["event"] == "start" and x["shard"] == 1]) == 1, 90, proc=p
        ), "shard 1 never started"
        run_id = world.last_run().name
        psutil.Process(p.pid).kill()
        p.wait(timeout=30)
        for r in world.ledger_rows():  # whatever survived the runner (no job object on Linux) must not run on
            if r["event"] == "start":
                with contextlib.suppress(psutil.Error):
                    psutil.Process(r["pid"]).kill()
        from pitstudio.runner import queue

        (job,) = queue.jobs()
        assert job["state"] == "running", "nobody has noticed the death yet"
        # another worker starts: it must settle the stale job before taking anything new
        r = world.cli("worker")
        assert r.code == 0, r.text
        (job,) = queue.jobs()
        assert job["state"] == "interrupted" and "worker-restart" in (job["reason"] or "")
        r2 = world.cli("run", "--resume", run_id, "--profile", "test-profile")
        assert r2.code == 0, r2.text
        counts = {i: sum(1 for x in world.starts() if x["shard"] == i) for i in range(4)}
        assert counts == {0: 1, 1: 2, 2: 1, 3: 1}, f"only the interrupted shard runs twice: {counts}"
        assert sorted(index_digests(world)) == sorted(shard_digest("st50_physics", i) for i in range(4))
        assert any(j["state"] == "succeeded" for j in queue.jobs()), "the resumed work ends succeeded"
    finally:
        if p.poll() is None:
            p.kill()
