"""T-011-032 - FR-011-23, P-011-10: tape-gradient gate against a 4 + 4 run central finite difference.

Oracles (independent of the code under test; plan 011 test strategy FR-011-23 and P-011-10):
- hand calculation of the gate on fixed numbers (spec section 7): FD = (mean_plus - mean_minus) / (2 h);
  SE_FD = s_p sqrt(1/4 + 1/4) / (2 h) with s_p the pooled standard deviation (6 degrees of freedom, equal group sizes:
  s_p^2 = (s_plus^2 + s_minus^2) / 2); the gradient is trusted iff |FD| >= 2.447 SE_FD, sign(g_tape) = sign(FD) and
  |g_tape - FD| <= 3.707 SE_FD (Student t_{0.975,6} = 2.447 and t_{0.995,6} = 3.707, published table values).
  Worked numbers: plus = (10.1, 9.9, 10.2, 9.8), minus = (8.1, 7.9, 8.2, 7.8), h = 0.05: both groups have sum of squares
  0.10, variance 0.10 / 3, s_p = 0.1825742, SE_FD = 0.1825742 * 0.7071068 / 0.1 = 1.290994, FD = 2.0 / 0.1 = 20;
- a reference gate written in this file from the same formulas, used for the random metamorphic checks;
- binomial arithmetic of P-011-10: a fake simulator with known gradient g and Gaussian run-to-run noise, 1,000
    trials per
  configuration; the true SE_FD is sigma sqrt(1/2) / (2 h); the acceptance rate of the true gradient is expected 0.99
  (plan: 20,000-trial simulation 0.990 at |g| = 10 SE_FD), the bound 0.98 leaves three binomial standard deviations.

Expected public API (module `pitstudio.calibration.gradient_gate`, under `src/pitstudio/calibration/`):

    check_gradient(tape_gradient, plus_runs, minus_runs, h) -> GateResult
        plus_runs / minus_runs: exactly 4 finite losses each at mu + h and mu - h; h > 0 finite; tape_gradient finite.
        GateResult attributes: trusted (bool), fd_gradient, se_fd, failure in {"none", "fd-not-significant",
        "sign-mismatch", "disagreement"} ("none" iff trusted), runs_per_side (= 4), dof (= 6).
    Raises `pitstudio.calibration.errors.InvalidCalibrationError` for a wrong number of runs, a non-finite value or
        h <= 0.
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402
from pitstudio.calibration.gradient_gate import check_gradient  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
T_SIG, T_AGREE = 2.447, 3.707
PLUS = [10.1, 9.9, 10.2, 9.8]
MINUS = [8.1, 7.9, 8.2, 7.8]
H = 0.05
SE = math.sqrt(0.10 / 3.0) * math.sqrt(0.5) / (2 * H)  # 1.290994 (hand calculation above)


def ref_gate(g: float, plus: list[float], minus: list[float], h: float) -> bool:
    fd = (statistics.fmean(plus) - statistics.fmean(minus)) / (2 * h)
    sp = math.sqrt((statistics.variance(plus) + statistics.variance(minus)) / 2.0)
    se = sp * math.sqrt(0.25 + 0.25) / (2 * h)
    return abs(fd) >= T_SIG * se and g * fd > 0 and abs(g - fd) <= T_AGREE * se


def shifted_plus(k_sig: float) -> list[float]:
    """The plus group shifted so that FD = k_sig * SE exactly, the spreads unchanged."""
    delta = k_sig * SE * 2 * H - (statistics.fmean(PLUS) - statistics.fmean(MINUS))
    return [v + delta for v in PLUS]


# ------------------------------------------------------------------ FR-011-23 by hand


@pytest.mark.req("FR-011-23")
def test_worked_example_fd_and_se_and_a_trusted_gradient() -> None:
    res = check_gradient(20.0, PLUS, MINUS, H)
    assert res.fd_gradient == pytest.approx(20.0, rel=1e-12)
    assert res.se_fd == pytest.approx(1.290994, rel=1e-6)
    assert res.trusted is True
    assert res.failure == "none"
    assert res.runs_per_side == 4
    assert res.dof == 6


@pytest.mark.req("FR-011-23")
def test_pooled_standard_deviation_of_unequal_groups_by_hand() -> None:
    plus = [10.0, 10.4, 9.6, 10.0]  # sum of squares 0.32, variance 0.106667
    minus = [8.0, 8.2, 7.8, 8.0]  # sum of squares 0.08, variance 0.026667
    res = check_gradient(10.0, plus, minus, 0.1)  # FD = 2 / 0.2 = 10; s_p^2 = 0.0666667; SE = 0.182574 / 0.2
    assert res.fd_gradient == pytest.approx(10.0, rel=1e-12)
    assert res.se_fd == pytest.approx(0.912871, rel=1e-6)


@pytest.mark.req("FR-011-23")
def test_zero_spread_gives_zero_se_and_trusts_only_the_exact_gradient() -> None:
    plus, minus = [2.0] * 4, [1.0] * 4
    assert check_gradient(1.0, plus, minus, 0.5).trusted is True
    res = check_gradient(1.1, plus, minus, 0.5)
    assert res.se_fd == 0.0
    assert res.trusted is False
    assert res.failure == "disagreement"


@pytest.mark.req("FR-011-23")
@pytest.mark.parametrize(("k_sig", "trusted"), [(2.4465, False), (2.4475, True)])
def test_significance_threshold_is_2_447_se(k_sig: float, trusted: bool) -> None:
    plus = shifted_plus(k_sig)
    fd = (statistics.fmean(plus) - statistics.fmean(MINUS)) / (2 * H)
    res = check_gradient(fd, plus, MINUS, H)
    assert res.trusted is trusted
    assert res.failure == ("none" if trusted else "fd-not-significant")


@pytest.mark.req("FR-011-23")
@pytest.mark.parametrize(("k_dis", "trusted"), [(3.700, True), (-3.700, True), (3.715, False), (-3.715, False)])
def test_agreement_threshold_is_3_707_se(k_dis: float, trusted: bool) -> None:
    res = check_gradient(20.0 + k_dis * SE, PLUS, MINUS, H)
    assert res.trusted is trusted
    assert res.failure == ("none" if trusted else "disagreement")


@pytest.mark.req("FR-011-23")
def test_a_sign_mismatch_with_small_disagreement_is_reported_as_sign_mismatch() -> None:
    plus = shifted_plus(2.5)  # FD = 2.5 SE, significant
    fd = (statistics.fmean(plus) - statistics.fmean(MINUS)) / (2 * H)
    g = -1.0 * SE  # |g - FD| = 3.5 SE <= 3.707 SE, so only the sign rule fails
    res = check_gradient(g, plus, MINUS, H)
    assert fd == pytest.approx(2.5 * SE, rel=1e-9)
    assert res.trusted is False
    assert res.failure == "sign-mismatch"


@pytest.mark.req("FR-011-23")
def test_a_negative_fd_is_handled_symmetrically() -> None:
    assert check_gradient(-20.0, MINUS, PLUS, H).trusted is True
    assert check_gradient(20.0, MINUS, PLUS, H).trusted is False


# ------------------------------------------------------------------ metamorphic relations of the gate


@pytest.mark.req("FR-011-23")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    plus=st.lists(st.floats(-100, 100), min_size=4, max_size=4),
    minus=st.lists(st.floats(-100, 100), min_size=4, max_size=4),
    h=st.floats(1e-3, 1.0),
    ratio=st.floats(-3.0, 3.0),
)
def test_property_decision_equals_the_reference_gate(
    plus: list[float], minus: list[float], h: float, ratio: float
) -> None:
    fd = (statistics.fmean(plus) - statistics.fmean(minus)) / (2 * h)
    if fd == 0.0 or ratio == 0.0 or statistics.pstdev(plus + minus) < 1e-9:
        return
    g = ratio * fd
    # skip knife-edge inputs: the decision must be stable for 1e-9 relative changes of g
    near = [g * (1 + e) for e in (-1e-9, 1e-9)]
    if len({ref_gate(x, plus, minus, h) for x in [g, *near]}) != 1:
        return
    assert check_gradient(g, plus, minus, h).trusted is ref_gate(g, plus, minus, h)


@pytest.mark.req("FR-011-23")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    scale=st.floats(0.1, 50.0),
    offset=st.floats(-50.0, 50.0),
    ratio=st.floats(0.5, 1.5),
)
def test_metamorphic_scaling_the_loss_and_shifting_it_keep_the_decision(
    scale: float, offset: float, ratio: float
) -> None:
    g = ratio * 20.0
    base = check_gradient(g, PLUS, MINUS, H).trusted
    scaled = check_gradient(g * scale, [v * scale for v in PLUS], [v * scale for v in MINUS], H).trusted
    shifted = check_gradient(g, [v + offset for v in PLUS], [v + offset for v in MINUS], H).trusted
    swapped = check_gradient(-g, MINUS, PLUS, H).trusted
    near_edge = min(abs(abs(g - 20.0) / SE - T_AGREE), abs(g / SE - 0.0)) < 1e-6
    if not near_edge:
        assert scaled is base
        assert shifted is base
        assert swapped is base


# ------------------------------------------------------------------ P-011-10 acceptance and rejection rates


def simulate_gate(g_true: float, g_tape: float, sigma: float, h: float, seed: int, n: int = 1000) -> list[bool]:
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        plus = (g_true * h + rng.normal(0.0, sigma, 4)).tolist()
        minus = (-g_true * h + rng.normal(0.0, sigma, 4)).tolist()
        out.append(check_gradient(g_tape, plus, minus, h).trusted)
    return out


@pytest.mark.req("P-011-10")
@pytest.mark.parametrize("sigma", [0.1, 0.5, 2.0])
@pytest.mark.parametrize("multiple", [10.0, 30.0, 100.0])
@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_true_gradient_is_accepted_in_at_least_98_percent_of_1000_trials(
    sigma: float, multiple: float, sign: float
) -> None:
    h = 0.04
    se_true = sigma * math.sqrt(0.5) / (2 * h)
    g = sign * multiple * se_true
    accepted = sum(simulate_gate(g, g, sigma, h, seed=int(sigma * 100 + multiple)))
    assert accepted >= 980


@pytest.mark.req("P-011-10")
@pytest.mark.parametrize("sigma", [0.1, 0.5, 2.0])
@pytest.mark.parametrize("multiple", [10.0, 100.0])
def test_sign_flipped_gradient_is_rejected_in_every_trial(sigma: float, multiple: float) -> None:
    h = 0.04
    g = multiple * sigma * math.sqrt(0.5) / (2 * h)
    assert sum(simulate_gate(g, -g, sigma, h, seed=77)) == 0


@pytest.mark.req("P-011-10")
@pytest.mark.parametrize("sigma", [0.1, 0.5, 2.0])
@pytest.mark.parametrize("tape_sign", [1.0, -1.0])
def test_a_tape_gradient_of_10_se_is_rejected_in_every_trial_when_the_true_gradient_is_zero(
    sigma: float, tape_sign: float
) -> None:
    h = 0.04
    se_true = sigma * math.sqrt(0.5) / (2 * h)
    assert sum(simulate_gate(0.0, tape_sign * 10.0 * se_true, sigma, h, seed=99)) == 0


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-23")
@pytest.mark.parametrize(
    ("plus", "minus"),
    [
        ([1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0]),
        ([1.0] * 4, [1.0] * 5),
        ([], []),
        ([1.0, 2.0, float("nan"), 3.0], [1.0] * 4),
        ([1.0] * 4, [float("inf"), 1.0, 1.0, 1.0]),
    ],
    ids=["three-plus", "five-minus", "empty", "nan", "inf"],
)
def test_wrong_run_counts_and_non_finite_runs_are_rejected(plus: list[float], minus: list[float]) -> None:
    with pytest.raises(InvalidCalibrationError):
        check_gradient(1.0, plus, minus, 0.05)


@pytest.mark.req("FR-011-23")
@pytest.mark.parametrize("h", [0.0, -0.05, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_step_is_rejected(h: float) -> None:
    with pytest.raises(InvalidCalibrationError):
        check_gradient(1.0, PLUS, MINUS, h)


@pytest.mark.req("FR-011-23")
@pytest.mark.parametrize("g", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_tape_gradient_is_rejected(g: float) -> None:
    with pytest.raises(InvalidCalibrationError):
        check_gradient(g, PLUS, MINUS, H)
