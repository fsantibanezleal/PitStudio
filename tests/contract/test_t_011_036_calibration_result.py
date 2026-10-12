"""T-011-036 - FR-011-26, SC-011-06: calibration result reporting and gradient-reliability accounting.

Oracles (independent of the code under test):
- the draft JSON Schema 2020-12 of DC-011-04 (`specs/011-surrogates/contracts/calibration-result.schema.json`),
    checked with
  the reference implementation `jsonschema` (every document the driver returns must validate, including the conditional
  rules: a gradient arm carries its gradient-check log and deterministic accumulation, an unreliable gradient and a
  not-identified parameter cannot cover the truth, a synthetic trial carries truth and covers_truth);
- the fake analytic simulator of tests/_calib_fake.py (theta = a + b mu + sigma z(seed)): the loss at the estimate, the
  smooth angle and the interval of FR-011-22 are recomputed here from the closed form with `statistics.stdev` and the
  published Student quantile t_{0.975,7} = 2.364624 (any t table);
- hand arithmetic of the accounting of FR-011-21 / FR-011-23: a gradient arm with budget 12 runs 2 iterations of
  3 x S = 6 equivalents, the interval costs 3 x R = 24 simulations and the two gradient checks 2 x (4 + 4) = 16, both
  reported outside the budget;
- SC-011-06: a tape gradient with its sign flipped (a faulty adjoint) must be reported "unreliable", with the failing
  checks published, and counted by the reliability accounting; a correct gradient must be reported "reliable" with every
  check trusted.

Expected public API (module `pitstudio_studio.physics.calibration.driver`, package under `studio/src/`; the
    accounting helper
lives in `pitstudio.calibration.study`):

    calibrate(request: dict, simulator) -> dict
        Runs one calibration (one arm) and returns a DC-011-04 document (a dict valid against the schema above).
        request keys (the plan's recipe): kind ("synthetic-trial" | "literature-target"), arm ("gradient" | "cma-es"),
        trial_id (slug), target ({"theta_deg", "packing_seed"} or the literature fields), truth ({"sliding_friction"},
        synthetic only), mu0, bounds [lo, hi], budget, window_steps (W), settling_steps, packing_seeds (S, int),
        interval_runs (R, int), seeds ({"target", "optimisation", "interval", "gradient_check"}: lists of ints),
            particle_count,
        adam_lr, cma_seed, secondary_arm (bool), solver_version.
        simulator: the protocol of tests/_calib_fake.py (`solver`, `differentiable`, `particle_count`,
        `free_device_memory_bytes`, `theta`, `hard_theta`, `theta_and_grad`).
        The gradient arm runs the arm of tape.run_gradient_arm, then the gradient check of FR-011-23 at the first
            and at the
        final iterate (4 + 4 runs on the gradient-check seeds at mu -/+ h, h = 0.05 mu), then the interval of
            FR-011-22 on the
        interval seeds at the best evaluated mu_hat; the CMA-ES arm runs cmaes.run_cmaes_arm and the interval only.
        A gradient trial is "unreliable" when either check is untrusted; every parameter of an unreliable trial has
        covers_truth False.
    pitstudio.calibration.study.gradient_reliability(results: list[dict]) -> dict
        {"trials": int, "reliable": int, "unreliable": int, "untrusted_used": int, "failures": list of
        {"trial_id", "iterate", "failure"}}: counts the gradient-arm documents by gradient_status, lists every failed
        check with its label, and counts reliable documents that nevertheless contain an untrusted check (must be 0).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem, default_request, z_of  # noqa: E402
from pitstudio_studio.physics.calibration import driver  # noqa: E402

from pitstudio.calibration import study  # noqa: E402

SCHEMA = json.loads(
    (ROOT / "specs" / "011-surrogates" / "contracts" / "calibration-result.schema.json").read_text(encoding="utf-8")
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
T975_7 = 2.364624  # published Student t quantile, 7 degrees of freedom
LABEL = "calibrated synthetic — not validated against real data"


def errors_of(doc: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(doc)]


def gradient_request(**kw) -> dict:
    return default_request(budget=12, adam_lr=0.02, **kw)  # 2 iterations, still far from the optimum


@pytest.fixture(scope="module")
def gradient_run() -> tuple[dict, FakeDem]:
    fake = FakeDem(24.0, 20.0, sigma=0.05)
    return driver.calibrate(gradient_request(), fake), fake


@pytest.fixture(scope="module")
def cmaes_run() -> tuple[dict, FakeDem]:
    fake = FakeDem(24.0, 20.0, sigma=0.05)
    return driver.calibrate(default_request(arm="cma-es", budget=24, cma_seed=3), fake), fake


# ------------------------------------------------------------------ FR-011-26 the published document


@pytest.mark.req("FR-011-26")
def test_gradient_result_validates_against_the_dc_011_04_schema(gradient_run) -> None:
    doc, _ = gradient_run
    assert errors_of(doc) == []
    assert doc["arm"] == "gradient"
    assert doc["kind"] == "synthetic-trial"
    assert doc["label"] == LABEL


@pytest.mark.req("FR-011-26")
def test_cmaes_result_validates_and_has_no_gradient_block(cmaes_run) -> None:
    doc, _ = cmaes_run
    assert errors_of(doc) == []
    assert doc["arm"] == "cma-es"
    assert "gradient_check" not in doc
    assert "gradient_status" not in doc
    assert doc["cmaes"]["sigma0"] == 0.1
    assert doc["cmaes"]["population"] == 4  # 4 + floor(3 ln 1)
    assert doc["check_simulations"] == 0


@pytest.mark.req("FR-011-26")
def test_the_recipe_values_are_published_back(gradient_run) -> None:
    doc, _fake = gradient_run
    assert doc["window_steps"] == 1000
    assert doc["settling_steps"] == 20000
    assert doc["packing_seeds"] == 2
    assert doc["interval_runs"] == 8
    assert doc["seeds"]["target"] == [9001]
    assert doc["seeds"]["optimisation"] == [9101, 9102]
    assert doc["seeds"]["interval"] == [9201 + i for i in range(8)]
    assert doc["seeds"]["gradient_check"] == [9301 + i for i in range(4)]
    assert doc["deterministic_accumulation"] is True
    assert doc["solver"] == "warp-dem"
    assert doc["particle_count"] == 2000
    assert doc["trial_id"] == "trial-001"
    assert doc["budget_simulations"] == 12
    assert doc["wall_time_s"] >= 0.0
    p = doc["parameters"][0]
    assert p["name"] == "sliding_friction"
    assert p["start"] == pytest.approx(0.55, rel=1e-12)
    assert p["bounds"] == [0.1, 1.0]
    assert p["truth"] == pytest.approx(0.40, rel=1e-12)
    assert p["fd_step"] == pytest.approx(0.05 * p["estimate"], rel=1e-9)


@pytest.mark.req("FR-011-26")
def test_loss_terms_weights_and_both_observables_are_published(gradient_run) -> None:
    doc, fake = gradient_run
    p = doc["parameters"][0]
    mu_hat = p["estimate"]
    seeds = [9101, 9102]
    loss_hand = statistics.fmean([(fake.a + fake.b * mu_hat + fake.sigma * z_of(s) - 32.0) ** 2 for s in seeds])
    theta_s = statistics.fmean([fake.a + fake.b * mu_hat + fake.sigma * z_of(s) for s in seeds])
    loss = doc["loss"]
    assert loss["observable"] == "smooth-envelope"
    assert len(loss["terms"]) == 1
    term = loss["terms"][0]
    assert term["name"] == "repose"
    assert term["weight"] == pytest.approx(1.0)
    assert term["value"] == pytest.approx(loss_hand, rel=1e-6, abs=1e-9)
    assert loss["total"] == pytest.approx(term["weight"] * term["value"], rel=1e-9, abs=1e-12)
    assert loss["smooth_theta_deg"] == pytest.approx(theta_s, rel=1e-6)
    assert loss["hard_theta_deg"] == pytest.approx(
        theta_s + fake.hard_offset, rel=1e-6
    )  # the hard observable beside it


@pytest.mark.req("FR-011-26")
def test_budget_check_and_interval_simulations_are_counted_separately(gradient_run) -> None:
    doc, _fake = gradient_run
    assert doc["simulations"] == 12  # 2 iterations x 2 heaps x 3 forward-equivalents
    assert doc["check_simulations"] == 16  # 2 iterates x (4 + 4) runs, outside the budget
    assert doc["interval_simulations"] == 24  # 3 mu values x 8 interval seeds
    assert doc["stop_reason"] == "budget"


@pytest.mark.req("FR-011-26")
def test_gradient_checks_are_logged_at_the_first_and_the_final_iterate(gradient_run) -> None:
    doc, _ = gradient_run
    log = doc["gradient_check"]
    assert [c["iterate"] for c in log] == ["first", "final"]
    for c in log:
        assert c["parameter"] == "sliding_friction"
        assert c["runs_per_side"] == 4
        assert c["dof"] == 6
        assert c["trusted"] is True
        assert c["failure"] == "none"
        assert c["se_fd"] >= 0.0
    assert log[0]["mu"] == pytest.approx(0.55, rel=1e-12)
    assert log[0]["fd_gradient"] == pytest.approx(log[0]["tape_gradient"], abs=3.707 * log[0]["se_fd"] + 1e-9)


@pytest.mark.req("FR-011-26")
def test_the_published_interval_follows_the_fr_011_22_formula(gradient_run) -> None:
    doc, fake = gradient_run
    p = doc["parameters"][0]
    mu_hat = p["estimate"]
    sd = statistics.stdev([fake.a + fake.b * mu_hat + fake.sigma * z_of(9201 + i) for i in range(8)])
    half = T975_7 * sd * math.sqrt(1.0 + 1.0 / 2.0) / fake.b
    iv = p["interval"]
    assert iv["level"] == 0.95
    assert iv["t_quantile"] == pytest.approx(T975_7, rel=1e-6)
    assert iv["sigma_theta_deg"] == pytest.approx(sd, rel=1e-6)
    assert iv["slope_deg_per_unit"] == pytest.approx(fake.b, rel=1e-6)
    assert p["identification"] == "identified"
    assert iv["lower"] == pytest.approx(mu_hat - half, rel=1e-6, abs=1e-9)
    assert iv["upper"] == pytest.approx(mu_hat + half, rel=1e-6, abs=1e-9)
    assert p["covers_truth"] is bool(mu_hat - half <= 0.40 <= mu_hat + half)


# ------------------------------------------------------------------ SC-011-06 gradient reliability


@pytest.mark.req("SC-011-06")
def test_a_correct_tape_gradient_is_reported_reliable_with_every_check_trusted(gradient_run) -> None:
    doc, _ = gradient_run
    assert doc["gradient_status"] == "reliable"
    assert all(c["trusted"] for c in doc["gradient_check"])


@pytest.mark.req("SC-011-06")
@pytest.mark.parametrize("scale", [-1.0, -0.5])
def test_a_faulty_tape_gradient_is_reported_unreliable_published_and_never_covers(scale: float) -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.05, grad_scale=scale)
    doc = driver.calibrate(gradient_request(), fake)
    assert errors_of(doc) == []  # the schema forces covers_truth False for an unreliable gradient
    assert doc["gradient_status"] == "unreliable"
    assert any(c["trusted"] is False and c["failure"] != "none" for c in doc["gradient_check"])
    assert all(p["covers_truth"] is False for p in doc["parameters"])
    assert doc["check_simulations"] == 16  # the failed checks cost the same and are reported


@pytest.mark.req("SC-011-06")
def test_the_reliability_accounting_counts_and_lists_every_failure() -> None:
    good = [driver.calibrate(gradient_request(trial_id=f"good-{i}"), FakeDem(24.0, 20.0, sigma=0.05)) for i in range(3)]
    bad = [
        driver.calibrate(gradient_request(trial_id=f"bad-{i}"), FakeDem(24.0, 20.0, sigma=0.05, grad_scale=-1.0))
        for i in range(2)
    ]
    acc = study.gradient_reliability(good + bad)
    assert acc["trials"] == 5
    assert acc["reliable"] == 3
    assert acc["unreliable"] == 2
    assert acc["untrusted_used"] == 0
    assert {f["trial_id"] for f in acc["failures"]} == {"bad-0", "bad-1"}
    assert all(f["failure"] != "none" and f["iterate"] in {"first", "final"} for f in acc["failures"])


@pytest.mark.req("SC-011-06")
def test_the_accounting_flags_a_document_that_hides_an_untrusted_check(gradient_run) -> None:
    doc, _ = gradient_run
    tampered = json.loads(json.dumps(doc))
    tampered["gradient_check"][1]["trusted"] = False
    tampered["gradient_check"][1]["failure"] = "disagreement"  # but gradient_status still says "reliable"
    acc = study.gradient_reliability([tampered])
    assert acc["untrusted_used"] == 1


@pytest.mark.req("SC-011-06")
def test_the_accounting_ignores_documents_of_the_cmaes_arm(cmaes_run) -> None:
    doc, _ = cmaes_run
    acc = study.gradient_reliability([doc])
    assert acc["trials"] == 0
    assert acc["failures"] == []
