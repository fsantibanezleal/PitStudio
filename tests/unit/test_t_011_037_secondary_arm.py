"""T-011-037 - FR-011-27: optional (mu_s, mu_r) arm from repose and hopper discharge, and "weakly identified" labelling.

Oracles (independent of the code under test; plan 011 test strategy FR-011-27):
- the loss of the spec written out by hand: L = (theta_s - theta*)^2 / (1 deg)^2 + ((Q - Q*) / Q*)^2 / 0.05^2, so the
  repose term has weight 1 and the discharge term weight 1 / 0.05^2 = 400, and the total is the weighted sum;
- the two-parameter fake of tests/_calib_fake.py (FakeDem2): theta = a + b mu_s + c mu_r + sigma z(seed), Q = q0 (1
    + k mu_s +
  m mu_r), with c = 0.05 and m = 0.0005, so the rolling friction is almost invisible: a delta-method half-width
  t sigma sqrt(1 + 1/S) / |slope| with the repose slope c = 0.05 is 2.36 x 0.05 x 1.22 / 0.05 = 2.9, far above 50 %
      of the
  prior range [0.05, 1.0] (0.475), while the sliding friction (slope b = 20) has a half-width of about 0.007;
- the draft schema of DC-011-04 (a two-parameter document needs `secondary_arm` true, a discharge target and two
    parameters).

"Weakly identified" is read as: the interval is bounded (the parameter is identified) and its width (upper - lower)
    exceeds
50 % of the prior range (bounds[1] - bounds[0]) of that parameter.

Expected public API (module `pitstudio_studio.physics.calibration.driver`, see T-011-036 for the request keys):
    calibrate(request, simulator2) -> dict           with request["secondary_arm"] True, request["arm"] "cma-es"
        and the extra keys
        target["discharge_rate_kg_per_s"] (Q*), "rolling_bounds" [lo, hi] and "mu0_rolling";
        simulator2.observables(mu_s, mu_r, seed) -> (theta_deg, discharge_kg_per_s) is the two-observable protocol
            of FakeDem2.
    The document has two parameters, in the order sliding_friction, rolling_friction, each with its own interval and
    `covers_truth` (synthetic trial); loss.terms = [repose, discharge] with the weights above.
    Raises `pitstudio.calibration.errors.InvalidCalibrationError` naming `discharge_rate_kg_per_s` when the
        secondary arm is
    enabled without a positive finite discharge target, and naming `rolling_bounds` for bounds outside [0.05, 2] or
        inverted.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem2, default_request, z_of  # noqa: E402
from pitstudio_studio.physics.calibration import driver  # noqa: E402

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402

SCHEMA = json.loads(
    (ROOT / "specs" / "011-surrogates" / "contracts" / "calibration-result.schema.json").read_text(encoding="utf-8")
)
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
MU_S, MU_R = 0.40, 0.20


def request(fake: FakeDem2, **kw) -> dict:
    theta_star = fake.a + fake.b * MU_S + fake.c * MU_R + fake.sigma * z_of(9001)
    q_star = fake.q0 * (1.0 + fake.k * MU_S + fake.m * MU_R)
    base = default_request(
        arm="cma-es",
        secondary_arm=True,
        budget=120,
        target={"theta_deg": theta_star, "packing_seed": 9001, "discharge_rate_kg_per_s": q_star},
        truth={"sliding_friction": MU_S, "rolling_friction": MU_R},
        rolling_bounds=[0.05, 1.0],
        mu0_rolling=0.30,
    )
    base.update(kw)
    return base


@pytest.fixture(scope="module")
def run() -> tuple[dict, FakeDem2, dict]:
    fake = FakeDem2()
    req = request(fake)
    return driver.calibrate(req, fake), fake, req


@pytest.mark.req("FR-011-27")
def test_the_two_parameter_document_validates_and_orders_its_parameters(run) -> None:
    doc, _, _ = run
    assert [e.message for e in VALIDATOR.iter_errors(doc)] == []
    assert doc["secondary_arm"] is True
    assert [p["name"] for p in doc["parameters"]] == ["sliding_friction", "rolling_friction"]
    assert doc["target"]["discharge_rate_kg_per_s"] == pytest.approx(
        2.4002, rel=1e-9
    )  # 2 (1 + 0.5 x 0.4 + 0.0005 x 0.2)
    assert doc["simulations"] <= doc["budget_simulations"]


@pytest.mark.req("FR-011-27")
def test_the_loss_has_the_repose_term_of_weight_one_and_the_discharge_term_of_weight_400(run) -> None:
    doc, fake, req = run
    mu_s, mu_r = (p["estimate"] for p in doc["parameters"])
    theta_star = req["target"]["theta_deg"]
    q_star = req["target"]["discharge_rate_kg_per_s"]
    seeds = req["seeds"]["optimisation"]
    thetas = [fake.a + fake.b * mu_s + fake.c * mu_r + fake.sigma * z_of(s) for s in seeds]
    q = fake.q0 * (1.0 + fake.k * mu_s + fake.m * mu_r)
    repose = statistics.fmean([(t - theta_star) ** 2 for t in thetas])
    discharge = ((q - q_star) / q_star) ** 2
    terms = {t["name"]: t for t in doc["loss"]["terms"]}
    assert set(terms) == {"repose", "discharge"}
    assert terms["repose"]["weight"] == pytest.approx(1.0 / 1.0**2)
    assert terms["discharge"]["weight"] == pytest.approx(1.0 / 0.05**2)  # 400
    assert terms["repose"]["value"] == pytest.approx(repose, rel=1e-6, abs=1e-9)
    assert terms["discharge"]["value"] == pytest.approx(discharge, rel=1e-6, abs=1e-12)
    total = terms["repose"]["weight"] * repose + terms["discharge"]["weight"] * discharge
    assert doc["loss"]["total"] == pytest.approx(total, rel=1e-6, abs=1e-9)


@pytest.mark.req("FR-011-27")
def test_the_almost_invisible_rolling_friction_is_labelled_weakly_identified_and_the_sliding_friction_is_not(
    run,
) -> None:
    doc, _, req = run
    sliding, rolling = doc["parameters"]
    assert sliding["identification"] == "identified"
    assert rolling["identification"] == "weakly-identified"
    lo, hi = req["rolling_bounds"]
    width = rolling["interval"]["upper"] - rolling["interval"]["lower"]
    assert width > 0.5 * (hi - lo)  # the rule behind the label
    assert sliding["interval"]["upper"] - sliding["interval"]["lower"] < 0.5 * (req["bounds"][1] - req["bounds"][0])


@pytest.mark.req("FR-011-27")
def test_every_parameter_carries_its_own_interval_and_truth_coverage_flag(run) -> None:
    doc, _, _ = run
    for p, truth in zip(doc["parameters"], (MU_S, MU_R), strict=True):
        assert p["truth"] == pytest.approx(truth)
        assert isinstance(p["covers_truth"], bool)
        assert p["interval"]["level"] == 0.95
        assert p["fd_step"] > 0.0
        lo, hi = p["bounds"]
        assert lo <= p["estimate"] <= hi


@pytest.mark.req("FR-011-27")
def test_the_primary_arm_alone_has_one_parameter_and_no_discharge_term() -> None:
    from _calib_fake import FakeDem

    fake = FakeDem(24.0, 20.0, sigma=0.05)
    doc = driver.calibrate(default_request(arm="cma-es", budget=24), fake)
    assert doc["secondary_arm"] is False
    assert len(doc["parameters"]) == 1
    assert [t["name"] for t in doc["loss"]["terms"]] == ["repose"]


@pytest.mark.req("FR-011-27")
@pytest.mark.parametrize(
    "bad", [None, 0.0, -1.0, float("nan"), float("inf")], ids=["missing", "zero", "negative", "nan", "inf"]
)
def test_the_secondary_arm_needs_a_positive_finite_discharge_target(bad) -> None:
    fake = FakeDem2()
    req = request(fake)
    if bad is None:
        del req["target"]["discharge_rate_kg_per_s"]
    else:
        req["target"]["discharge_rate_kg_per_s"] = bad
    with pytest.raises(InvalidCalibrationError, match="discharge_rate_kg_per_s"):
        driver.calibrate(req, fake)
    assert fake.calls == []  # refused before any simulation


@pytest.mark.req("FR-011-27")
@pytest.mark.parametrize("bounds", [[0.01, 1.0], [0.05, 2.5], [0.9, 0.2], [float("nan"), 1.0]])
def test_rolling_bounds_outside_the_range_or_inverted_are_refused(bounds: list[float]) -> None:
    fake = FakeDem2()
    with pytest.raises(InvalidCalibrationError, match="rolling_bounds"):
        driver.calibrate(request(fake, rolling_bounds=bounds), fake)
    assert fake.calls == []
