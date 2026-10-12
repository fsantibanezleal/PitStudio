# ruff: noqa: E501, PT018
"""T-002-094: the in-run thermal guard (US-002-2, G5 review).

Requirement: FR-002-66.

Expected API (module `pitstudio.runner.guards`, stated for the implementer; a pure state machine, one call per telemetry
sample):
  * `ThermalGuard(pause_c=83.0, resume_c=75.0, stop_c=87.0, block_minutes=45.0, cooldown_minutes=10.0, supports_checkpoint=False)`
    (the defaults are the values of FR-002-66; they are the `runner.run_pause_temp_c`, `run_resume_temp_c`, `run_stop_temp_c`,
    `gpu_block_minutes` and `gpu_cooldown_minutes` thresholds, NOT YET in specs/000-foundation/thresholds.yaml: see the red
    report), exposing the attributes `pause_c`, `resume_c`, `stop_c`, `block_minutes`, `cooldown_minutes`;
  * `observe(t_s: float, temp_c: float, hw_error: bool = False) -> ThermalDecision` with `.action` in "run" | "pause" |
    "stop" | "cooldown", `.reason` (None | "thermal" | "hw-error" | "block"), `.checkpoint` (True when the action is "stop" and
    the stage supports checkpoints), `.exit_code` (5 for "stop", else None) and, for "cooldown", `.resume_at_s`;
  * rules: temperature >= pause_c pauses at the next step boundary and the pause lasts until temperature <= resume_c (a
    pause is not left in between); temperature >= stop_c, or `hw_error=True` (a new WHEA/PCIe AER event for the GPU during
    the stage), stops the stage: reason `thermal` / `hw-error`, exit code 5, checkpoint first when supported, and every later
    observation is "stop" too; continuous GPU time per block is capped at `block_minutes`, followed by `cooldown_minutes`
    of cool-down ("cooldown" with `resume_at_s`), after which a new block starts;
  * command line: a stage whose GPU reaches the stop temperature is ended by the runner within seconds, the job exits 5 and the
    reason `thermal` is recorded (stdout or events), the stage process is gone and the GPU lock is released.
Oracles: the scripted sequence 70, 84, 80, 76, 74, 88 C of the plan (hand-derived actions), exact boundary values, a
fake device with a scripted temperature.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import recipe, stage


def guard(**kw):
    from pitstudio.runner import guards

    return guards.ThermalGuard(**kw)


def run_seq(g, temps: list[float], hz: float = 1.0) -> list:
    return [g.observe(i / hz, t) for i, t in enumerate(temps)]


@pytest.mark.req("FR-002-66")
def test_fr_002_66_defaults_are_the_documented_values() -> None:
    g = guard()
    assert (g.pause_c, g.resume_c, g.stop_c, g.block_minutes, g.cooldown_minutes) == (83, 75, 87, 45, 10)


@pytest.mark.req("FR-002-66")
def test_fr_002_66_the_scripted_sequence_pauses_holds_resumes_and_stops() -> None:
    g = guard()
    out = run_seq(g, [70, 84, 80, 76, 74, 88])
    assert [d.action for d in out] == ["run", "pause", "pause", "pause", "run", "stop"], (
        "pause at 84; 80 and 76 are above 75: still paused; resume at 74; stop at 88"
    )
    assert [d.reason for d in out] == [None, None, None, None, None, "thermal"]
    assert out[-1].exit_code == 5 and all(d.exit_code is None for d in out[:-1])
    assert out[-1].checkpoint is False, "this stage has no checkpoint to save"
    assert guard().observe(0, 60).action == "run"


@pytest.mark.req("FR-002-66")
@pytest.mark.parametrize(
    ("temps", "actions"),
    [
        ([82.99, 83.0, 83.01], ["run", "pause", "pause"]),  # the pause threshold is inclusive
        ([84, 75.01, 75.0], ["pause", "pause", "run"]),  # the resume threshold is inclusive; just above it stays paused
        ([84, 86.99, 87.0], ["pause", "pause", "stop"]),  # a paused stage still stops at the stop temperature
        ([60, 86.99, 87.0, 40], ["run", "pause", "stop", "stop"]),  # stop is final even when the GPU cools
        ([87.0], ["stop"]),  # straight to stop
        ([100.0, 30.0], ["stop", "stop"]),
        ([83, 75, 83, 75, 83], ["pause", "run", "pause", "run", "pause"]),  # repeated cycles
        (
            [74, 76, 82, 82.9, 40],
            ["run", "run", "run", "run", "run"],
        ),  # between resume and pause while running: no action
        (
            [84, 80, 75, 80, 70],
            ["pause", "pause", "run", "run", "run"],
        ),  # after resuming at 75, 80 is below the pause threshold: runs
    ],
)
def test_fr_002_66_thresholds_are_exact_and_hysteresis_holds(temps: list[float], actions: list[str]) -> None:
    out = run_seq(guard(), temps)
    assert [d.action for d in out] == actions


@pytest.mark.req("FR-002-66")
@pytest.mark.parametrize("supports", [True, False])
@pytest.mark.parametrize(
    ("temp", "err", "reason"),
    [(88.0, False, "thermal"), (60.0, True, "hw-error"), (87.0, False, "thermal"), (30.0, True, "hw-error")],
)
def test_fr_002_66_a_stop_saves_a_checkpoint_first_only_when_the_stage_supports_one(
    supports: bool, temp: float, err: bool, reason: str
) -> None:
    g = guard(supports_checkpoint=supports)
    assert g.observe(0, 60).action == "run"
    d = g.observe(1, temp, hw_error=err)
    assert (d.action, d.reason, d.exit_code, d.checkpoint) == ("stop", reason, 5, supports)
    for later in (g.observe(2, 40), g.observe(3, 95, hw_error=False), g.observe(4, 40, hw_error=True)):
        assert later.action == "stop", "no step may run after a stop condition"
        assert later.exit_code == 5


@pytest.mark.req("FR-002-66")
def test_fr_002_66_a_hardware_error_event_stops_even_a_cool_gpu_and_a_paused_one() -> None:
    g = guard()
    assert [d.action for d in run_seq(g, [84, 80])] == ["pause", "pause"]
    d = g.observe(2, 79, hw_error=True)
    assert (d.action, d.reason, d.exit_code) == ("stop", "hw-error", 5)
    assert guard().observe(0, 20.0, hw_error=True).reason == "hw-error"


@pytest.mark.req("FR-002-66")
def test_fr_002_66_a_45_minute_block_is_followed_by_a_10_minute_cooldown_and_a_new_block() -> None:
    g = guard()
    block, cool = 45 * 60, 10 * 60
    actions: dict[int, str] = {}
    resume_at = None
    for t in range(0, 2 * block + cool + 5):
        d = g.observe(float(t), 60.0)
        actions[t] = d.action
        if d.action == "cooldown":
            assert d.reason == "block" and d.exit_code is None
            resume_at = resume_at if resume_at is not None else d.resume_at_s
    first_cool = min(t for t, a in actions.items() if a == "cooldown")
    assert block <= first_cool <= block + 1, (
        f"the cap is 45 minutes of continuous GPU time, saw cooldown at t={first_cool}"
    )
    assert all(actions[t] == "run" for t in range(0, first_cool))
    assert resume_at is not None and first_cool + cool - 1 <= resume_at <= first_cool + cool + 1
    first_run_again = min(t for t, a in actions.items() if t > first_cool and a == "run")
    assert first_cool + cool <= first_run_again <= first_cool + cool + 1, (
        f"cooldown lasts 10 minutes, ran again at {first_run_again}"
    )
    assert all(actions[t] == "cooldown" for t in range(first_cool, first_run_again))
    second_cool = min((t for t, a in actions.items() if t > first_run_again and a == "cooldown"), default=None)
    assert second_cool is not None and block <= second_cool - first_run_again <= block + 1, (
        "a new 45-minute block starts after the cooldown"
    )


@pytest.mark.req("FR-002-66")
def test_fr_002_66_a_cooldown_does_not_override_a_stop() -> None:
    g = guard()
    for t in range(0, 45 * 60):
        g.observe(float(t), 60.0)
    assert g.observe(45 * 60.0, 60.0).action == "cooldown"
    d = g.observe(45 * 60.0 + 1, 90.0)
    assert d.action == "stop" and d.reason == "thermal"


# ---- on the command line -----------------------------------------------------------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(
        monkeypatch, tmp_path, device=rw.device_doc(temp_c=[[0, 50], [6, 90]])
    )  # cool for the first 6 s of the backend's life
    yield w
    rw.cleanup_world(w)


@pytest.mark.req("FR-002-66")
def test_fr_002_66_a_stage_on_a_gpu_that_reaches_the_stop_temperature_is_ended_with_exit_5_and_reason_thermal(
    world,
) -> None:
    world.set_guards(cooldown_wait_s=0)
    world.write_recipe(
        recipe(
            "toohot",
            [
                stage(
                    "st50_physics",
                    gpu="exclusive",
                    vram=2.0,
                    timeout_s=120,
                    params={"mode": "grandchild", "sleep_s": 60},
                )
            ],
        )
    )
    t0 = time.monotonic()
    r = world.run("toohot")
    elapsed = time.monotonic() - t0
    assert r.code == 5, r.text
    assert elapsed < 40, f"the runner must react within seconds of the 87 C sample, took {elapsed:.1f}s"
    texts = r.text + " ".join(str(e) for e in world.events()) + str(world.manifest())
    assert "thermal" in texts
    rows = world.ledger_rows()
    pids = [x["pid"] for x in rows if x["event"] == "start"] + [
        x["child_pid"] for x in rows if x["event"] == "grandchild"
    ]
    assert pids, "the stage did start (the GPU was cool at the start)"
    deadline = time.monotonic() + 10
    while (
        any(psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE for p in pids)
        and time.monotonic() < deadline
    ):
        time.sleep(0.1)
    assert not any(psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE for p in pids), (
        "the stage tree is gone"
    )
    from filelock import FileLock

    with FileLock(world.lock_dir / "gpu0.compute", timeout=0):
        pass
