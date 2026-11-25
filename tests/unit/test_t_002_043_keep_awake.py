# ruff: noqa: PT018
"""T-002-043: keep the machine awake while the queue is busy (Windows, profile `keep_awake: true`).

Requirement: FR-002-29.

Expected API: `pitstudio.runner.oswin.set_thread_execution_state(flags: int) -> int` wraps kernel32
`SetThreadExecutionState` (the attribute exists on every OS; it is only called on Windows). The worker calls it with
ES_CONTINUOUS | ES_SYSTEM_REQUIRED (0x80000001) while the queue holds a queued or running job, and with ES_CONTINUOUS
(0x80000000) when the queue becomes empty and on every exit path (success, stage failure, exception). It is never
called when the profile says `keep_awake: false`, nor on Linux.
Oracle: the Win32 documentation values written out by hand (ES_CONTINUOUS = 0x80000000, ES_SYSTEM_REQUIRED = 0x00000001)
and a spy on the binding.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
KEEP = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
RELEASE = ES_CONTINUOUS
assert KEEP == 0x80000001


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    from pitstudio.runner import oswin

    calls: list[int] = []

    def fake(flags: int) -> int:
        calls.append(flags)
        return ES_CONTINUOUS

    monkeypatch.setattr(oswin, "set_thread_execution_state", fake)
    return calls


def world_with(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, keep_awake: bool, recipes: list[dict]):
    prof = rw.profile_doc(keep_awake=keep_awake)
    return rw.make_world(monkeypatch, tmp_path, profile=prof, recipes=recipes)


@pytest.mark.req("FR-002-29")
def test_fr_002_29_busy_queue_sets_the_flags_and_empty_queue_clears_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spy: list[int]
) -> None:
    w = world_with(monkeypatch, tmp_path, rw.IS_WINDOWS, [recipe("calm", [stage("s10_preprocess")])])
    try:
        assert w.run("calm").code == 0
        assert spy == ([KEEP, RELEASE] if rw.IS_WINDOWS else []), f"call sequence {[hex(c) for c in spy]}"
    finally:
        rw.cleanup_world(w)


@pytest.mark.req("FR-002-29")
def test_fr_002_29_the_flags_are_cleared_after_a_failed_stage_and_a_cancelled_or_refused_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spy: list[int]
) -> None:
    w = world_with(
        monkeypatch,
        tmp_path,
        rw.IS_WINDOWS,
        [
            recipe("bad", [stage("s10_preprocess", params={"mode": "fail"})]),
            recipe("refused", [stage("st50_physics", gpu="exclusive", vram=60.0)]),
        ],
    )
    try:
        assert w.run("bad").code == 1
        assert w.run("refused").code == 5
        if rw.IS_WINDOWS:
            assert spy and spy[0] == KEEP and spy[-1] == RELEASE
            assert set(spy) == {KEEP, RELEASE}
            assert spy.count(KEEP) == spy.count(RELEASE), "every acquire is matched by a release"
        else:
            assert spy == []
    finally:
        rw.cleanup_world(w)


@pytest.mark.req("FR-002-29")
def test_fr_002_29_the_flags_are_cleared_even_when_the_run_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spy: list[int]
) -> None:
    w = world_with(monkeypatch, tmp_path, rw.IS_WINDOWS, [recipe("boom", [stage("s10_preprocess")])])
    try:
        import subprocess

        def exploding(*a: object, **k: object) -> None:
            raise RuntimeError("cannot start any process")

        monkeypatch.setattr(subprocess, "Popen", exploding)
        with contextlib.suppress(Exception):
            w.run("boom")
        if rw.IS_WINDOWS:
            assert spy and spy[-1] == RELEASE and spy.count(KEEP) == spy.count(RELEASE) >= 1
        else:
            assert spy == []
    finally:
        rw.cleanup_world(w)


@pytest.mark.req("FR-002-29")
def test_fr_002_29_a_worker_draining_two_jobs_keeps_the_machine_awake_between_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spy: list[int]
) -> None:
    w = world_with(
        monkeypatch,
        tmp_path,
        rw.IS_WINDOWS,
        [recipe("first", [stage("s10_preprocess")]), recipe("second", [stage("st10_terrain")])],
    )
    try:
        assert w.run("first", "--detach").code == 0
        assert w.run("second", "--detach").code == 0
        assert spy == [], "enqueueing alone does not need the keep-awake request"
        assert w.cli("worker").code == 0
        if rw.IS_WINDOWS:
            assert spy[0] == KEEP and spy[-1] == RELEASE
            # the queue is never empty between the two jobs, so the machine is not released in between
            assert spy.count(RELEASE) == 1 and RELEASE not in spy[:-1], [hex(c) for c in spy]
        else:
            assert spy == []
        assert len(w.starts()) == 2
    finally:
        rw.cleanup_world(w)


@pytest.mark.req("FR-002-29")
def test_fr_002_29_profiles_without_keep_awake_never_call_the_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, spy: list[int]
) -> None:
    w = world_with(monkeypatch, tmp_path, False, [recipe("calm", [stage("s10_preprocess")])])
    try:
        assert w.run("calm").code == 0
        assert spy == []
    finally:
        rw.cleanup_world(w)
