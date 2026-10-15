"""T-017-050: GPU stages under the runner against the fake GPU backend; time recorded (unit, fake tools, studio
environment).

Requirements: FR-017-50, NFR-017-07.

Spec: specs/017-planning-survey/spec.md
- FR-017-50 (optional): where a CUDA GPU is available, COLMAP dense stereo and Brush training run only through the
  runner
  under `gpu0.compute`, honour `gpu0.hold`, and stop with a recorded reason on a timeout (default 2 h per flight) or
  out-of-memory; these behaviours are verified with the fake GPU backend and fake tool binaries;
- NFR-017-07: reconstruction time per flight <= 2 h (an estimate; recorded in the run manifest).
plan.md test strategy row FR-017-50: the runner's fake GPU backend and fake tool binaries (lock held, hold file,
timeout,
OOM). Constitution principle 12: one job per device at a time under the machine-wide locks; nothing starts while a
`gpu0.hold` file exists.

Oracles:
- the order of events written to one log by the lock (an injected lock factory that logs `lock-enter` /
  `lock-exit`) and by
  the fake tool (`tool-start` / `tool-end`): lock-enter < tool-start < tool-end < lock-exit on success, and the
  lock is
  released after a timeout, an OOM, a failure and an exception (every exit path);
- a `gpu0.hold` file in the lock folder: the stage does not start the tool, takes no lock and reports "held";
- a fake tool that sleeps past a 1 s limit (killed: its heartbeat file stops changing), a fake tool that exits with
  code 3 and
  prints "CUDA error: out of memory" (reason "out of memory"), one that exits with code 1 (status "failed");
- an injected scripted clock: start 100.0 s and end 5,500.0 s give a wall time of 5,400 s (1.5 h), recorded;
- the 2 h limit by hand: 7,200 s accepted, 7,200.001 s an overrun.

Expected public API (module `pitstudio_studio.survey.gpu_stage`, `studio/` environment):
    DEFAULT_TIMEOUT_S = 7200.0
    run_gpu_stage(command: Sequence[str], *, lock_dir: Path, lock_factory, clock, timeout_s: float =
    DEFAULT_TIMEOUT_S,
                  cuda_available: bool = True, env: Mapping[str, str] | None = None, flight: str = "f01") ->
                  StageResult
        - cuda_available False: status "not_run", reason "no CUDA GPU", the tool is not started;
        - a file `lock_dir/gpu0.hold`: status "held", reason containing "gpu0.hold", nothing started, no lock taken;
        - otherwise `with lock_factory(lock_dir / "gpu0.compute"):` runs `command`; wall_s = clock.monotonic() after -
          before (read exactly twice); exit 0 -> "succeeded"; still running after `timeout_s` -> killed, "timeout"
          (reason names the limit in seconds); non-zero exit with "out of memory" (case-insensitive) in its output ->
          "oom" (reason "out of memory"); any other non-zero exit -> "failed"; the lock is released on every path.
        StageResult: status, reason (None on success), wall_s, flight, record (dict for the run manifest:
        {"flight", "status", "reason", "wall_s", "timeout_s"}).
    check_reconstruction_time(wall_s: float, *, limit_s: float = DEFAULT_TIMEOUT_S) -> dict
        {"wall_s", "limit_s", "within_budget": wall_s <= limit_s, "note": None or "overrun"}.
"""

from __future__ import annotations

import contextlib
import inspect
import sys
import textwrap
import time
from pathlib import Path

import pytest
from pitstudio_studio.survey.gpu_stage import DEFAULT_TIMEOUT_S, check_reconstruction_time, run_gpu_stage


class LogLock:
    """An injectable lock factory: logs its enter and exit to the shared event log."""

    def __init__(self, log: Path) -> None:
        self.log = log
        self.paths: list[Path] = []

    def __call__(self, path: Path):
        self.paths.append(path)

        @contextlib.contextmanager
        def held():
            self.log.open("a").write("lock-enter\n")
            try:
                yield
            finally:
                self.log.open("a").write("lock-exit\n")

        return held()


class ScriptedClock:
    def __init__(self, *values: float) -> None:
        self.values = list(values)
        self.reads = 0

    def monotonic(self) -> float:
        self.reads += 1
        return self.values.pop(0)


def _tool(tmp_path: Path, body: str) -> tuple[list[str], Path]:
    script = tmp_path / "tool.py"
    log = tmp_path / "events.log"
    script.write_text(
        "import os, sys, time\nlog = os.environ['EVENT_LOG']\n"
        "open(log, 'a').write('tool-start\\n')\n" + textwrap.dedent(body) + "\nopen(log, 'a').write('tool-end\\n')\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)], log


def _run(tmp_path: Path, body: str, *, clock=None, **kw):
    command, log = _tool(tmp_path, body)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir(exist_ok=True)
    lock = LogLock(log)
    result = run_gpu_stage(
        command,
        lock_dir=lock_dir,
        lock_factory=lock,
        clock=clock or ScriptedClock(100.0, 5500.0),
        env={"EVENT_LOG": str(log)},
        **kw,
    )
    return result, log, lock, lock_dir


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-50
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-50")
def test_a_stage_runs_under_the_gpu0_compute_lock_and_releases_it_afterwards(tmp_path: Path) -> None:
    result, log, lock, lock_dir = _run(tmp_path, "pass")
    assert result.status == "succeeded"
    assert result.reason is None
    assert log.read_text().split() == ["lock-enter", "tool-start", "tool-end", "lock-exit"]
    assert lock.paths == [lock_dir / "gpu0.compute"]


@pytest.mark.req("FR-017-50")
def test_a_gpu0_hold_file_prevents_the_start_and_the_lock(tmp_path: Path) -> None:
    command, log = _tool(tmp_path, "pass")
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    (lock_dir / "gpu0.hold").write_text("maintenance", encoding="utf-8")
    lock = LogLock(log)
    result = run_gpu_stage(
        command, lock_dir=lock_dir, lock_factory=lock, clock=ScriptedClock(0.0, 1.0), env={"EVENT_LOG": str(log)}
    )
    assert result.status == "held"
    assert "gpu0.hold" in result.reason
    assert not log.exists()  # the tool never started and the lock was never taken
    assert lock.paths == []


@pytest.mark.req("FR-017-50")
def test_without_a_cuda_gpu_the_optional_stage_is_not_run(tmp_path: Path) -> None:
    result, log, lock, _ = _run(tmp_path, "pass", cuda_available=False)
    assert result.status == "not_run"
    assert result.reason == "no CUDA GPU"
    assert not log.exists()
    assert lock.paths == []


@pytest.mark.req("FR-017-50")
def test_a_tool_past_the_timeout_is_killed_and_the_lock_is_released(tmp_path: Path) -> None:
    body = (
        "beat = os.environ['EVENT_LOG'] + '.beat'\n"
        "for _ in range(600):\n"
        "    open(beat, 'w').write(str(time.time()))\n"
        "    time.sleep(0.1)\n"
    )
    result, log, _, _ = _run(tmp_path, body, timeout_s=1.0)
    assert result.status == "timeout"
    assert "1" in result.reason
    assert "timeout" in result.reason.lower()
    events = log.read_text().split()
    assert events == ["lock-enter", "tool-start", "lock-exit"]  # killed: no tool-end, lock released
    beat = Path(str(log) + ".beat")
    stamp = beat.read_text()
    time.sleep(0.6)
    assert beat.read_text() == stamp  # the process is gone: the heartbeat no longer changes


@pytest.mark.req("FR-017-50")
def test_an_out_of_memory_exit_is_recorded_with_its_reason(tmp_path: Path) -> None:
    result, log, _, _ = _run(tmp_path, "print('CUDA error: Out Of Memory', file=sys.stderr)\nsys.exit(3)")
    assert result.status == "oom"
    assert result.reason == "out of memory"
    assert log.read_text().split()[-1] == "lock-exit"


@pytest.mark.req("FR-017-50")
def test_any_other_failure_is_a_failed_stage_and_the_lock_is_still_released(tmp_path: Path) -> None:
    result, log, _, _ = _run(tmp_path, "print('segfault?', file=sys.stderr)\nsys.exit(1)")
    assert result.status == "failed"
    assert result.reason
    assert log.read_text().split() == ["lock-enter", "tool-start", "lock-exit"]


@pytest.mark.req("FR-017-50")
def test_the_lock_is_released_when_starting_the_tool_raises(tmp_path: Path) -> None:
    log = tmp_path / "events.log"
    lock = LogLock(log)
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    with pytest.raises((FileNotFoundError, OSError)):
        run_gpu_stage(
            ["definitely-not-a-binary-xyz"], lock_dir=lock_dir, lock_factory=lock, clock=ScriptedClock(0.0, 1.0)
        )
    assert log.read_text().split() == ["lock-enter", "lock-exit"]


@pytest.mark.req("FR-017-50")
def test_the_default_timeout_is_two_hours() -> None:
    assert DEFAULT_TIMEOUT_S == 7200.0
    assert inspect.signature(run_gpu_stage).parameters["timeout_s"].default == 7200.0


# ----------------------------------------------------------------------------------------------------------------------
# NFR-017-07
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("NFR-017-07")
def test_the_wall_time_is_recorded_for_the_run_manifest(tmp_path: Path) -> None:
    clock = ScriptedClock(100.0, 5500.0)
    result, *_ = _run(tmp_path, "pass", clock=clock, flight="f07")
    assert clock.reads == 2
    assert result.wall_s == 5400.0
    assert result.record == {
        "flight": "f07",
        "status": "succeeded",
        "reason": None,
        "wall_s": 5400.0,
        "timeout_s": 7200.0,
    }


@pytest.mark.req("NFR-017-07")
@pytest.mark.parametrize(("wall", "within"), [(5400.0, True), (7200.0, True), (7200.001, False), (20_000.0, False)])
def test_two_hours_is_the_per_flight_budget_and_an_overrun_is_reported(wall: float, within: bool) -> None:
    check = check_reconstruction_time(wall)
    assert check["within_budget"] is within
    assert check["limit_s"] == 7200.0
    assert (check["note"] == "overrun") is (not within)


@pytest.mark.req("NFR-017-07")
def test_a_failed_stage_still_records_its_wall_time(tmp_path: Path) -> None:
    result, *_ = _run(tmp_path, "sys.exit(1)", clock=ScriptedClock(10.0, 40.5))
    assert result.wall_s == 30.5
    assert result.record["wall_s"] == 30.5
    assert result.record["status"] == "failed"
