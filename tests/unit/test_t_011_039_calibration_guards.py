"""T-011-039 - FR-011-29, FR-011-30: non-differentiable solver refusal and hostile calibration requests.

Oracles (independent of the code under test; plan 011 test strategy FR-011-29 / FR-011-30):
- the fake simulator of tests/_calib_fake.py with its call log: "before any simulation" is checked as zero logged calls;
- the exact refusal text of FR-011-29, "not differentiable — gradient-free only", and the schema rule of the draft
    DC-011-04
  (a Newton MPM document admits the CMA-ES arm only), checked with the reference implementation `jsonschema`;
- the limits of FR-011-30 written out in the table below: theta* in [5, 60] deg, mu0 and bounds in [0.05, 2] not
    inverted,
  budget in [1, 10^4], W in [100, 5,000], S and R >= 2, the four seed sets pairwise disjoint, and the tape memory
  estimate 24 B x particles x W (plus contact buffers, which only increase it) against 80 % of the free device memory:
  24 x 2,000 x 1,000 = 48,000,000 B exceeds 80 % of 55,000,000 B (44,000,000 B) whatever the contact buffers are;
- seeds are integers in [0, 2^32 - 1] (draft schema), so negative and fractional seeds are hostile as well.

Expected public API (module `pitstudio_studio.physics.calibration.driver`; error class
`pitstudio.calibration.errors.InvalidCalibrationError`; request keys as in T-011-036):
    calibrate(request, simulator) -> dict
        Raises InvalidCalibrationError, with a message that names the offending request key, before any simulation.
            For a
        gradient request on a simulator whose `differentiable` is False the message is "not differentiable —
            gradient-free only".
    calibrate_arms(request, simulator, arms=("gradient", "cma-es")) -> CalibrationRun
        CalibrationRun.results: list of DC-011-04 documents (one per arm run); CalibrationRun.refusals: list of
        {"arm", "reason"}. A non-differentiable solver (Newton implicit MPM) gives refusals == [{"arm": "gradient",
        "reason": "not differentiable — gradient-free only"}] and results == [the CMA-ES document].
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem, default_request  # noqa: E402
from pitstudio_studio.physics.calibration import driver  # noqa: E402

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402

VALIDATOR = jsonschema.Draft202012Validator(
    json.loads(
        (ROOT / "specs" / "011-surrogates" / "contracts" / "calibration-result.schema.json").read_text(encoding="utf-8")
    )
)
NOT_DIFFERENTIABLE = "not differentiable — gradient-free only"


def untouched(fake: FakeDem) -> bool:
    return fake.forward_calls == [] and fake.grad_calls == []


# ------------------------------------------------------------------ FR-011-29


@pytest.mark.req("FR-011-29")
def test_a_non_differentiable_solver_refuses_the_gradient_arm_and_runs_cma_es_only() -> None:
    mpm = FakeDem(24.0, 20.0, sigma=0.05, solver="newton-mpm", differentiable=False)
    run = driver.calibrate_arms(default_request(budget=24), mpm)
    assert run.refusals == [{"arm": "gradient", "reason": NOT_DIFFERENTIABLE}]
    assert [d["arm"] for d in run.results] == ["cma-es"]
    assert run.results[0]["solver"] == "newton-mpm"
    assert [e.message for e in VALIDATOR.iter_errors(run.results[0])] == []
    assert mpm.grad_calls == []  # the tape is never entered


@pytest.mark.req("FR-011-29")
def test_a_single_gradient_request_on_a_non_differentiable_solver_raises_with_the_exact_text() -> None:
    mpm = FakeDem(24.0, 20.0, solver="newton-mpm", differentiable=False)
    with pytest.raises(InvalidCalibrationError, match=NOT_DIFFERENTIABLE):
        driver.calibrate(default_request(arm="gradient"), mpm)
    assert untouched(mpm)


@pytest.mark.req("FR-011-29")
def test_a_differentiable_solver_runs_both_arms_without_refusals() -> None:
    warp = FakeDem(24.0, 20.0, sigma=0.05)
    run = driver.calibrate_arms(default_request(budget=24), warp)
    assert run.refusals == []
    assert sorted(d["arm"] for d in run.results) == ["cma-es", "gradient"]
    for doc in run.results:
        assert [e.message for e in VALIDATOR.iter_errors(doc)] == []


@pytest.mark.req("FR-011-29")
def test_the_cma_es_arm_alone_is_fine_on_a_non_differentiable_solver() -> None:
    mpm = FakeDem(24.0, 20.0, sigma=0.05, solver="newton-mpm", differentiable=False)
    doc = driver.calibrate(default_request(arm="cma-es", budget=24), mpm)
    assert doc["arm"] == "cma-es"
    assert [e.message for e in VALIDATOR.iter_errors(doc)] == []


# ------------------------------------------------------------------ FR-011-30 hostile requests


def edit(path: str, value) -> dict:
    req = default_request()
    node = req
    keys = path.split(".")
    for k in keys[:-1]:
        node = node[k]
    node[keys[-1]] = value
    return req


NAN, INF = float("nan"), float("inf")
HOSTILE = [
    (edit("target.theta_deg", 4.99), "theta_deg"),
    (edit("target.theta_deg", 60.01), "theta_deg"),
    (edit("target.theta_deg", -10.0), "theta_deg"),
    (edit("target.theta_deg", NAN), "theta_deg"),
    (edit("target.theta_deg", INF), "theta_deg"),
    (edit("mu0", 0.04), "mu0"),
    (edit("mu0", 2.01), "mu0"),
    (edit("mu0", NAN), "mu0"),
    (edit("bounds", [0.04, 1.0]), "bounds"),
    (edit("bounds", [0.1, 2.1]), "bounds"),
    (edit("bounds", [1.0, 0.1]), "bounds"),
    (edit("bounds", [0.5, 0.5]), "bounds"),
    (edit("bounds", [NAN, 1.0]), "bounds"),
    (edit("bounds", [0.1]), "bounds"),
    (edit("budget", 0), "budget"),
    (edit("budget", -5), "budget"),
    (edit("budget", 10_001), "budget"),
    (edit("window_steps", 99), "window_steps"),
    (edit("window_steps", 5001), "window_steps"),
    (edit("packing_seeds", 1), "packing_seeds"),
    (edit("packing_seeds", 0), "packing_seeds"),
    (edit("interval_runs", 1), "interval_runs"),
    (edit("interval_runs", 0), "interval_runs"),
    (edit("seeds.optimisation", [9101, 9001]), "seeds"),  # shares the target seed
    (edit("seeds.interval", [9101] + [9202 + i for i in range(7)]), "seeds"),  # shares an optimisation seed
    (edit("seeds.gradient_check", [9201, 9302, 9303, 9304]), "seeds"),  # shares an interval seed
    (edit("seeds.optimisation", [-1, 9102]), "seeds"),
    (edit("seeds.optimisation", [9101.5, 9102]), "seeds"),
    (edit("seeds.optimisation", [2**32, 9102]), "seeds"),
    (edit("seeds.optimisation", []), "seeds"),
]


@pytest.mark.req("FR-011-30")
@pytest.mark.parametrize(("request_doc", "key"), HOSTILE, ids=[f"{i:02d}-{k}" for i, (_, k) in enumerate(HOSTILE)])
def test_hostile_requests_raise_naming_the_key_before_any_simulation(request_doc: dict, key: str) -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.05)
    with pytest.raises(InvalidCalibrationError, match=key):
        driver.calibrate(request_doc, fake)
    assert untouched(fake)


@pytest.mark.req("FR-011-17")
@pytest.mark.parametrize("count", [0, -1, 5001, 20000])
def test_a_synthetic_trial_must_be_trial_scale_between_1_and_5000_particles(count: int) -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.05)
    with pytest.raises(InvalidCalibrationError, match="particle_count"):
        driver.calibrate(edit("particle_count", count), fake)
    assert untouched(fake)


@pytest.mark.req("FR-011-26")
@pytest.mark.parametrize(
    ("path", "value", "key"),
    [
        ("arm", "newton", "arm"),
        ("kind", "field-trial", "kind"),
        ("trial_id", "Bad Id!", "trial_id"),
        ("trial_id", "", "trial_id"),
    ],
)
def test_unknown_arm_kind_or_a_malformed_trial_id_is_refused_before_any_simulation(path: str, value, key: str) -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.05)
    with pytest.raises(InvalidCalibrationError, match=key):
        driver.calibrate(edit(path, value), fake)
    assert untouched(fake)


@pytest.mark.req("FR-011-30")
def test_the_tape_memory_estimate_above_80_percent_of_free_memory_is_refused_for_the_gradient_arm() -> None:
    fake = FakeDem(
        24.0, 20.0, sigma=0.05, free_device_memory_bytes=55_000_000
    )  # 80 % = 44 MB < 24 x 2000 x 1000 = 48 MB
    with pytest.raises(InvalidCalibrationError, match="memory"):
        driver.calibrate(default_request(arm="gradient"), fake)
    assert untouched(fake)


@pytest.mark.req("FR-011-30")
def test_the_same_request_passes_the_memory_guard_with_enough_free_memory_and_for_the_cma_es_arm() -> None:
    roomy = FakeDem(24.0, 20.0, sigma=0.05, free_device_memory_bytes=2**34)
    assert driver.calibrate(default_request(arm="gradient", budget=12), roomy)["arm"] == "gradient"
    tight = FakeDem(24.0, 20.0, sigma=0.05, free_device_memory_bytes=55_000_000)
    assert driver.calibrate(default_request(arm="cma-es", budget=16), tight)["arm"] == "cma-es"  # no tape, no estimate


@pytest.mark.req("FR-011-30")
@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("target.theta_deg", 5.0),
        ("target.theta_deg", 60.0),
        ("mu0", 0.05),
        ("mu0", 2.0),
        ("bounds", [0.05, 2.0]),
        ("window_steps", 100),
        ("window_steps", 5000),
    ],
)
def test_values_exactly_on_the_limits_are_accepted(path: str, value) -> None:
    req = edit(path, value)
    req["bounds"] = [0.05, 2.0]  # the widest legal box, so that mu0 at either limit lies inside it
    req["arm"] = "cma-es"
    req["budget"] = 16
    doc = driver.calibrate(req, FakeDem(24.0, 20.0, sigma=0.05))
    assert [e.message for e in VALIDATOR.iter_errors(doc)] == []


@pytest.mark.req("FR-011-30")
def test_a_refused_request_is_not_modified_and_a_valid_one_is_not_mutated() -> None:
    req = default_request(arm="cma-es", budget=16)
    before = copy.deepcopy(req)
    driver.calibrate(req, FakeDem(24.0, 20.0, sigma=0.05))
    assert req == before
