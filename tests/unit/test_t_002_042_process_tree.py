# ruff: noqa: PT018
"""T-002-042: whole process trees are cleaned up on timeout, cancel and runner death (US-002-4).

Requirements: FR-002-27, FR-002-28.

Expected behaviour (stated for the implementer):
  * every stage process starts inside a Windows job object with kill-on-close, or (Linux) in its own process group;
  * after a timeout the runner ends the stage's whole tree within 10 s, records `error_class: timeout` (stage failed,
    exit 1), releases its GPU locks and stops its telemetry;
  * `studio queue cancel <job_id>` of a running job ends its tree within 10 s, releases the locks and makes the
    worker exit 6; the job state becomes `cancelled`;
  * (Windows) when the runner process itself dies, every process of the tree is gone within 10 s; (Linux) the stage was
    started in a new process group, which is what a later cancel kills.
  * `.github/workflows/ci.yml` has a job `runner-windows` on a GitHub-hosted Windows runner running the runner tests.
Oracles: psutil (reference process enumeration) over the pids the fake stage records for itself and its grandchild;
wall-clock bounds from the requirement; filelock to see whether the GPU lock is free.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import contextlib

import runner_world as rw
from runner_world import recipe, stage


def alive(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def tree_pids(world: rw.World) -> tuple[int, int]:
    rows = world.ledger_rows()
    stage_pid = next(r["pid"] for r in rows if r["event"] == "start")
    child = next(r["child_pid"] for r in rows if r["event"] == "grandchild")
    return stage_pid, child


def gone_within(pids: list[int], seconds: float) -> float | None:
    t0 = time.monotonic()
    while time.monotonic() - t0 <= seconds:
        if not any(alive(p) for p in pids):
            return time.monotonic() - t0
        time.sleep(0.05)
    return None


def lock_is_free(world: rw.World, name: str = "gpu0.compute") -> bool:
    from filelock import FileLock, Timeout

    lock = FileLock(world.lock_dir / name)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return False
    lock.release()
    return True


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    for line in w.ledger_rows():  # never leave sleepers behind
        for key in ("pid", "child_pid"):
            if key in line and alive(line[key]):
                with contextlib.suppress(psutil.Error):
                    psutil.Process(line[key]).kill()
    rw.cleanup_world(w)


def start_runner(world: rw.World, *argv: str) -> subprocess.Popen[str]:
    out = (world.base / "runner.out").open("w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "pitstudio.runner", *argv],
        env=world.env(),
        cwd=str(world.base),
        stdout=out,
        stderr=subprocess.STDOUT,
        text=True,
    )


@pytest.mark.req("FR-002-28")
@pytest.mark.req("FR-002-27")
@pytest.mark.parametrize("gpu", ["none", "exclusive"])
def test_fr_002_28_timeout_ends_the_whole_tree_within_10_seconds_releases_locks(world, gpu: str) -> None:
    sid = "st50_physics" if gpu == "exclusive" else "s10_preprocess"
    world.write_recipe(
        recipe(
            "timeouts",
            [
                stage(
                    sid,
                    gpu=gpu,
                    vram=2.0 if gpu == "exclusive" else None,
                    timeout_s=2,
                    params={"mode": "grandchild", "sleep_s": 120},
                )
            ],
        )
    )
    t0 = time.monotonic()
    r = world.run("timeouts")
    elapsed = time.monotonic() - t0
    assert r.code == 1, r.text
    rec = world.stage_record(sid)
    assert (rec["status"], rec["error_class"]) == ("failed", "timeout")
    stage_pid, child = tree_pids(world)
    assert elapsed < 2 + 10 + 10, f"the run took {elapsed:.1f}s"
    assert gone_within([stage_pid, child], 1.0) is not None, "stage or its grandchild survived the timeout"
    assert lock_is_free(world), "the GPU lock must be released"
    assert not any(alive(p) for p in (stage_pid, child))


@pytest.mark.req("FR-002-28")
def test_fr_002_28_the_manifest_records_the_timeout_attempt_and_downstream_is_skipped(world) -> None:
    world.write_recipe(
        recipe(
            "timeouts2",
            [
                stage("s10_preprocess", timeout_s=1, params={"mode": "sleep", "sleep_s": 60}),
                stage("s20_feature_extraction", inputs=[rw.up("s10_preprocess", "out.bin")]),
            ],
        )
    )
    assert world.run("timeouts2").code == 1
    rec = world.stage_record("s10_preprocess")
    assert rec["error_class"] == "timeout" and rec["attempts"][0]["error_class"] == "timeout"
    assert world.stage_record("s20_feature_extraction")["status"] == "skipped"


@pytest.mark.req("FR-002-27")
@pytest.mark.req("FR-002-28")
def test_fr_002_27_cancelling_a_running_job_ends_the_tree_within_10_seconds_and_exits_6(world) -> None:
    world.write_recipe(
        recipe(
            "cancelme",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    timeout_s=600,
                    params={"mode": "grandchild", "sleep_s": 300},
                )
            ],
        )
    )
    p = start_runner(world, "run", str(world.recipes["cancelme"]), "--profile", "test-profile")
    try:
        assert rw.wait_until(lambda: any(r["event"] == "grandchild" for r in world.ledger_rows()), 60, proc=p), (
            "the stage did not start"
        )
        stage_pid, child = tree_pids(world)
        from pitstudio.runner import queue

        (job,) = queue.jobs()
        assert job["state"] == "running"
        t0 = time.monotonic()
        r = world.cli("queue", "cancel", job["job_id"])
        assert r.code == 0, r.text
        assert p.wait(timeout=30) == 6
        took = gone_within([stage_pid, child], 10.0)
        assert took is not None, "the tree survived the cancel for more than 10 s"
        assert time.monotonic() - t0 <= 10 + 1
        assert lock_is_free(world)
        assert queue.job(job["job_id"])["state"] == "cancelled"
    finally:
        if p.poll() is None:
            p.kill()


@pytest.mark.req("FR-002-27")
def test_fr_002_27_when_the_runner_dies_its_tree_dies_on_windows_and_is_a_separate_group_on_linux(world) -> None:
    world.write_recipe(
        recipe("killrunner", [stage("s10_preprocess", timeout_s=600, params={"mode": "grandchild", "sleep_s": 300})])
    )
    p = start_runner(world, "run", str(world.recipes["killrunner"]), "--profile", "test-profile")
    try:
        assert rw.wait_until(lambda: any(r["event"] == "grandchild" for r in world.ledger_rows()), 60, proc=p), (
            "the stage did not start"
        )
        stage_pid, child = tree_pids(world)
        if rw.IS_WINDOWS:
            psutil.Process(p.pid).kill()  # TerminateProcess: no cleanup code runs in the runner
            p.wait(timeout=30)
            took = gone_within([stage_pid, child], 10.0)
            assert took is not None, "kill-on-job-close must remove the tree within 10 s of the runner's death"
        else:
            assert os.getpgid(stage_pid) == stage_pid != os.getpgid(p.pid), (
                "a stage starts in a new process group on Linux"
            )
            assert os.getpgid(child) == stage_pid
            p.terminate()
            p.wait(timeout=30)
    finally:
        if p.poll() is None:
            p.kill()


@pytest.mark.req("FR-002-27")
def test_fr_002_27_ci_has_a_windows_job_for_the_runner_tests() -> None:
    ci = yaml.safe_load((rw.ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job: dict[str, Any] = ci["jobs"]["runner-windows"]
    assert str(job["runs-on"]).startswith("windows")
    assert "pytest" in json.dumps(job)
