"""T-017-047: per-flight metrics and paired comparisons (pipeline).

Requirements: FR-017-39, FR-017-40, SC-017-06.

Spec: specs/017-planning-survey/spec.md
- FR-017-39: `s50_evaluate` reports per flight and seed the volume error 100 (V_hat - V) / V (%) of fill and cut
  for the
  photogrammetric and the splat surfaces, the gridding floor, the reprojection RMSE (px), the alignment RMSE (m), the
  median absolute depth error against the rendered depth (m), the GSD and the image registration ratio; no pass
  threshold
  applies;
- FR-017-40: any statement that one surface or one survey design gives a smaller volume error than another comes from
  paired differences of |error| over flights x seeds through the decision rule (FR-000-05) with a paired percentile
  bootstrap (B = 10,000); otherwise "no significant difference";
- SC-017-06: survey volume error reported for every survey design and seed against exact truth, with no pass threshold
  (pre-registered); the report has one row per design and seed and no pass field.
plan.md test strategy rows FR-017-39 (contract of the per-flight block; volume error by hand on a fixture), FR-017-40
(paired bootstrap bounds from injected resamples (numpy)), SC-017-06 (one row per design and seed and no pass field).

Oracles (hand calculation and numpy):
- the volume error by hand: V = 1,000 m^3 and V_hat = 1,014.2 -> 1.42 %; V_hat = 990 -> -1.0 %;
- the alignment RMSE = sqrt(mean over points of |residual vector|^2) (residuals (0.03, 0, 0) and (0, 0.04, 0):
  sqrt((0.0009
  + 0.0016) / 2) = 0.035355339), the median absolute depth error (|pred - true| over finite pairs: 0.01, 0.02, 0.09 ->
  0.02), the registration ratio 28 / 30;
- the paired percentile bootstrap written in the test with numpy on injected resample indices: for paired
  differences d_i
  = |e_a,i| - |e_b,i| the bootstrap means over the resamples, the 2.5 and 97.5 percentiles (`numpy.percentile`),
  the claim
  "A smaller than B" iff the interval is entirely below 0 (and "B smaller than A" iff entirely above), else "no
  significant
  difference" (FR-000-05);
- the DC-017-04 schema (`jsonschema`) and the spec's synthetic photogrammetric volume example as the base document.

Expected public API (module `pitstudio.survey.report`, numpy only; used by `s50_evaluate` in `pipeline/`):
    volume_error_pct(v_hat: float, v_true: float) -> float                # 100 (v_hat - v_true) / v_true;
    ValueError for
                                                                          # v_true <= 0 or non-finite values
    alignment_rmse_m(residuals: np.ndarray (n, 3)) -> float
    median_abs_depth_error_m(predicted: np.ndarray, rendered: np.ndarray) -> float   # over pairs where both are
    finite
    registration_ratio(n_registered: int, n_total: int) -> float
    survey_row(*, flight: str, seed: int, method: str, v_fill_m3, v_cut_m3, truth: Mapping, floor: Mapping,
               reprojection_rmse_px, alignment_residuals, depth_predicted, depth_rendered, gsd_cm_per_px,
               n_registered, n_total, base: Mapping) -> dict
        the DC-017-04 volume object of a synthetic flight: `base` supplies surfaces, grid, polygon and cells (as in
        the
        spec example); id f"{flight}-s{seed}-{method}", scope "synthetic", status "ok", v_fill/v_cut/v_net, and an
        `errors`
        block {fill_pct, cut_pct, floor_fill_pct, floor_cut_pct, reprojection_rmse_px, alignment_rmse_m,
        depth_abs_median_m, gsd_cm_per_px, registration_ratio}; no key named pass / passed / threshold / ok_flag
        anywhere.
    @dataclass Comparison: statement: str, mean_difference: float, ci_low: float, ci_high: float, resamples: int
    compare_methods(abs_errors_a, abs_errors_b, *, a_name: str, b_name: str, seed: int = 0, resamples: int = 10_000,
                    resample_indices: np.ndarray | None = None) -> Comparison
        statement "<a_name> gives a smaller volume error than <b_name>", "<b_name> gives a smaller volume error than
        <a_name>" or exactly "no significant difference"; `resample_indices` (B, n) integers replace the random draws
        (then `resamples` is B); ValueError for different lengths, fewer than 2 pairs, non-finite or negative errors.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from pitstudio.survey.report import (
    alignment_rmse_m,
    compare_methods,
    median_abs_depth_error_m,
    registration_ratio,
    survey_row,
    volume_error_pct,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads(
    (ROOT / "specs/017-planning-survey/contracts/examples/survey-volume.valid.json").read_text("utf-8")
)
SYNTHETIC = EXAMPLE["volumes"][1]
SCHEMA = json.loads((ROOT / "contracts" / "survey-volume.schema.json").read_text("utf-8"))


def _errors(volumes: list[dict]) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(SCHEMA).iter_errors({"schema_version": "1.0", "volumes": volumes}))


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-39
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-39")
def test_the_volume_error_by_hand() -> None:
    assert volume_error_pct(1014.2, 1000.0) == pytest.approx(1.42, rel=1e-12)
    assert volume_error_pct(990.0, 1000.0) == pytest.approx(-1.0, rel=1e-12)
    assert volume_error_pct(1000.0, 1000.0) == 0.0


@pytest.mark.req("FR-017-39")
@pytest.mark.parametrize(
    ("v_hat", "v_true"), [(1.0, 0.0), (1.0, -5.0), (float("nan"), 10.0), (1.0, float("inf")), (float("inf"), 1.0)]
)
def test_hostile_volumes_are_refused(v_hat: float, v_true: float) -> None:
    with pytest.raises(ValueError, match=r"."):
        volume_error_pct(v_hat, v_true)


@pytest.mark.req("FR-017-39")
def test_the_alignment_rmse_the_depth_error_and_the_registration_ratio_by_hand() -> None:
    residuals = np.array([[0.03, 0.0, 0.0], [0.0, 0.04, 0.0]])
    assert alignment_rmse_m(residuals) == pytest.approx(np.sqrt((0.0009 + 0.0016) / 2), rel=1e-12)
    predicted = np.array([1.00, 2.00, 3.00, np.nan, 5.0])
    rendered = np.array([1.01, 2.02, 3.09, 4.0, np.nan])
    assert median_abs_depth_error_m(predicted, rendered) == pytest.approx(0.02, rel=1e-9)  # |0.01|, |0.02|, |0.09|
    assert registration_ratio(28, 30) == pytest.approx(28 / 30, rel=1e-12)
    assert registration_ratio(0, 30) == 0.0


@pytest.mark.req("FR-017-39")
def test_degenerate_metric_inputs_are_refused() -> None:
    with pytest.raises(ValueError, match=r"."):
        alignment_rmse_m(np.zeros((0, 3)))
    with pytest.raises(ValueError, match=r"."):
        median_abs_depth_error_m(np.array([np.nan]), np.array([1.0]))  # no finite pair
    with pytest.raises(ValueError, match=r"."):
        registration_ratio(5, 0)
    with pytest.raises(ValueError, match=r"."):
        registration_ratio(31, 30)


def _row(**over) -> dict:
    truth_fill = 9605.0 / 1.0142  # chosen so that the fill error is exactly +1.42 %
    truth_cut = 11880.0 / 0.99  # and the cut error exactly -1.0 %
    args = {
        "flight": "f01", "seed": 0, "method": "photogrammetric", "v_fill_m3": 9605.0, "v_cut_m3": 11880.0,
        "truth": {"fill": truth_fill, "cut": truth_cut}, "floor": {"fill_pct": 0.05, "cut_pct": -0.04},
        "reprojection_rmse_px": 0.61, "alignment_residuals": np.array([[0.012, 0.0, 0.0]] * 3 + [[0.0, 0.0, 0.0]] * 3),
        "depth_predicted": np.array([1.0, 2.0, 3.0]), "depth_rendered": np.array([1.034, 2.034, 3.034]),
        "gsd_cm_per_px": 2.0, "n_registered": 29, "n_total": 30, "base": SYNTHETIC,
    }  # fmt: skip
    args.update(over)
    return survey_row(**args)


@pytest.mark.req("FR-017-39")
def test_the_per_flight_block_holds_every_reported_metric_and_validates() -> None:
    row = _row()
    assert row["id"] == "f01-s0-photogrammetric"
    assert (row["scope"], row["method"], row["status"]) == ("synthetic", "photogrammetric", "ok")
    assert (row["v_fill_m3"], row["v_cut_m3"], row["v_net_m3"]) == (9605.0, 11880.0, 9605.0 - 11880.0)
    e = row["errors"]
    assert e["fill_pct"] == pytest.approx(1.42, rel=1e-9)
    assert e["cut_pct"] == pytest.approx(-1.0, rel=1e-9)
    assert (e["floor_fill_pct"], e["floor_cut_pct"]) == (0.05, -0.04)
    assert e["reprojection_rmse_px"] == 0.61
    assert e["alignment_rmse_m"] == pytest.approx(np.sqrt(3 * 0.012**2 / 6), rel=1e-12)
    assert e["depth_abs_median_m"] == pytest.approx(0.034, rel=1e-9)
    assert e["gsd_cm_per_px"] == 2.0
    assert e["registration_ratio"] == pytest.approx(29 / 30, rel=1e-12)
    assert _errors([row]) == []


@pytest.mark.req("FR-017-39")
def test_the_splat_row_has_its_own_id_and_the_same_metric_block() -> None:
    splat = _row(method="splat")
    assert splat["id"] == "f01-s0-splat"
    assert splat["method"] == "splat"
    assert set(splat["errors"]) == set(_row()["errors"])


# ----------------------------------------------------------------------------------------------------------------------
# SC-017-06
# ----------------------------------------------------------------------------------------------------------------------


def _keys(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _keys(v)}
    return set()


@pytest.mark.req("SC-017-06")
def test_the_report_has_one_row_per_design_seed_and_method_and_no_pass_field() -> None:
    rows = [
        _row(flight=f"f{f:02d}", seed=s, method=m, base=copy.deepcopy(SYNTHETIC))
        for f in range(1, 13)
        for s in range(3)
        for m in ("photogrammetric", "splat")
    ]
    assert len(rows) == 72
    assert len({r["id"] for r in rows}) == 72
    assert _errors(rows) == []
    assert not (_keys(rows) & {"pass", "passed", "threshold", "ok_flag", "accept", "accepted", "verdict"})


@pytest.mark.req("SC-017-06")
def test_errors_of_every_sign_and_size_are_reported_without_a_verdict() -> None:
    bad = _row(v_fill_m3=19_000.0)  # an error of about +100 %: reported, not judged
    assert bad["errors"]["fill_pct"] > 90.0
    assert "pass" not in _keys([bad])
    assert _errors([bad]) == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-40
# ----------------------------------------------------------------------------------------------------------------------


def _hand_bootstrap(a, b, idx):
    d = np.abs(np.asarray(a)) - np.abs(np.asarray(b))
    means = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


@pytest.mark.req("FR-017-40")
def test_the_interval_comes_from_the_injected_paired_resamples() -> None:
    a = np.array([1.0, 2.0, 1.5, 0.5, 1.0, 2.5])
    b = np.array([2.0, 2.5, 3.0, 1.5, 1.2, 4.0])
    idx = np.random.default_rng(3).integers(0, 6, size=(2000, 6))
    c = compare_methods(a, b, a_name="photogrammetry", b_name="splat", resample_indices=idx)
    mean, lo, hi = _hand_bootstrap(a, b, idx)
    assert c.mean_difference == pytest.approx(mean, rel=1e-12)
    assert c.ci_low == pytest.approx(lo, rel=1e-12)
    assert c.ci_high == pytest.approx(hi, rel=1e-12)
    assert c.resamples == 2000
    assert hi < 0  # every paired difference is negative here: the interval excludes 0
    assert c.statement == "photogrammetry gives a smaller volume error than splat"


@pytest.mark.req("FR-017-40")
def test_the_reverse_claim_needs_the_interval_above_zero() -> None:
    a = np.array([3.0, 4.0, 3.5, 5.0])
    b = np.array([1.0, 1.0, 1.5, 2.0])
    idx = np.random.default_rng(4).integers(0, 4, size=(1000, 4))
    c = compare_methods(a, b, a_name="A", b_name="B", resample_indices=idx)
    assert c.statement == "B gives a smaller volume error than A"


@pytest.mark.req("FR-017-40")
def test_an_interval_containing_zero_gives_no_significant_difference() -> None:
    a = np.array([1.0, 3.0, 1.0, 3.0, 1.0, 3.0])
    b = np.array([3.0, 1.0, 3.0, 1.0, 3.0, 1.0])  # differences alternate -2, +2: mean 0
    idx = np.random.default_rng(5).integers(0, 6, size=(2000, 6))
    c = compare_methods(a, b, a_name="A", b_name="B", resample_indices=idx)
    mean, lo, hi = _hand_bootstrap(a, b, idx)
    assert lo < 0 < hi
    assert c.statement == "no significant difference"
    assert c.mean_difference == pytest.approx(mean, abs=1e-12)


@pytest.mark.req("FR-017-40")
def test_identical_errors_give_no_significant_difference() -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert compare_methods(a, a.copy(), a_name="A", b_name="B", seed=1).statement == "no significant difference"


@pytest.mark.req("FR-017-40")
def test_the_default_bootstrap_uses_10000_seeded_resamples() -> None:
    a = np.array([1.0, 2.0, 1.5, 0.5, 1.0, 2.5])
    b = np.array([2.0, 2.5, 3.0, 1.5, 1.2, 4.0])
    first = compare_methods(a, b, a_name="A", b_name="B", seed=11)
    again = compare_methods(a, b, a_name="A", b_name="B", seed=11)
    assert first.resamples == 10_000
    assert (first.ci_low, first.ci_high) == (again.ci_low, again.ci_high)  # deterministic given the seed


@pytest.mark.req("FR-017-40")
@pytest.mark.parametrize(
    ("a", "b"),
    [([1.0, 2.0], [1.0]), ([1.0], [1.0]), ([1.0, float("nan")], [1.0, 2.0]), ([1.0, -2.0], [1.0, 2.0]), ([], [])],
)
def test_hostile_error_lists_are_refused(a, b) -> None:
    with pytest.raises(ValueError, match=r"."):
        compare_methods(np.array(a), np.array(b), a_name="A", b_name="B")
