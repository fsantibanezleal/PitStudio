"""T-010-031: paired bootstrap into the decision rule; guards for fewer than two pairs and for unpaired ids.

Requirements: FR-010-25, FR-010-28, P-010-14, SC-010-02.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-25, FR-010-28), section 4 (P-010-14), section 5 (SC-010-02);
plan.md rows FR-010-25 and FR-010-28 ("mean differences and percentile bounds from injected resamples (numpy); FR-000-05
verdict table").

Expected API (module `pitstudio.slope.evaluate`, shared with T-010-030):
- `InsufficientPairsError(ValueError)` and `UnpairedError(ValueError)`.
- `paired_comparison(baseline, model, *, method="tcn", cutoff=0.5, indices=None, resamples=10000, seed=0) -> dict`:
  `baseline` and `model` map event id -> relative error. d_i = e_baseline(i) - e_model(i) over the sorted event ids;
  the 95 % interval of mean(d) is the percentile interval (numpy percentiles 2.5 and 97.5) of the means of resampled d
  (resampling the sorted-id positions; `indices` injects an int array (resamples, n) for exact tests). Result shaped as
  `ttf-results.schema.json#/$defs/comparison`: baseline "inverse_velocity", method, cutoff, stratum "snr_obs", n_pairs,
  mean_difference, interval {lower, upper}, bootstrap {resamples, method "paired-percentile", resample_unit
  "sorted-event-id", level 0.95, seed}, verdict "better" (lower > 0), "worse" (upper < 0) or "no significant
  difference".
  Exactly one pair: {"n_pairs": 1, "verdict": "single real event - no significance test"} (em dash in the text) with no
  interval and no mean-difference field. Zero pairs raise InsufficientPairsError; two sets with different id sets raise
  UnpairedError; neither returns an interval.
- `compare_all(inverse_velocity, models, *, seed, resamples=10000) -> {"comparisons": [...], "multiplicity": {...}}`
  where
  `inverse_velocity` maps cutoff -> {id: e}, `models` maps learned method -> cutoff -> {id: e}; one comparison per
  available (method, cutoff) in the order tcn, patchtst, chronos_bolt_zero_shot, chronos_bolt_fine_tuned x cutoffs
  0.5, 0.8;
  `multiplicity` = {"comparisons": 8, "family_wise_claim": False} whatever number of arms is available.

Oracles: hand-built difference vectors with injected resamples and numpy percentiles; the decision table of the spec
(lower bound > 0 is the only way to "better"); P-010-14 relations (swap negates, constant shift, permutation) on 2-2,000
pairs with a fixed resample matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
from pitstudio.slope import evaluate

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
SINGLE = "single real event — no significance test"


def _ids(n):
    return [f"voight-test-snr-obs-{i:06d}" for i in range(n)]


def _sets(d_values, model_errors=None):
    ids = _ids(len(d_values))
    model = dict(zip(ids, model_errors if model_errors is not None else [0.5] * len(ids), strict=True))
    base = {i: model[i] + d for i, d in zip(ids, d_values, strict=True)}
    return base, model


@pytest.mark.req("FR-010-25")
def test_mean_difference_and_interval_from_injected_resamples_by_hand() -> None:
    d = [0.1, 0.2, 0.3, 0.4]
    base, model = _sets(d)
    idx = np.array([[0, 1, 2, 3], [0, 0, 0, 0], [3, 3, 3, 3], [1, 2, 1, 2], [0, 3, 0, 3], [2, 2, 3, 3]])
    means = np.array(d)[idx].mean(axis=1)  # 0.25, 0.1, 0.4, 0.25, 0.25, 0.35
    lo, hi = np.percentile(means, [2.5, 97.5])
    r = evaluate.paired_comparison(base, model, indices=idx, seed=9)
    assert r["n_pairs"] == 4
    assert r["mean_difference"] == pytest.approx(0.25, rel=1e-12)
    assert r["interval"]["lower"] == pytest.approx(lo, rel=1e-12)
    assert r["interval"]["upper"] == pytest.approx(hi, rel=1e-12)
    assert r["verdict"] == "better"  # lower bound 0.1 + ... > 0
    assert r["baseline"] == "inverse_velocity"
    assert (r["method"], r["cutoff"], r["stratum"]) == ("tcn", 0.5, "snr_obs")
    assert r["bootstrap"]["method"] == "paired-percentile"
    assert r["bootstrap"]["resample_unit"] == "sorted-event-id"
    assert r["bootstrap"]["level"] == 0.95
    assert r["bootstrap"]["seed"] == 9


@pytest.mark.req("SC-010-02")
@pytest.mark.parametrize(
    ("d", "verdict"),
    [
        ([0.1, 0.2, 0.3, 0.4, 0.25, 0.15, 0.35, 0.3], "better"),
        ([-0.1, -0.2, -0.3, -0.4, -0.25, -0.15, -0.35, -0.3], "worse"),
        ([0.5, -0.5, 0.4, -0.4, 0.45, -0.45, 0.3, -0.35], "no significant difference"),
        ([0.0] * 8, "no significant difference"),  # identical methods: the interval is [0, 0], never "better"
    ],
)
def test_the_verdict_is_better_only_when_the_lower_bound_is_above_zero(d, verdict) -> None:
    base, model = _sets(d)
    r = evaluate.paired_comparison(base, model, resamples=2000, seed=3)
    assert r["verdict"] == verdict
    lo, hi = r["interval"]["lower"], r["interval"]["upper"]
    assert (verdict == "better") == (lo > 0)
    assert (verdict == "worse") == (hi < 0)
    assert lo <= r["mean_difference"] <= hi


@pytest.mark.req("FR-010-25")
def test_the_comparison_row_validates_against_the_results_schema_with_the_default_10000_resamples() -> None:
    base, model = _sets(list(np.linspace(-0.05, 0.2, 40)))
    r = evaluate.paired_comparison(base, model, seed=4243)
    assert r["bootstrap"]["resamples"] == 10_000
    assert lem_ref.schema_errors(r, "ttf-results", "comparison") == []


@pytest.mark.req("FR-010-25")
def test_the_default_bootstrap_is_seeded_and_independent_of_the_order_of_the_events() -> None:
    d = list(np.random.default_rng(2).normal(0.03, 0.1, 60))
    base, model = _sets(d)
    a = evaluate.paired_comparison(base, model, seed=5)
    b = evaluate.paired_comparison(dict(reversed(list(base.items()))), dict(reversed(list(model.items()))), seed=5)
    c = evaluate.paired_comparison(base, model, seed=6)
    assert a == b
    assert a["interval"] != c["interval"]
    # the interval is that of the mean of 60 differences: about +-1.96 sd / sqrt(60), a factor-2 band catches a wrong
    # statistic
    half = 1.96 * np.std(d, ddof=1) / np.sqrt(60)
    assert a["interval"]["lower"] == pytest.approx(np.mean(d) - half, abs=0.5 * half)
    assert a["interval"]["upper"] == pytest.approx(np.mean(d) + half, abs=0.5 * half)


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-28: guards


@pytest.mark.req("FR-010-28")
def test_one_pair_returns_the_single_event_verdict_and_never_an_interval() -> None:
    r = evaluate.paired_comparison({"dewit": 0.12}, {"dewit": 0.05})
    assert r == {"n_pairs": 1, "verdict": SINGLE}
    assert "interval" not in r
    assert "mean_difference" not in r
    assert "bootstrap" not in r


@pytest.mark.req("FR-010-28")
def test_no_pairs_raise_insufficient_pairs_error() -> None:
    with pytest.raises(evaluate.InsufficientPairsError):
        evaluate.paired_comparison({}, {})
    assert issubclass(evaluate.InsufficientPairsError, ValueError)


@pytest.mark.req("FR-010-28")
@pytest.mark.parametrize(
    ("base", "model"),
    [
        ({"a": 0.1, "b": 0.2}, {"a": 0.1, "c": 0.2}),  # same size, different ids
        ({"a": 0.1, "b": 0.2, "c": 0.3}, {"a": 0.1, "b": 0.2}),  # one id missing
        ({"a": 0.1, "b": 0.2}, {"a": 0.1, "b": 0.2, "c": 0.3}),
        ({"a": 0.1}, {"b": 0.1}),  # a single unit but not the same unit
        ({"a": 0.1, "b": 0.2}, {}),
    ],
)
def test_unpaired_event_ids_raise_unpaired_error_and_return_no_interval(base, model) -> None:
    with pytest.raises(evaluate.UnpairedError):
        evaluate.paired_comparison(base, model, resamples=100)
    assert issubclass(evaluate.UnpairedError, ValueError)


@pytest.mark.req("FR-010-28")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.5])
def test_non_finite_or_negative_errors_are_rejected(bad) -> None:
    with pytest.raises(ValueError, match=r"."):
        evaluate.paired_comparison({"a": 0.1, "b": bad}, {"a": 0.1, "b": 0.2}, resamples=100)


# ---------------------------------------------------------------------------------------------------------------------
# P-010-14


@st.composite
def _pairs(draw):
    n = draw(st.integers(2, 2000))
    rng = np.random.default_rng(draw(st.integers(0, 2**32 - 1)))
    return rng.uniform(0.0, 3.0, n), rng.uniform(0.0, 3.0, n)


def _idx(n):
    return np.random.default_rng(0).integers(0, n, size=(100, n))


def _pair_dicts(e_base, e_model):
    ids = _ids(len(e_base))
    return dict(zip(ids, map(float, e_base), strict=True)), dict(zip(ids, map(float, e_model), strict=True))


@pytest.mark.req("P-010-14")
@PROP
@given(_pairs())
def test_swapping_the_two_methods_negates_the_interval(case) -> None:
    b, m = _pair_dicts(*case)
    n = len(b)
    ab = evaluate.paired_comparison(b, m, indices=_idx(n))
    ba = evaluate.paired_comparison(m, b, indices=_idx(n))
    assert ba["mean_difference"] == pytest.approx(-ab["mean_difference"], rel=1e-12, abs=1e-12)
    assert ba["interval"]["lower"] == pytest.approx(-ab["interval"]["upper"], rel=1e-9, abs=1e-12)
    assert ba["interval"]["upper"] == pytest.approx(-ab["interval"]["lower"], rel=1e-9, abs=1e-12)


@pytest.mark.req("P-010-14")
@PROP
@given(_pairs(), st.floats(0.0, 5.0))
def test_adding_kappa_to_every_model_error_shifts_the_interval_by_minus_kappa(case, kappa) -> None:
    b, m = _pair_dicts(*case)
    shifted = {i: v + kappa for i, v in m.items()}
    n = len(b)
    r0 = evaluate.paired_comparison(b, m, indices=_idx(n))
    r1 = evaluate.paired_comparison(b, shifted, indices=_idx(n))
    assert r1["interval"]["lower"] == pytest.approx(r0["interval"]["lower"] - kappa, abs=1e-9)
    assert r1["interval"]["upper"] == pytest.approx(r0["interval"]["upper"] - kappa, abs=1e-9)
    assert r1["mean_difference"] == pytest.approx(r0["mean_difference"] - kappa, abs=1e-9)


@pytest.mark.req("P-010-14")
@PROP
@given(_pairs(), st.integers(0, 2**32 - 1))
def test_permuting_the_event_order_leaves_the_interval_unchanged(case, seed) -> None:
    b, m = _pair_dicts(*case)
    order = np.random.default_rng(seed).permutation(len(b))
    keys = list(b)
    pb = {keys[i]: b[keys[i]] for i in order}
    pm = {keys[i]: m[keys[i]] for i in order}
    n = len(b)
    assert evaluate.paired_comparison(pb, pm, indices=_idx(n)) == evaluate.paired_comparison(b, m, indices=_idx(n))


# ---------------------------------------------------------------------------------------------------------------------
# the eight comparisons


def _errors(rng, shift=0.0, n=30):
    return {f"voight-test-snr-obs-{i:06d}": float(v) for i, v in enumerate(rng.uniform(0.0, 0.5, n) + shift)}


@pytest.mark.req("FR-010-25")
def test_compare_all_makes_eight_comparisons_and_states_no_family_wise_claim() -> None:
    rng = np.random.default_rng(3)
    iv = {0.5: _errors(rng, 0.5), 0.8: _errors(rng, 0.5)}
    methods = ["tcn", "patchtst", "chronos_bolt_zero_shot", "chronos_bolt_fine_tuned"]
    models = {
        m: {
            0.5: dict(zip(iv[0.5], _errors(rng).values(), strict=True)),
            0.8: dict(zip(iv[0.8], _errors(rng).values(), strict=True)),
        }
        for m in methods
    }
    out = evaluate.compare_all(iv, models, seed=4243)
    assert [(c["method"], c["cutoff"]) for c in out["comparisons"]] == [(m, c) for m in methods for c in (0.5, 0.8)]
    assert out["multiplicity"] == {"comparisons": 8, "family_wise_claim": False}
    assert all(c["verdict"] == "better" for c in out["comparisons"])  # models are 0.5 better by construction
    for c in out["comparisons"]:
        assert lem_ref.schema_errors(c, "ttf-results", "comparison") == []


@pytest.mark.req("FR-010-25")
def test_compare_all_with_a_missing_arm_still_states_eight_and_lists_only_available_rows() -> None:
    rng = np.random.default_rng(4)
    iv = {0.5: _errors(rng, 0.1), 0.8: _errors(rng, 0.1)}
    models = {"tcn": {0.5: dict(zip(iv[0.5], _errors(rng).values(), strict=True))}}
    out = evaluate.compare_all(iv, models, seed=1)
    assert [(c["method"], c["cutoff"]) for c in out["comparisons"]] == [("tcn", 0.5)]
    assert out["multiplicity"] == {"comparisons": 8, "family_wise_claim": False}
