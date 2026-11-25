"""T-011-035 - FR-011-24, FR-011-25, SC-011-02, SC-011-05: coverage study driver and paired comparisons.

Oracles (independent of the code under test; plan 011 test strategy FR-011-24 / FR-011-25 and SC-011-02 / SC-011-05):
- Wilson 95 % interval by hand (spec section 7: 45 covering trials of 50 give 0.786 to 0.957): p = 0.9, n = 50,
  z = 1.959964: centre (p + z^2 / 2n) / (1 + z^2 / n) = 0.9384146 / 1.0768292 = 0.871466, half width
  z sqrt(p (1 - p) / n + z^2 / 4 n^2) / (1 + z^2 / n) = 0.085065, i.e. (0.78640, 0.95653); the closed forms for k = 0
  (upper z^2 / (n + z^2) = 0.071346) and k = n (lower 1 - 0.071346 = 0.928654) are also written out;
- the paired percentile bootstrap bounds from injected resamples (numpy): with the resample index matrix supplied by the
  test, the bounds are `numpy.percentile(mean of the resampled paired differences, [2.5, 97.5])`; one case in which
      every
  resample is identical makes the bounds equal under every percentile definition;
- the decision rule FR-000-05: a verdict "better" only when the paired 95 % interval of the difference excludes 0,
  otherwise the words "no significant difference";
- verdict logic on fixture trial sets built here: 44, 45 and 46 covering trials of 50 (SC-011-02 passes from 45 of 50);
- the study driver on the fake simulator of tests/_calib_fake.py: both arms receive the same truths and targets,
    every seed
  of every role in every trial is distinct, counts of "not identified" and "gradient unreliable" follow the
      per-trial flags.

Expected public API (module `pitstudio.calibration.study`, under `src/pitstudio/calibration/`; error class
`pitstudio.calibration.errors.InvalidCalibrationError`):

    wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]
        Raises InvalidCalibrationError for n < 1, k < 0 or k > n.
    draw_truths(n: int, seed: int) -> np.ndarray      n values uniform in [0.3, 0.8] from a seeded generator
        (reproducible).
    paired_bootstrap(a, b, *, resamples=10_000, seed, indices=None) -> BootstrapResult
        differences d_i = a_i - b_i over pairs (trials); `indices` (optional int array [B, n]) replaces the random
        resampling (injected resamples); attributes mean_diff, ci_lower, ci_upper (2.5th and 97.5th percentiles of the
        resampled means). Raises InvalidCalibrationError for fewer than 2 pairs or lengths that differ.
    compare_arms(a, b, *, name_a, name_b, metric, lower_is_better=True, resamples=10_000, seed) -> dict
        {"verdict": "a" | "b" | "no significant difference", "mean_diff", "ci": (lo, hi), "statement": str}; "a" (resp.
        "b") only when the interval excludes 0 on the side that makes a (b) better; the statement contains the words
        "no significant difference" exactly when the verdict does.
    summarise_arm(trials: list[dict], *, parameter=0, expected_trials=None) -> dict      (`expected_trials`: see
        T-011-096)
        trials: DC-011-04 documents of one arm. {"n_trials", "covering", "coverage", "wilson": (lo, hi),
        "not_identified", "gradient_unreliable", "abs_error": {"mean", "median", "max"}, "interval_width":
        {"mean", "median", "max"}, "simulations": {"mean", "total"}, "wall_time_s": {"mean", "total"},
        "sc_011_02": "pass" | "fail"}; covering counts the documents whose parameter has covers_truth True;
        pass iff covering / n_trials >= 0.90 (45 of 50).
    run_coverage_study(simulator, arms, *, n_trials=50, seed, packing_seeds=2, interval_runs=8) -> dict
        simulator: the protocol of tests/_calib_fake.py; arms: mapping arm name -> callable(simulator, trial) ->
            dict with
        "mu_hat", "simulations", "wall_time_s" and for the gradient arm "gradient_status" ("reliable" | "unreliable").
        `trial` (dict): index, mu_true, theta_star, seeds {"target": [..], "optimisation": [..], "interval": [..]}.
        For every trial the truth is drawn once (draw_truths(n_trials, seed)), the target theta* =
            simulator.theta(mu_true,
        target seed), and the same trial dict goes to every arm; seeds are distinct across roles and trials. Returns
        {"truths": [...], "arms": {name: {"trials": [DC-011-04-like per-trial records], "summary":
            summarise_arm(...)}}}.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem, z_of  # noqa: E402

from pitstudio.calibration import study  # noqa: E402
from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402

Z95 = 1.959964


def wilson_by_hand(k: int, n: int) -> tuple[float, float]:
    p = k / n
    denom = 1.0 + Z95**2 / n
    centre = (p + Z95**2 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95**2 / (4 * n**2)) / denom
    return centre - half, centre + half


# ------------------------------------------------------------------ FR-011-24 Wilson interval


@pytest.mark.req("FR-011-24")
def test_wilson_interval_for_45_of_50_is_the_spec_hand_value() -> None:
    lo, hi = study.wilson_interval(45, 50)
    assert lo == pytest.approx(0.78640, abs=2e-5)
    assert hi == pytest.approx(0.95653, abs=2e-5)
    assert (round(lo, 3), round(hi, 3)) == (0.786, 0.957)  # the values quoted in spec section 7


@pytest.mark.req("FR-011-24")
@pytest.mark.parametrize(("k", "n"), [(0, 50), (50, 50), (1, 50), (25, 50), (43, 50), (7, 8)])
def test_wilson_interval_equals_the_closed_form(k: int, n: int) -> None:
    lo, hi = study.wilson_interval(k, n)
    elo, ehi = wilson_by_hand(k, n)
    assert lo == pytest.approx(elo, abs=1e-6)
    assert hi == pytest.approx(ehi, abs=1e-6)


@pytest.mark.req("FR-011-24")
def test_wilson_interval_at_the_extremes_is_the_closed_form_and_stays_inside_zero_one() -> None:
    lo0, hi0 = study.wilson_interval(0, 50)
    assert lo0 == pytest.approx(0.0, abs=1e-12)
    assert hi0 == pytest.approx(3.841459 / (50 + 3.841459), abs=1e-6)  # z^2 / (n + z^2) = 0.071346
    lo1, hi1 = study.wilson_interval(50, 50)
    assert hi1 == pytest.approx(1.0, abs=1e-12)
    assert lo1 == pytest.approx(1.0 - 0.071346, abs=1e-5)


@pytest.mark.req("FR-011-24")
@pytest.mark.parametrize(("k", "n"), [(1, 0), (-1, 50), (51, 50), (0, 0)])
def test_wilson_interval_rejects_impossible_counts(k: int, n: int) -> None:
    with pytest.raises(InvalidCalibrationError):
        study.wilson_interval(k, n)


@pytest.mark.req("FR-011-24")
def test_the_truths_are_uniform_in_0_3_to_0_8_and_reproducible_by_seed() -> None:
    a = study.draw_truths(50, 17)
    b = study.draw_truths(50, 17)
    c = study.draw_truths(50, 18)
    assert a.shape == (50,)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert a.min() >= 0.3
    assert a.max() <= 0.8
    big = study.draw_truths(20_000, 1)
    assert big.mean() == pytest.approx(0.55, abs=0.005)  # uniform on [0.3, 0.8]: mean 0.55, sd 0.1443 / sqrt(20000)
    assert big.std() == pytest.approx(0.5 / math.sqrt(12.0), abs=0.005)


# ------------------------------------------------------------------ FR-011-25 paired bootstrap and the decision rule


@pytest.mark.req("FR-011-25")
def test_identical_resamples_give_identical_bounds_under_every_percentile_definition() -> None:
    a = [3.0, 5.0, 4.0, 6.0]
    b = [1.0, 2.0, 3.0, 4.0]  # d = (2, 3, 1, 2), mean 2
    idx = np.tile(np.arange(4), (50, 1))
    res = study.paired_bootstrap(a, b, seed=0, indices=idx)
    assert res.mean_diff == pytest.approx(2.0, abs=1e-12)
    assert res.ci_lower == pytest.approx(2.0, abs=1e-12)
    assert res.ci_upper == pytest.approx(2.0, abs=1e-12)


@pytest.mark.req("FR-011-25")
def test_percentile_bounds_of_injected_resamples_equal_numpy_percentiles() -> None:
    rng = np.random.default_rng(4)
    a = rng.normal(5.0, 1.0, 30)
    b = rng.normal(4.7, 1.0, 30)
    idx = rng.integers(0, 30, size=(2000, 30))
    d = a - b
    means = d[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    res = study.paired_bootstrap(a, b, seed=0, indices=idx)
    assert res.ci_lower == pytest.approx(lo, rel=1e-9)
    assert res.ci_upper == pytest.approx(hi, rel=1e-9)
    assert res.mean_diff == pytest.approx(d.mean(), rel=1e-12)


@pytest.mark.req("FR-011-25")
def test_the_default_bootstrap_uses_ten_thousand_reproducible_resamples() -> None:
    rng = np.random.default_rng(8)
    a, b = rng.normal(1.0, 1.0, 40), rng.normal(0.0, 1.0, 40)
    first = study.paired_bootstrap(a, b, seed=123)
    again = study.paired_bootstrap(a, b, seed=123)
    other = study.paired_bootstrap(a, b, seed=124)
    assert (first.ci_lower, first.ci_upper) == (again.ci_lower, again.ci_upper)
    assert (first.ci_lower, first.ci_upper) != (other.ci_lower, other.ci_upper)
    # the percentile interval of a mean of 40 differences: about mean +/- 1.96 sd / sqrt(40)
    d = a - b
    half = 1.96 * d.std(ddof=1) / math.sqrt(40)
    assert first.ci_lower == pytest.approx(d.mean() - half, abs=0.08)
    assert first.ci_upper == pytest.approx(d.mean() + half, abs=0.08)


@pytest.mark.req("FR-011-25")
def test_a_clear_paired_advantage_is_called_better_and_names_the_winner() -> None:
    err_cma = np.full(50, 0.03)
    err_grad = np.full(50, 0.01)  # the gradient arm is more accurate in every pair
    out = study.compare_arms(
        err_grad, err_cma, name_a="gradient", name_b="cma-es", metric="absolute error", lower_is_better=True, seed=1
    )
    assert out["verdict"] == "a"
    assert out["ci"][1] < 0.0
    assert "gradient" in out["statement"]
    assert "no significant difference" not in out["statement"]


@pytest.mark.req("FR-011-25")
def test_a_difference_that_the_interval_does_not_exclude_is_no_significant_difference() -> None:
    a = np.array([1.0, -1.0] * 25)  # paired differences alternate +-1: mean 0, interval contains 0
    b = np.zeros(50)
    out = study.compare_arms(a, b, name_a="gradient", name_b="cma-es", metric="wall time", lower_is_better=True, seed=1)
    assert out["verdict"] == "no significant difference"
    assert "no significant difference" in out["statement"]
    assert out["ci"][0] < 0.0 < out["ci"][1]


@pytest.mark.req("FR-011-25")
def test_the_direction_flag_swaps_the_winner() -> None:
    narrower = study.compare_arms(
        np.full(30, 1.0),
        np.full(30, 2.0),
        name_a="gradient",
        name_b="cma-es",
        metric="width",
        lower_is_better=True,
        seed=2,
    )
    wider = study.compare_arms(
        np.full(30, 1.0),
        np.full(30, 2.0),
        name_a="gradient",
        name_b="cma-es",
        metric="coverage",
        lower_is_better=False,
        seed=2,
    )
    assert narrower["verdict"] == "a"
    assert wider["verdict"] == "b"


@pytest.mark.req("FR-011-25")
@pytest.mark.parametrize(
    ("a", "b"),
    [([1.0], [2.0]), ([], []), ([1.0, 2.0, 3.0], [1.0, 2.0]), ([1.0, float("nan")], [1.0, 2.0])],
    ids=["one-pair", "empty", "unpaired-lengths", "nan"],
)
def test_too_few_unpaired_or_non_finite_pairs_are_rejected(a: list[float], b: list[float]) -> None:
    with pytest.raises(InvalidCalibrationError):
        study.paired_bootstrap(a, b, seed=0)
    with pytest.raises(InvalidCalibrationError):
        study.compare_arms(a, b, name_a="x", name_b="y", metric="m", seed=0)


# ------------------------------------------------------------------ SC-011-02 / SC-011-05 verdicts on fixture
#   trial sets


def trial_doc(k: int, covers: bool, *, identification: str = "identified", status: str | None = None) -> dict:
    doc = {
        "trial_id": f"t{k:03d}",
        "arm": "gradient" if status is not None else "cma-es",
        "simulations": 40 + k,
        "wall_time_s": 1.0 + 0.1 * k,
        "parameters": [
            {
                "name": "sliding_friction",
                "truth": 0.5,
                "estimate": 0.5 + 0.01 * (k % 5),
                "identification": identification,
                "covers_truth": covers,
                "interval": {
                    "lower": 0.4 if identification == "identified" else None,
                    "upper": 0.6 if identification == "identified" else None,
                },
            }
        ],
    }
    if status is not None:
        doc["gradient_status"] = status
    return doc


def fixture_set(covering: int, n: int = 50) -> list[dict]:
    return [trial_doc(k, k < covering) for k in range(n)]


@pytest.mark.req("SC-011-02")
@pytest.mark.parametrize(("covering", "verdict"), [(44, "fail"), (45, "pass"), (46, "pass"), (50, "pass"), (0, "fail")])
def test_sc_011_02_passes_from_45_covering_trials_of_50(covering: int, verdict: str) -> None:
    s = study.summarise_arm(fixture_set(covering))
    assert s["n_trials"] == 50
    assert s["covering"] == covering
    assert s["coverage"] == pytest.approx(covering / 50)
    assert s["sc_011_02"] == verdict
    elo, ehi = wilson_by_hand(covering, 50)
    assert s["wilson"][0] == pytest.approx(elo, abs=1e-6)
    assert s["wilson"][1] == pytest.approx(ehi, abs=1e-6)


@pytest.mark.req("FR-011-24")
def test_the_summary_counts_not_identified_and_unreliable_trials_and_never_counts_them_as_covering() -> None:
    trials = fixture_set(45)
    trials[3] = trial_doc(3, False, identification="not-identified")
    trials[7] = trial_doc(7, False, identification="not-identified")
    trials[10] = trial_doc(10, False, status="unreliable")
    trials[11] = trial_doc(11, False, status="reliable")
    s = study.summarise_arm(trials)
    assert s["not_identified"] == 2
    assert s["gradient_unreliable"] == 1
    assert s["covering"] == sum(t["parameters"][0]["covers_truth"] for t in trials)
    assert s["simulations"]["total"] == sum(t["simulations"] for t in trials)
    assert s["simulations"]["mean"] == pytest.approx(sum(t["simulations"] for t in trials) / 50)
    assert s["wall_time_s"]["total"] == pytest.approx(sum(t["wall_time_s"] for t in trials))


@pytest.mark.req("FR-011-24")
def test_the_summary_reports_absolute_error_and_interval_width_statistics() -> None:
    trials = fixture_set(50)
    errs = sorted(abs(t["parameters"][0]["estimate"] - 0.5) for t in trials)
    s = study.summarise_arm(trials)
    assert s["abs_error"]["mean"] == pytest.approx(sum(errs) / 50, abs=1e-12)
    assert s["abs_error"]["max"] == pytest.approx(max(errs), abs=1e-12)
    assert s["abs_error"]["median"] == pytest.approx(float(np.median(errs)), abs=1e-12)
    assert s["interval_width"]["mean"] == pytest.approx(0.2, abs=1e-12)  # every identified interval is [0.4, 0.6]


@pytest.mark.req("SC-011-05")
def test_a_large_mean_difference_with_a_huge_spread_is_not_called_better() -> None:
    # paired differences (10, -9, 12, -11, 9, -10) x 5: mean 0.1667, standard deviation about 10.3: the 95 % interval of
    # the mean (about +/- 3.8) contains 0, so the statement must be "no significant difference"
    d = np.array([10.0, -9.0, 12.0, -11.0, 9.0, -10.0] * 5)
    out = study.compare_arms(
        d + 5.0,
        np.full(30, 5.0),
        name_a="surrogate",
        name_b="baseline",
        metric="repose error",
        lower_is_better=True,
        seed=7,
    )
    assert out["verdict"] == "no significant difference"
    assert "no significant difference" in out["statement"]
    assert out["mean_diff"] == pytest.approx(d.mean(), abs=1e-12)


@pytest.mark.req("SC-011-05")
def test_a_small_but_consistent_paired_difference_is_called_better() -> None:
    rng = np.random.default_rng(3)
    base = rng.normal(10.0, 3.0, 50)  # large between-trial spread, tiny paired noise
    out = study.compare_arms(
        base - 0.5 + rng.normal(0.0, 0.05, 50),
        base,
        name_a="gradient",
        name_b="cma-es",
        metric="wall time",
        lower_is_better=True,
        seed=7,
    )
    assert out["verdict"] == "a"
    assert out["ci"][1] < 0.0


# ------------------------------------------------------------------ FR-011-24 the study driver


def exact_arm(fake: FakeDem, status: str | None = None):
    def run(simulator, trial: dict) -> dict:
        s_opt = trial["seeds"]["optimisation"]
        mean_noise = float(np.mean([simulator.theta(0.0, s) - simulator.a for s in s_opt]))
        mu_hat = (trial["theta_star"] - simulator.a - mean_noise) / simulator.b
        out = {"mu_hat": min(max(mu_hat, 0.1), 1.0), "simulations": 40, "wall_time_s": 0.5}
        if status is not None:
            out["gradient_status"] = status
        return out

    return run


@pytest.mark.req("FR-011-24")
def test_the_study_gives_both_arms_the_same_truths_targets_and_distinct_seeds() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    seen: dict[str, list[dict]] = {"gradient": [], "cma-es": []}

    def recording(name: str):
        inner = exact_arm(fake, "reliable" if name == "gradient" else None)

        def run(simulator, trial):
            seen[name].append(trial)
            return inner(simulator, trial)

        return run

    out = study.run_coverage_study(
        fake, {"gradient": recording("gradient"), "cma-es": recording("cma-es")}, n_trials=50, seed=21
    )
    assert len(seen["gradient"]) == len(seen["cma-es"]) == 50
    truths = study.draw_truths(50, 21)
    assert out["truths"] == pytest.approx(list(truths), rel=1e-12)
    for g, c in zip(seen["gradient"], seen["cma-es"], strict=True):
        assert g["mu_true"] == c["mu_true"]
        assert g["theta_star"] == c["theta_star"]
        assert g["seeds"] == c["seeds"]
    for j, g in enumerate(seen["gradient"]):
        assert g["index"] == j
        assert g["mu_true"] == pytest.approx(truths[j], rel=1e-12)
        assert g["theta_star"] == pytest.approx(
            fake.a + fake.b * truths[j] + 0.3 * z_of(g["seeds"]["target"][0]), abs=1e-9
        )
    every = [s for g in seen["gradient"] for role in ("target", "optimisation", "interval") for s in g["seeds"][role]]
    assert len(every) == len(set(every))  # disjoint across roles and across trials
    assert all(len(g["seeds"]["optimisation"]) == 2 and len(g["seeds"]["interval"]) == 8 for g in seen["gradient"])


@pytest.mark.req("FR-011-24")
def test_the_study_reports_per_arm_summaries_with_fifty_trials_each() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    out = study.run_coverage_study(
        fake, {"gradient": exact_arm(fake, "reliable"), "cma-es": exact_arm(fake)}, n_trials=50, seed=5
    )
    assert set(out["arms"]) == {"gradient", "cma-es"}
    for name in ("gradient", "cma-es"):
        arm = out["arms"][name]
        assert len(arm["trials"]) == 50
        assert arm["summary"]["n_trials"] == 50
        assert 0 <= arm["summary"]["covering"] <= 50
        assert arm["summary"]["wilson"][0] <= arm["summary"]["coverage"] <= arm["summary"]["wilson"][1]
    # exact optimiser, honest interval: coverage near 0.95 (binomial: 50 trials, sd 0.031)
    assert out["arms"]["cma-es"]["summary"]["coverage"] >= 0.84


@pytest.mark.req("FR-011-24")
def test_an_unreliable_gradient_trial_is_counted_and_never_covers() -> None:
    fake = FakeDem(24.0, 20.0, sigma=0.3)
    flagged = {4, 9, 30}

    def gradient(simulator, trial):
        res = exact_arm(fake, "unreliable" if trial["index"] in flagged else "reliable")(simulator, trial)
        return res

    out = study.run_coverage_study(fake, {"gradient": gradient, "cma-es": exact_arm(fake)}, n_trials=50, seed=6)
    trials = out["arms"]["gradient"]["trials"]
    assert out["arms"]["gradient"]["summary"]["gradient_unreliable"] == 3
    for j in flagged:
        assert trials[j]["parameters"][0]["covers_truth"] is False
    assert out["arms"]["cma-es"]["summary"]["gradient_unreliable"] == 0


@pytest.mark.req("FR-011-24")
def test_trials_in_a_flat_response_region_are_counted_not_identified_from_the_arms_own_estimates() -> None:
    fake = FakeDem(
        24.0, 20.0, sigma=0.3, flat_above=0.55
    )  # no slope for mu above 0.55: estimates there are not identified

    def on_truth(simulator, trial):  # an arm that returns the truth itself, to place estimates on both sides of 0.55
        return {"mu_hat": trial["mu_true"], "simulations": 40, "wall_time_s": 0.5}

    out = study.run_coverage_study(fake, {"cma-es": on_truth}, n_trials=50, seed=7)
    trials = out["arms"]["cma-es"]["trials"]
    # slope 0 on both finite-difference points iff mu_hat - h = 0.95 mu_hat >= 0.55 (h = 0.05 mu_hat)
    flat = [t for t in trials if 0.95 * t["parameters"][0]["estimate"] >= 0.55]
    assert len(flat) > 0
    assert out["arms"]["cma-es"]["summary"]["not_identified"] == len(flat)
    assert all(t["parameters"][0]["identification"] == "not-identified" for t in flat)
    assert all(t["parameters"][0]["covers_truth"] is False for t in flat)


@pytest.mark.req("FR-011-24")
@pytest.mark.parametrize("n_trials", [0, -3, 1])
def test_a_study_needs_at_least_two_trials(n_trials: int) -> None:
    fake = FakeDem(24.0, 20.0)
    with pytest.raises(InvalidCalibrationError):
        study.run_coverage_study(fake, {"cma-es": exact_arm(fake)}, n_trials=n_trials, seed=1)
