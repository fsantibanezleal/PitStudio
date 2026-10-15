# ruff: noqa: E501, PT018
"""T-002-030: machine-wide GPU locks, the GPU hold and lock waiting (US-002-2).

Requirements: FR-002-15, FR-002-16, FR-002-17, FR-002-18, FR-002-23, P-002-09, NFR-002-04.

Expected API (stated for the implementer):
  * `pitstudio.runner.locks`:
      - `lock_dir() -> Path`: GPU_LOCK_DIR, default `<system temp>/gpu-locks` (as studio/bench/run_bench.py);
      - `hold_reason(directory: Path | None = None) -> str | None`: None when no `gpu0.hold` (tested with
        `os.path.lexists`: a directory or a broken link counts); else the first 4,096 bytes decoded as UTF-8 with
        replacement, stripped, cut to 300 characters, or `no reason given` when that is empty or unreadable;
      - `acquire(name: str, *, wait_s: float, lock_dir: Path | None = None, clock=None) -> context manager`: holds
        `<lock_dir>/<name>` through `filelock` (name `gpu0.compute` or `gpu0.nvenc`; the lock file has exactly that
        name); polls at most every 5 s using `clock.sleep(seconds)` / `clock.monotonic()`; re-checks the hold on every
        poll; raises `locks.LockTimeout` after `wait_s`, `locks.GpuHold` (with `.reason`) when a hold appears;
        releases on every exit path;
  * command line: a command that may run GPU work (`run` of a recipe with a GPU stage, `worker`, `profile`) exits 4
    with `GPU hold in <lock dir>/gpu0.hold: <reason> -- not starting` before importing `pynvml` or `filelock`;
    `run` of a recipe with only CPU stages is not stopped by a hold or a held GPU lock;
  * a GPU stage whose lock stays taken for the profile's `guards.lock_wait_s` ends the job `blocked`
    (`error_class: lock-timeout`) with exit 3 and starts no process; a hold that appears between shards ends the job
    `held` (state and reason in `pitstudio.runner.queue.job(job_id)`), exit 4, resumable with `run --resume <run_id>`.
Oracles: real `filelock` contention in threads and processes (reference implementation), expected reason strings
computed by hand from the byte rules, fake clock for waiting, interval-overlap check of recorded timestamps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import itertools

import runner_world as rw
from runner_world import FakeClock, recipe, stage

GPU_RECIPE = recipe("gpu-one", [stage("st50_physics", gpu="exclusive", vram=2.0, params={"probe_locks": True})])
CPU_RECIPE = recipe("cpu-one", [stage("s10_preprocess", params={"probe_locks": True})])


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path, recipes=[GPU_RECIPE, CPU_RECIPE])
    yield w
    rw.cleanup_world(w)


def make_broken_link(path: Path, scratch: Path) -> None:
    """A dangling link: symlink to nothing, or (no symlink privilege on Windows) a junction whose target was removed."""
    try:
        os.symlink(scratch / "nowhere", path)
    except OSError:
        target = scratch / "junction-target"
        target.mkdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(path), str(target)], check=True, capture_output=True)
        target.rmdir()


def hold_line(world: rw.World, reason: str) -> str:
    return f"GPU hold in {world.lock_dir / 'gpu0.hold'}: {reason} -- not starting"


# ---- FR-002-16: hold file --------------------------------------------------------------------------------------------
HOLD_CASES: list[tuple[str, bytes | str, str]] = [
    ("text", "bugcheck under investigation\n", "bugcheck under investigation"),
    ("padded-text", "\n\t  reason with edges \r\n\n", "reason with edges"),
    ("empty", "", "no reason given"),
    ("whitespace-only", " \n\t\r\n ", "no reason given"),
    ("long-text-cut-to-300-chars", "é" * 400, "é" * 300),
    ("reason-after-4096-bytes-is-not-read", " " * 4096 + "late reason", "no reason given"),
    ("invalid-utf8", b"\xff\xfe broken bytes", (b"\xff\xfe broken bytes").decode("utf-8", "replace").strip()),
    ("megabyte-of-binary", bytes(range(256)) * 4096, (bytes(range(256)) * 16).decode("utf-8", "replace").strip()[:300]),
    ("unicode", "déjà vu 中文 \U0001f525", "déjà vu 中文 \U0001f525"),
]


@pytest.mark.req("FR-002-16")
@pytest.mark.parametrize(("name", "content", "reason"), HOLD_CASES, ids=[c[0] for c in HOLD_CASES])
def test_fr_002_16_hold_file_stops_gpu_commands_with_exit_4_before_any_gpu_library(
    world, name: str, content: bytes | str, reason: str
) -> None:
    p = world.lock_dir / "gpu0.hold"
    p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    calls = rw.forbid_popen(world.monkeypatch)
    for argv in (
        ("run", str(world.recipes["gpu-one"]), "--profile", "test-profile"),
        ("worker",),
        ("profile", str(world.recipes["gpu-one"]), "--stage", "st50_physics", "--profile", "test-profile"),
    ):
        r = world.cli(*argv)
        assert r.code == 4, f"{argv[0]}: exit {r.code}\n{r.text}"
        assert hold_line(world, reason) in r.text.replace("\r\n", "\n"), r.text
    assert calls == [] and world.ledger_rows() == []


@pytest.mark.req("FR-002-16")
def test_fr_002_16_hold_reason_function_follows_the_byte_rules(world) -> None:
    from pitstudio.runner import locks

    assert locks.hold_reason() is None
    for _, content, reason in HOLD_CASES:
        p = world.lock_dir / "gpu0.hold"
        p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        assert locks.hold_reason() == reason
    assert locks.lock_dir() == world.lock_dir


@pytest.mark.req("FR-002-16")
@pytest.mark.parametrize("kind", ["directory", "broken-link"])
def test_fr_002_16_a_directory_or_a_broken_link_is_still_a_hold(world, tmp_path: Path, kind: str) -> None:
    p = world.lock_dir / "gpu0.hold"
    if kind == "directory":
        p.mkdir()
    else:
        make_broken_link(p, tmp_path)
    assert os.path.lexists(p)
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    r = world.cli("run", str(world.recipes["gpu-one"]), "--profile", "test-profile")
    assert r.code == 4, r.text
    assert hold_line(world, "no reason given") in r.text
    from pitstudio.runner import locks

    assert locks.hold_reason() == "no reason given"
    assert world.ledger_rows() == []


@pytest.mark.req("FR-002-16")
def test_fr_002_16_planning_and_read_only_commands_ignore_the_hold(world) -> None:
    world.hold("not now")
    rw.block_modules(world.monkeypatch, "pynvml", "filelock")
    assert world.cli("plan", str(world.recipes["gpu-one"]), "--profile", "test-profile").code == 0
    assert world.cli("queue", "ls").code == 0
    st = world.cli("status")
    assert st.code == 0 and "not now" in st.text, "status shows the hold reason (FR-002-58)"


@pytest.mark.req("FR-002-16")
@pytest.mark.req("FR-002-23")
def test_fr_002_23_the_hold_stops_gpu_work_only_cpu_recipes_still_run(world) -> None:
    world.hold("gpu maintenance")
    rw.block_modules(world.monkeypatch, "pynvml")
    r = world.run("cpu-one")
    assert r.code == 0, r.text
    (row,) = world.starts()
    assert row["locks_held"] == {"gpu0.compute": False, "gpu0.nvenc": False}


# ---- FR-002-15 / FR-002-23: locks held for the whole execution ---------------------------------------------------------
class Contender(threading.Thread):
    """Polls a machine-wide lock with the same library the runner uses; records every moment it could take it."""

    def __init__(self, path: Path) -> None:
        super().__init__(daemon=True)
        self.path = path
        self.stop = threading.Event()
        self.acquired_at: list[float] = []

    def run(self) -> None:
        from filelock import FileLock, Timeout

        lock = FileLock(self.path)
        while not self.stop.is_set():
            try:
                lock.acquire(timeout=0)
            except Timeout:
                pass
            else:
                self.acquired_at.append(time.time_ns())
                lock.release()
            time.sleep(0.002)


@pytest.mark.req("FR-002-15")
@pytest.mark.parametrize(
    ("gpu", "stage_id", "mine", "other"),
    [
        ("exclusive", "st50_physics", "gpu0.compute", "gpu0.nvenc"),
        ("nvenc", "st56_encode", "gpu0.nvenc", "gpu0.compute"),
    ],
)
def test_fr_002_15_a_gpu_stage_holds_its_lock_and_only_its_lock_while_it_runs(
    world, gpu: str, stage_id: str, mine: str, other: str
) -> None:
    world.write_recipe(
        recipe(
            "locky", [stage(stage_id, gpu=gpu, vram=2.0 if gpu == "exclusive" else None, params={"probe_locks": True})]
        )
    )
    r = world.run("locky")
    assert r.code == 0, r.text
    (row,) = world.starts()
    assert row["locks_held"][mine] is True and row["locks_held"][other] is False
    # released afterwards
    from filelock import FileLock

    for name in ("gpu0.compute", "gpu0.nvenc"):
        with FileLock(world.lock_dir / name, timeout=0):
            pass


@pytest.mark.req("FR-002-15")
def test_fr_002_15_the_lock_is_held_through_retries_and_released_on_failure(world) -> None:
    world.write_recipe(
        recipe(
            "retrying",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    params={"mode": "oom_if_big", "particles": 100, "limit": 50, "probe_locks": True},
                    retry=[{"particles": 10}],
                )
            ],
        )
    )
    c = Contender(world.lock_dir / "gpu0.compute")
    c.start()
    time.sleep(0.05)
    try:
        r = world.run("retrying")
    finally:
        c.stop.set()
        c.join(5)
    assert r.code == 0, r.text
    starts = world.starts()
    assert len(starts) == 2 and all(s["locks_held"]["gpu0.compute"] for s in starts)
    rows = world.ledger_rows()
    first_start, last_end = min(x["t_ns"] for x in rows), max(x["t_ns"] for x in rows)
    window = [t for t in c.acquired_at if first_start <= t <= last_end]
    assert window == [], "the lock was free between the attempts of one stage"
    assert c.acquired_at, "sanity: the contender can take the lock when nobody holds it"

    world.write_recipe(recipe("failing", [stage("st50_physics", gpu="exclusive", vram=2.0, params={"mode": "fail"})]))
    assert world.run("failing").code == 1
    from filelock import FileLock

    with FileLock(world.lock_dir / "gpu0.compute", timeout=0):
        pass


@pytest.mark.req("FR-002-15")
def test_fr_002_15_the_lock_is_released_after_a_timeout(world) -> None:
    world.write_recipe(
        recipe(
            "slow",
            [stage("st50_physics", gpu="exclusive", vram=2.0, timeout_s=1, params={"mode": "sleep", "sleep_s": 20})],
        )
    )
    t0 = time.monotonic()
    r = world.run("slow")
    assert r.code == 1, r.text
    assert time.monotonic() - t0 < 20
    assert world.stage_record("st50_physics")["error_class"] in ("timeout", "warmup-timeout")
    from filelock import FileLock

    with FileLock(world.lock_dir / "gpu0.compute", timeout=0):
        pass


# ---- FR-002-18: waiting --------------------------------------------------------------------------------------------------
class HookClock(FakeClock):
    def __init__(self, on_sleep: Any) -> None:
        super().__init__()
        self.on_sleep = on_sleep

    def sleep(self, seconds: float) -> None:
        super().sleep(seconds)
        self.on_sleep(len(self.sleeps), self.t)


@pytest.mark.req("FR-002-18")
def test_fr_002_18_waiting_polls_at_most_every_5_seconds_then_times_out(world) -> None:
    from filelock import FileLock
    from pitstudio.runner import locks

    holder = FileLock(world.lock_dir / "gpu0.compute")
    holder.acquire(timeout=0)
    try:
        clock = FakeClock()
        with (
            pytest.raises(locks.LockTimeout),
            locks.acquire("gpu0.compute", wait_s=23, lock_dir=world.lock_dir, clock=clock),
        ):
            pytest.fail("the lock is held elsewhere")
        assert clock.sleeps and all(0 < s <= 5 for s in clock.sleeps), clock.sleeps
        assert 23 <= clock.t <= 23 + 5, f"gave up at t={clock.t}"
    finally:
        holder.release()


@pytest.mark.req("FR-002-18")
def test_fr_002_18_a_lock_released_while_waiting_is_taken_at_the_next_poll(world) -> None:
    from filelock import FileLock, Timeout
    from pitstudio.runner import locks

    holder = FileLock(world.lock_dir / "gpu0.compute")
    holder.acquire(timeout=0)
    released = []

    def on_sleep(n: int, t: float) -> None:
        if n == 3 and not released:
            holder.release()
            released.append(t)

    clock = HookClock(on_sleep)
    with locks.acquire("gpu0.compute", wait_s=3600, lock_dir=world.lock_dir, clock=clock):
        assert released and clock.t == released[0], "taken at the first poll after the release"
        with pytest.raises(Timeout):
            FileLock(world.lock_dir / "gpu0.compute").acquire(timeout=0)
    assert len(clock.sleeps) == 3


@pytest.mark.req("FR-002-18")
@pytest.mark.req("FR-002-16")
def test_fr_002_18_a_hold_appearing_while_waiting_is_noticed_at_the_next_poll(world) -> None:
    from filelock import FileLock
    from pitstudio.runner import locks

    holder = FileLock(world.lock_dir / "gpu0.compute")
    holder.acquire(timeout=0)
    try:

        def on_sleep(n: int, t: float) -> None:
            if n == 2:
                world.hold("appeared while you waited")

        clock = HookClock(on_sleep)
        with (
            pytest.raises(locks.GpuHold) as e,
            locks.acquire("gpu0.compute", wait_s=3600, lock_dir=world.lock_dir, clock=clock),
        ):
            pytest.fail("must not start under a hold")
        assert e.value.reason == "appeared while you waited"
        assert len(clock.sleeps) == 2, "re-checked on every poll"
    finally:
        holder.release()


@pytest.mark.req("FR-002-18")
def test_fr_002_18_a_gpu_stage_that_cannot_get_its_lock_ends_blocked_with_exit_3_and_starts_nothing(world) -> None:
    from filelock import FileLock

    holder = FileLock(world.lock_dir / "gpu0.compute")
    holder.acquire(timeout=0)
    try:
        t0 = time.monotonic()
        r = world.run("gpu-one")
    finally:
        holder.release()
    elapsed = time.monotonic() - t0
    assert r.code == 3, r.text
    assert 1.5 <= elapsed < 30, f"waited {elapsed:.1f}s for a lock_wait_s of 2"
    assert world.ledger_rows() == [], "the stage must not start"
    rec = world.stage_record("st50_physics")
    assert (rec["status"], rec["error_class"]) == ("blocked", "lock-timeout")
    from pitstudio.runner import queue

    (job,) = queue.jobs()
    assert job["state"] == "blocked"


@pytest.mark.req("FR-002-23")
def test_fr_002_23_a_cpu_stage_is_not_blocked_by_another_processs_gpu_lock(world) -> None:
    from filelock import FileLock

    locks_ = [FileLock(world.lock_dir / n) for n in ("gpu0.compute", "gpu0.nvenc")]
    for lk in locks_:
        lk.acquire(timeout=0)
    try:
        t0 = time.monotonic()
        r = world.run("cpu-one")
    finally:
        for lk in locks_:
            lk.release()
    assert r.code == 0, r.text
    assert time.monotonic() - t0 < 2.0 + 20, "no waiting for a lock a CPU stage does not need"
    (row,) = world.starts()
    assert row["locks_held"] == {"gpu0.compute": True, "gpu0.nvenc": True}, (
        "probe sees the foreign locks, so the stage held neither"
    )


# ---- FR-002-17: a hold appearing between shards ---------------------------------------------------------------------
@pytest.mark.req("FR-002-17")
def test_fr_002_17_a_hold_between_shards_ends_the_job_held_keeps_it_resumable_and_resume_runs_only_the_rest(
    world,
) -> None:
    world.write_recipe(
        recipe(
            "sharded",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    shardable=(10, 30),
                    params={"mode": "hold_after", "hold_dir": str(world.lock_dir), "hold_shard": 0},
                )
            ],
        )
    )
    r = world.run("sharded")
    assert r.code == 4, r.text
    assert [(s["stage"]["id"], s["shard"]) for s in world.starts()] == [("st50_physics", 0)], (
        "no further shard may start under a hold"
    )
    from pitstudio.runner import queue

    (job,) = queue.jobs()
    assert job["state"] == "held" and "hold appeared mid-run" in (job["reason"] or "")
    run_id = world.last_run().name
    assert any(e["type"] == "hold-detected" for e in world.events())
    world.release_hold()
    time.sleep(1.1)
    r2 = world.cli("run", "--resume", run_id, "--profile", "test-profile")
    assert r2.code == 0, r2.text
    shards = sorted(s["shard"] for s in world.starts())
    assert shards == [0, 1, 2], f"each shard exactly once across both runs: {shards}"
    assert world.last_run().name == run_id and len(world.run_dirs()) == 1, "resume reuses the run"


# ---- P-002-09: mutual exclusion across processes ---------------------------------------------------------------------
def intervals(rows: list[dict[str, Any]]) -> list[tuple[int, int, int]]:
    start: dict[int, int] = {}
    out = []
    for r in rows:
        if r["event"] == "start":
            start[r["pid"]] = r["t_ns"]
        elif r["event"] == "end":
            out.append((start[r["pid"]], r["t_ns"], r["pid"]))
    return sorted(out)


@pytest.mark.req("P-002-09")
@pytest.mark.parametrize("k", [2, 3, 6])
def test_p_002_09_runner_processes_never_overlap_inside_a_compute_stage(world, k: int, tmp_path: Path) -> None:
    world.set_guards(lock_wait_s=120)
    world.write_recipe(
        recipe("excl", [stage("st50_physics", gpu="exclusive", vram=2.0, params={"mode": "sleep", "sleep_s": 0.4})])
    )
    procs = []
    stores = []
    for _i in range(k):
        store = rw.short_dir("mx")
        stores.append(store)
        env = {**world.env(), "PITSTUDIO_STORE": str(store)}
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pitstudio.runner",
                    "run",
                    str(world.recipes["excl"]),
                    "--profile",
                    "test-profile",
                ],
                env=env,
                cwd=str(world.base),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        )
    outs = [p.communicate(timeout=240)[0] for p in procs]
    try:
        assert [p.returncode for p in procs] == [0] * k, outs
        iv = intervals(world.ledger_rows())
        assert len(iv) == k
        for (_, e1, _), (s2, _, _) in itertools.pairwise(iv):
            assert e1 <= s2, "two compute stages overlapped: " + json.dumps(iv)
    finally:
        import shutil

        for s in stores:
            shutil.rmtree(s, ignore_errors=True)


# ---- NFR-002-04: recovery after the holder is killed -----------------------------------------------------------------
@pytest.mark.req("NFR-002-04")
def test_nfr_002_04_a_new_acquire_succeeds_within_10_seconds_after_the_holder_is_killed(world) -> None:
    from pitstudio.runner import locks

    code = (
        "import sys, time\n"
        "from filelock import FileLock\n"
        "lock = FileLock(sys.argv[1]); lock.acquire(timeout=0)\n"
        "print('READY', flush=True)\n"
        "time.sleep(600)\n"
    )
    holder = subprocess.Popen(
        [sys.executable, "-c", code, str(world.lock_dir / "gpu0.compute")], stdout=subprocess.PIPE, text=True
    )
    try:
        assert holder.stdout.readline().strip() == "READY"
        with pytest.raises(locks.LockTimeout), locks.acquire("gpu0.compute", wait_s=0.3, lock_dir=world.lock_dir):
            pass
        holder.kill()
        holder.wait(10)
        t0 = time.monotonic()
        with locks.acquire("gpu0.compute", wait_s=10, lock_dir=world.lock_dir):
            took = time.monotonic() - t0
        assert took <= 10.0, f"recovery took {took:.1f}s"
    finally:
        if holder.poll() is None:
            holder.kill()
