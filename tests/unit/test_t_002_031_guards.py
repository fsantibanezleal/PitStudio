# ruff: noqa: E501, PT018
"""T-002-031: pre-flight guards: VRAM, temperature, disk, quota, capabilities, no GPU (US-002-2).

Requirements: FR-002-19, FR-002-20, FR-002-21, FR-002-22, P-002-10, DC-002-06.

Expected API (module `pitstudio.runner.guards`, pure functions, stated for the implementer):
  * `vram_ok(free_bytes: int, vram_gib_est: float, margin_gib: float) -> bool`:
    free_bytes >= ceil(vram_gib_est * 2**30) + margin_gib * 2**30;
  * `disk_ok(free_bytes: int, disk_gib_est: float, margin_gib: float) -> bool`: the same rule for the store volume;
  * `quota_ok(stored_bytes: int, disk_gib_est: float, quota_gib: float) -> bool`:
    stored_bytes + ceil(disk_gib_est * 2**30) <= quota_gib * 2**30;
  * `temp_ok(temp_c: float, max_start_temp_c: float) -> bool`: temp_c <= max_start_temp_c;
  * `wait_for_cooldown(read_temp, max_start_temp_c: float, cooldown_wait_s: float, *, clock) -> bool`: True at once when
    cool; else polls every 10 s (`clock.sleep(10)`) for up to `cooldown_wait_s`, True as soon as `read_temp()` <= max;
  * `capability_refusal(path: Path, requires: list[str], driver: str) -> str | None`: None when every listed probe is
    `pass` in a valid report whose `driver` equals `driver`; otherwise `"capability"` (missing, invalid, probe absent
    or not `pass`) or `"capability-stale"` (valid report of another driver);
  * command line: a refused stage exits 5, starts no process and records a `guard-refused` event whose `data.reason`
    (or `detail`) is vram | temp | disk | quota | capability | capability-stale | no-gpu; CPU stages ignore the GPU
    guards; an unavailable GPU backend (`init_error: true`) refuses GPU stages with `no-gpu` and runs CPU stages.
Oracles: hand calculation of every threshold with integers (2**30 B = 1 GiB), a fake clock, hand-built capability
reports, the monotonicity law of P-002-10, the fake device and the fake disk of tests/support/runner_world.py.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import runner_world as rw
from runner_world import GIB, FakeClock, recipe, stage


def need(est_gib: float, margin_gib: float) -> float:
    """Reference rule: ceil(est * 2**30) + margin * 2**30 (multiplying a float by 2**30 is exact)."""
    return math.ceil(est_gib * GIB) + margin_gib * GIB


# ---- FR-002-19: VRAM and temperature -----------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-19")
@pytest.mark.parametrize(
    ("free", "est", "margin", "ok"),
    [
        (8053063680, 6.0, 1.5, True),  # 6 GiB + 1.5 GiB = 8,053,063,680 exactly
        (8053063679, 6.0, 1.5, False),  # one byte short
        (8053063681, 6.0, 1.5, True),
        (107374183 + 1610612736, 0.1, 1.5, True),  # ceil(0.1 * 2**30) = 107,374,183 (0.1 GiB = 107,374,182.4 B)
        (107374182 + 1610612736, 0.1, 1.5, False),
        (0, 0.001, 1.5, False),
        (10**15, 256.0, 256.0, True),
        (2 * GIB, 0.5, 1.5, True),
        (2 * GIB - 1, 0.5, 1.5, False),
    ],
)
def test_fr_002_19_vram_rule_hand_calculated(free: int, est: float, margin: float, ok: bool) -> None:
    from pitstudio.runner import guards

    assert (free >= need(est, margin)) == ok  # the oracle itself
    assert guards.vram_ok(free, est, margin) is ok


@pytest.mark.req("FR-002-19")
@pytest.mark.parametrize(
    ("temp", "limit", "ok"),
    [
        (80, 80, True),
        (80.0001, 80, False),
        (79.9, 80, True),
        (0, 80, True),
        (200, 80, False),
        (60, 60, True),
        (60.5, 60, False),
    ],
)
def test_fr_002_19_temperature_boundary(temp: float, limit: float, ok: bool) -> None:
    from pitstudio.runner import guards

    assert guards.temp_ok(temp, limit) is ok


@pytest.mark.req("FR-002-19")
def test_fr_002_19_cooldown_polls_every_10_seconds_until_cool_or_out_of_time() -> None:
    from pitstudio.runner import guards

    # cool at once: no waiting
    clock = FakeClock()
    assert guards.wait_for_cooldown(lambda: 70.0, 80, 600, clock=clock) is True and clock.sleeps == []

    # hot, becomes cool at t = 15: polls at 10 (hot) and 20 (cool)
    clock = FakeClock()
    assert guards.wait_for_cooldown(lambda: 90.0 if clock.t < 15 else 75.0, 80, 600, clock=clock) is True
    assert clock.sleeps == [10, 10]

    # exactly at the limit counts as cool
    clock = FakeClock()
    assert guards.wait_for_cooldown(lambda: 85.0 if clock.t < 10 else 80.0, 80, 600, clock=clock) is True
    assert clock.sleeps == [10]

    # never cools: gives up within the allowed time
    clock = FakeClock()
    assert guards.wait_for_cooldown(lambda: 95.0, 80, 35, clock=clock) is False
    assert len(clock.sleeps) >= 3 and all(0 < s <= 10 for s in clock.sleeps) and sum(clock.sleeps) <= 35 + 1e-9

    # no allowance at all: refuse at once
    clock = FakeClock()
    assert guards.wait_for_cooldown(lambda: 95.0, 80, 0, clock=clock) is False and clock.sleeps == []


# ---- FR-002-20: disk and quota ---------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-20")
@pytest.mark.parametrize(
    ("free", "est", "margin", "ok"),
    [
        (22 * GIB, 2.0, 20, True),
        (22 * GIB - 1, 2.0, 20, False),
        (20 * GIB + math.ceil(0.25 * GIB), 0.25, 20, True),
        (20 * GIB + math.ceil(0.25 * GIB) - 1, 0.25, 20, False),
        (21 * GIB, 0.0, 20, True),
        (20 * GIB - 1, 0.0, 20, False),
    ],
)
def test_fr_002_20_disk_rule_hand_calculated(free: int, est: float, margin: float, ok: bool) -> None:
    from pitstudio.runner import guards

    assert (free >= need(est, margin)) == ok
    assert guards.disk_ok(free, est, margin) is ok


@pytest.mark.req("FR-002-20")
@pytest.mark.parametrize(
    ("stored", "est", "quota", "ok"),
    [
        (79 * GIB, 1.0, 80, True),
        (79 * GIB + 1, 1.0, 80, False),
        (0, 80.0, 80, True),
        (0, 80.000001, 80, False),
        (30 * GIB, 0.0, 30, True),
        (30 * GIB + 1, 0.0, 30, False),
    ],
)
def test_fr_002_20_quota_rule_hand_calculated(stored: int, est: float, quota: float, ok: bool) -> None:
    from pitstudio.runner import guards

    assert (stored + math.ceil(est * GIB) <= quota * GIB) == ok
    assert guards.quota_ok(stored, est, quota) is ok


# ---- P-002-10: monotonicity ----------------------------------------------------------------------------------------------------
@pytest.mark.req("P-002-10")
@settings(max_examples=300, deadline=None)
@given(
    free=st.integers(0, 2**50),
    delta=st.integers(0, 2**40),
    est=st.floats(0.0, 300.0, allow_nan=False),
    bigger=st.floats(0.0, 300.0, allow_nan=False),
    margin=st.sampled_from([1.5, 2.0, 20.0, 64.0]),
)
def test_p_002_10_more_free_space_never_turns_a_pass_into_a_refusal_and_a_bigger_estimate_never_the_reverse(
    free: int, delta: int, est: float, bigger: float, margin: float
) -> None:
    from pitstudio.runner import guards

    big = est + bigger
    for rule in (guards.vram_ok, guards.disk_ok):
        assert rule(free, est, margin) == (free >= need(est, margin))
        if rule(free, est, margin):
            assert rule(free + delta, est, margin), "more free space must not refuse"
        if not rule(free, est, margin):
            assert not rule(free, big, margin), "a larger estimate must not pass"
            assert not rule(max(free - delta, 0), est, margin), "less free space must not pass"
        if rule(free, big, margin):
            assert rule(free, est, margin), "a smaller estimate must not refuse"


@pytest.mark.req("P-002-10")
@settings(max_examples=300, deadline=None)
@given(
    t=st.floats(-50, 150, allow_nan=False),
    cooler=st.floats(0, 100, allow_nan=False),
    limit=st.floats(0, 80, allow_nan=False),
)
def test_p_002_10_a_lower_temperature_never_turns_a_pass_into_a_refusal(t: float, cooler: float, limit: float) -> None:
    from pitstudio.runner import guards

    if guards.temp_ok(t, limit):
        assert guards.temp_ok(t - cooler, limit)
    if not guards.temp_ok(t, limit):
        assert not guards.temp_ok(t + cooler, limit)


@pytest.mark.req("P-002-10")
@settings(max_examples=200, deadline=None)
@given(
    stored=st.integers(0, 2**45),
    more=st.integers(0, 2**40),
    est=st.floats(0, 100, allow_nan=False),
    quota=st.floats(0.5, 10000, allow_nan=False),
)
def test_p_002_10_quota_is_monotone_in_stored_bytes_and_estimate(
    stored: int, more: int, est: float, quota: float
) -> None:
    from pitstudio.runner import guards

    if not guards.quota_ok(stored, est, quota):
        assert not guards.quota_ok(stored + more, est, quota)
    if guards.quota_ok(stored + more, est, quota):
        assert guards.quota_ok(stored, est, quota)


# ---- FR-002-21 / DC-002-06: capabilities ---------------------------------------------------------------------------------------
DRIVER = rw.DRIVER


def caps(**over: Any) -> dict[str, Any]:
    return {**rw.capabilities_doc(), **over}


CAP_CASES: list[tuple[str, Any, list[str], str | None]] = [
    ("all-pass", caps(), ["warp_newton", "nvenc"], None),
    ("no-probes-required", caps(), [], None),
    ("probe-absent", caps(), ["warp_newton", "isaacsim"], "capability"),
    (
        "probe-fail",
        caps(probes={"warp_newton": {"status": "fail", "versions": {}, "error": "boom"}}),
        ["warp_newton"],
        "capability",
    ),
    (
        "probe-skip",
        caps(probes={"warp_newton": {"status": "skip", "versions": {}, "notes": ["not written"]}}),
        ["warp_newton"],
        "capability",
    ),
    ("stale-driver", caps(driver="570.12"), ["warp_newton"], "capability-stale"),
    ("invalid-schema", {"driver": DRIVER, "probes": "nope"}, ["warp_newton"], "capability"),
    ("empty-object", {}, ["warp_newton"], "capability"),
    ("probes-null", caps(probes=None), ["warp_newton"], "capability"),
    ("list-document", [1, 2], ["warp_newton"], "capability"),
]


@pytest.mark.req("FR-002-21")
@pytest.mark.parametrize(("label", "doc", "requires", "expected"), CAP_CASES, ids=[c[0] for c in CAP_CASES])
def test_fr_002_21_capability_report_rules(
    tmp_path: Path, label: str, doc: Any, requires: list[str], expected: str | None
) -> None:
    from pitstudio.runner import guards

    p = tmp_path / "capabilities.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert guards.capability_refusal(p, requires, DRIVER) == expected


@pytest.mark.req("FR-002-21")
@pytest.mark.parametrize(
    "body",
    [None, b"", b"{truncated", b"\xff\xfe", b"NaN", b'{"driver": NaN}', b"\xef\xbb\xbf{}", b"[]" * 100000],
    ids=["missing", "empty", "truncated", "binary", "nan", "nan-field", "bom", "huge"],
)
def test_fr_002_21_missing_or_unreadable_report_is_a_refusal_not_a_crash(tmp_path: Path, body: bytes | None) -> None:
    from pitstudio.runner import guards

    p = tmp_path / "capabilities.json"
    if body is not None:
        p.write_bytes(body)
    assert guards.capability_refusal(p, ["warp_newton"], DRIVER) == "capability"


# ---- the guards on the command line ----------------------------------------------------------------------------------------------
@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    w = rw.make_world(monkeypatch, tmp_path)
    yield w
    rw.cleanup_world(w)


def refusal_reason(world: rw.World) -> str | None:
    for e in world.events():
        if e["type"] == "guard-refused":
            data = e.get("data") or {}
            return data.get("reason") or e.get("detail")
    return None


def gpu_recipe(
    name: str = "gpu", *, vram: float = 6.0, disk: float = 0.001, requires: list[str] | None = None
) -> dict[str, Any]:
    return recipe(name, [stage("st50_physics", gpu="exclusive", vram=vram, disk=disk, requires=requires)])


@pytest.mark.req("FR-002-19")
@pytest.mark.parametrize(
    ("free", "code"), [(math.ceil(6.0 * GIB) + int(1.5 * GIB), 0), (math.ceil(6.0 * GIB) + int(1.5 * GIB) - 1, 5)]
)
def test_fr_002_19_vram_guard_on_the_command_line(world, free: int, code: int) -> None:
    world.write_device(rw.device_doc(free_bytes=free))
    world.write_recipe(gpu_recipe())
    r = world.run("gpu")
    assert r.code == code, r.text
    if code == 5:
        assert refusal_reason(world) == "vram"
        assert world.ledger_rows() == [], "a refused stage starts no process"
        from filelock import FileLock

        for name in ("gpu0.compute", "gpu0.nvenc"):
            with FileLock(world.lock_dir / name, timeout=0):
                pass


@pytest.mark.req("FR-002-19")
def test_fr_002_19_a_too_hot_gpu_is_refused_with_reason_temp_when_there_is_no_cooldown_allowance(world) -> None:
    world.set_guards(cooldown_wait_s=0)
    world.write_device(rw.device_doc(temp_c=80.5))
    world.write_recipe(gpu_recipe())
    r = world.run("gpu")
    assert r.code == 5, r.text
    assert refusal_reason(world) == "temp" and world.ledger_rows() == []
    world.write_device(rw.device_doc(temp_c=80))
    import time

    time.sleep(1.1)
    assert world.run("gpu").code == 0


@pytest.mark.req("FR-002-19")
def test_fr_002_19_a_gpu_that_cools_down_within_the_allowance_is_used(world) -> None:
    # hot for the first 0.2 s of the backend's life, then cool; the guard polls (every 10 s) at most cooldown_wait_s
    world.set_guards(cooldown_wait_s=30)
    world.write_device(rw.device_doc(temp_c=[[0, 85], [0.2, 60]]))
    world.write_recipe(gpu_recipe())
    import time

    t0 = time.monotonic()
    r = world.run("gpu")
    assert r.code == 0, r.text
    assert time.monotonic() - t0 < 30
    assert len(world.starts()) == 1


@pytest.mark.req("FR-002-20")
@pytest.mark.parametrize(("free", "code"), [(22 * GIB, 0), (22 * GIB - 1, 5)])
def test_fr_002_20_disk_guard_applies_to_every_stage_including_cpu_stages(world, free: int, code: int) -> None:
    world.write_recipe(recipe("cpu-disk", [stage("s10_preprocess", disk=2.0)]))
    world.set_free_disk(free)
    r = world.run("cpu-disk")
    assert r.code == code, r.text
    if code == 5:
        assert refusal_reason(world) == "disk" and world.ledger_rows() == []


@pytest.mark.req("FR-002-20")
def test_fr_002_20_quota_guard_refuses_a_stage_whose_estimate_alone_exceeds_its_quota(world) -> None:
    world.write_profile(rw.profile_doc(quotas={"st50_physics": 0.5}))
    world.write_recipe(gpu_recipe(disk=1.0))
    r = world.run("gpu")
    assert r.code == 5, r.text
    assert refusal_reason(world) == "quota" and world.ledger_rows() == []
    world.write_profile(rw.profile_doc(quotas={"st50_physics": 1.0}))
    import time

    time.sleep(1.1)
    assert world.run("gpu").code == 0


@pytest.mark.req("FR-002-21")
@pytest.mark.parametrize(
    ("label", "doc", "reason"),
    [
        ("probe-absent", caps(probes={"nvenc": {"status": "pass", "versions": {}}}), "capability"),
        ("probe-failed", caps(probes={"warp_newton": {"status": "fail", "versions": {}, "error": "x"}}), "capability"),
        ("stale", caps(driver="1.2.3"), "capability-stale"),
        ("invalid", {"nonsense": True}, "capability"),
    ],
)
def test_fr_002_21_capability_guard_on_the_command_line(world, label: str, doc: Any, reason: str) -> None:
    (world.repo / "studio" / "capabilities.json").write_text(json.dumps(doc), encoding="utf-8")
    world.write_recipe(gpu_recipe(requires=["warp_newton"]))
    r = world.run("gpu")
    assert r.code == 5, r.text
    assert refusal_reason(world) == reason and world.ledger_rows() == []


@pytest.mark.req("FR-002-21")
def test_fr_002_21_a_missing_report_refuses_and_a_valid_one_passes(world) -> None:
    world.write_recipe(gpu_recipe(requires=["warp_newton"]))
    (world.repo / "studio" / "capabilities.json").unlink()
    assert world.run("gpu").code == 5
    assert refusal_reason(world) == "capability"
    (world.repo / "studio" / "capabilities.json").write_text(json.dumps(rw.capabilities_doc()), encoding="utf-8")
    import time

    time.sleep(1.1)
    assert world.run("gpu").code == 0


@pytest.mark.req("FR-002-21")
def test_fr_002_21_stages_without_requires_do_not_consult_the_report(world) -> None:
    (world.repo / "studio" / "capabilities.json").write_text("{broken", encoding="utf-8")
    world.write_recipe(gpu_recipe())
    assert world.run("gpu").code == 0


# ---- FR-002-22: no GPU --------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-002-22")
def test_fr_002_22_without_a_gpu_backend_gpu_stages_are_refused_and_cpu_stages_run(world) -> None:
    doc = rw.device_doc()
    doc["init_error"] = True
    world.write_device(doc)
    world.write_recipe(gpu_recipe("gpu"))
    world.write_recipe(recipe("cpu", [stage("s10_preprocess")]))
    r = world.run("gpu")
    assert r.code == 5, r.text
    assert refusal_reason(world) == "no-gpu" and world.ledger_rows() == []
    import time

    time.sleep(1.1)
    r = world.run("cpu")
    assert r.code == 0, r.text
    assert len(world.starts()) == 1
    assert world.manifest()["gpu"] is None


@pytest.mark.req("FR-002-22")
def test_fr_002_22_a_mixed_job_runs_its_cpu_stage_then_refuses_the_gpu_stage(world) -> None:
    doc = rw.device_doc()
    doc["init_error"] = True
    world.write_device(doc)
    world.write_recipe(
        recipe(
            "mixed",
            [
                stage("s10_preprocess"),
                stage("st50_physics", gpu="exclusive", vram=2.0, inputs=[rw.up("s10_preprocess", "out.bin")]),
            ],
        )
    )
    r = world.run("mixed")
    assert r.code == 5, r.text
    assert [s["stage"]["id"] for s in world.starts()] == ["s10_preprocess"]
    assert refusal_reason(world) == "no-gpu"
