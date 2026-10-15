# ruff: noqa: E501, PT018
"""T-002-095: the thermal guard never resumes above the resume temperature and never runs past a stop condition (P-002-13).

Requirement: P-002-13 (refines FR-002-66).

Expected API: `pitstudio.runner.guards.ThermalGuard` as in tests/unit/test_t_002_094_thermal_guard.py (`observe(t_s, temp_c,
hw_error=False) -> decision` with `.action` "run" | "pause" | "stop" | "cooldown", `.reason`, `.checkpoint`, `.exit_code`);
the 45-minute block cap is made irrelevant here by a very large `block_minutes`.
Oracle: a reference state machine written from the requirement text (not from the guard), driven over the same sequence;
plus the two safety invariants stated directly.
Input domain: temperatures in [30, 100] C at telemetry_hz in [1, 4], with and without hardware-error events; the first test
keeps hardware errors on samples below the stop temperature so that the choice between the two stop reasons is not exercised
(the requirement does not rank them).
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

PAUSE, RESUME, STOP = 83.0, 75.0, 87.0


def make(supports: bool):
    from pitstudio.runner import guards

    return guards.ThermalGuard(
        pause_c=PAUSE,
        resume_c=RESUME,
        stop_c=STOP,
        block_minutes=10**6,
        cooldown_minutes=10,
        supports_checkpoint=supports,
    )


def reference(steps: list[tuple[float, bool]]) -> list[tuple[str, str | None]]:
    """Reference machine (FR-002-66 transcribed): returns (action, reason) per sample."""
    out: list[tuple[str, str | None]] = []
    state, stopped, why = "run", False, None
    for temp, err in steps:
        if stopped:
            out.append(("stop", why))
        elif err:
            stopped, why = True, "hw-error"
            out.append(("stop", why))
        elif temp >= STOP:
            stopped, why = True, "thermal"
            out.append(("stop", why))
        elif state == "pause":
            if temp <= RESUME:
                state = "run"
            out.append((state, None))
        else:
            if temp >= PAUSE:
                state = "pause"
            out.append((state, None))
    return out


temps = st.floats(30.0, 100.0, allow_nan=False)
rare_error = st.integers(0, 6).map(lambda n: n == 0)  # about one sample in seven is a hardware-error event


@pytest.mark.req("P-002-13")
@settings(max_examples=300, deadline=None)
@given(
    steps=st.lists(st.tuples(temps, rare_error), min_size=1, max_size=80),
    hz=st.floats(1.0, 4.0),
    supports=st.booleans(),
)
def test_p_002_13_the_guard_agrees_with_the_reference_state_machine_on_every_step(
    steps: list[tuple[float, bool]], hz: float, supports: bool
) -> None:
    for temp, err in steps:
        assume(not (err and temp >= STOP))
    g = make(supports)
    got = [g.observe(i / hz, temp, hw_error=err) for i, (temp, err) in enumerate(steps)]
    assert [(d.action, d.reason) for d in got] == reference(steps)


@pytest.mark.req("P-002-13")
@settings(max_examples=300, deadline=None)
@given(
    steps=st.lists(st.tuples(temps, rare_error), min_size=1, max_size=120),
    hz=st.floats(1.0, 4.0),
    supports=st.booleans(),
)
def test_p_002_13_never_resumes_above_the_resume_temperature_and_never_runs_after_a_stop(
    steps: list[tuple[float, bool]], hz: float, supports: bool
) -> None:
    g = make(supports)
    prev = "run"
    stopped_at: int | None = None
    for i, (temp, err) in enumerate(steps):
        d = g.observe(i / hz, temp, hw_error=err)
        if prev == "pause" and d.action == "run":
            assert temp <= RESUME, f"resumed at {temp} C (> {RESUME}) after a pause"
        if d.action == "run":
            assert temp < PAUSE and temp < STOP and not err, (
                f"a step may run at {temp} C (error event: {err}) only below the pause temperature"
            )
        if stopped_at is not None:
            assert d.action == "stop", f"a step ran at sample {i} after the stop at sample {stopped_at}"
        if d.action == "stop":
            if stopped_at is None:
                stopped_at = i
                assert err or temp >= STOP, "a stop needs a stop condition on that very sample"
            assert d.exit_code == 5 and d.reason in ("thermal", "hw-error")
            assert d.checkpoint is supports, "a stage that supports checkpoints saves one when it stops"
        prev = d.action


@pytest.mark.req("P-002-13")
@settings(max_examples=200, deadline=None)
@given(series=st.lists(st.floats(30.0, 86.99, allow_nan=False), min_size=1, max_size=100))
def test_p_002_13_without_stop_conditions_a_pause_starts_only_at_83_c_or_more(series: list[float]) -> None:
    g = make(False)
    paused = False
    for i, t in enumerate(series):
        d = g.observe(float(i), t)
        assert d.action in ("run", "pause")
        if d.action == "pause" and not paused:
            assert t >= PAUSE, "a pause starts only at or above the pause temperature"
        paused = d.action == "pause"
