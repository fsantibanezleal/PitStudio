"""T-011-053 - FR-011-35, FR-011-42, SC-011-03: relative L2 per field, KPIs, volume error, resolution transfer.

Oracles (independent of the code under test; plan 011 test strategy FR-011-35 / FR-011-42: "hand-computed relative
    L2, area, arrival
time and volume on 4 x 4 and 64 x 64 synthetic fields"):
- relative L2 = ||u_hat - u||_2 / ||u||_2 by hand: a field of ones (norm 4 on 4 x 4, 64 on 64 x 64) predicted as
    ones + 0.1 has error
  norm 0.4 (resp. 6.4): 0.1; a field that is zero except one cell of 3.0 predicted as 3.3 there: 0.3 / 3.0 = 0.1;
- the empty-field rule of spec section 7: a solver field with norm below 1e-9 is excluded from the mean and counted;
- statistics: ten per-scenario errors (0.01, ..., 0.08, 0.09, 0.09) whose last two values are equal, so that the
    90th percentile is 0.09
  under every definition, mean (0.36 + 0.18) / 10 = 0.054;
- KPIs on 4 x 4 grids, cell 8 m (cell area 64 m^2), h_thr = 0.5 m, T_end = 3,600 s (output times 450 k s). Truth
    depths h(t_k) = 0.1 k at cell
  (0, 0) and 1.0 at cell (1, 1) from k = 2 (0 before), h_max = (0.8 at (0, 0), 1.0 at (1, 1)): inundated area 2 x
      64 = 128 m^2;
  arrival at (1, 1): first k with h >= 0.5 is k = 2 -> 900 s, at (0, 0): k = 5 -> 2,250 s; maximum depth 1.0 m;
      volume of h(t_1) =
  0.1 x 64 = 6.4 m^3 and of h(t_2) = (0.2 + 1.0) x 64 = 76.8 m^3. A prediction with (3, 3) at 0.6 m in h_max has
      area 192 m^2 (abs
  error 64, relative 0.5); arrival at (1, 1) one snapshot later (k = 3, 1,350 s: error 450 s); depths x 1.05 give
      volume errors 0.05;
- SC-011-03: mean relative L2 of h_max (tailings) or of the time-averaged concentration (dust) <= 0.05
    (`models.fno_rel_l2_mean_max`
  of thresholds.yaml); 0.04999 passes and 0.0501 fails (no case sits on 0.05 itself: the last binary64 digit of a
      norm ratio is not
  specified).

Expected public API (module `pitstudio_pipeline.surrogates.fno.evaluate`, package under `pipeline/src/`; error class
`pitstudio_pipeline.surrogates.errors.EvaluationError`):

    relative_l2(pred, truth) -> float
    evaluate_fno(preds, truths, field_names, *, model) -> dict
        preds, truths: float arrays [S, C, H, W] in physical units (S held-out scenarios); field_names: C names;
            model "tailings" |
        "dust". Returns {"model", "n_scenarios", "fields": {name: {"per_scenario": [float or None], "mean", "p90",
            "n_included",
        "n_excluded_empty"}}, "sc_011_03": "pass" | "fail", "sc_field": "depth_max" | "concentration_mean",
            "threshold": 0.05}.
        Scenarios whose solver field has norm < 1e-9 are None in per_scenario, excluded from mean and p90 and counted.
    tailings_kpi_errors(pred, truth, *, cell_size_m, h_thr_m, checkpoints, t_end_s) -> dict
        pred, truth: [9, H, W] (h(t_1..t_8), h_max); checkpoints: list of (row, col). Returns {"area_m2": {"pred",
            "truth", "abs_error",
        "rel_error"}, "arrival_time_s": [{"checkpoint", "pred", "truth", "abs_error"}], "max_depth_m": {"pred",
            "truth", "abs_error",
        "rel_error"}, "volume_rel_error": [8 floats]}; an arrival that never happens is None and gives abs_error None.
    dust_kpi_errors(pred, truth, *, receptors) -> dict    {"receptors": [{"receptor", "pred", "truth", "abs_error",
        "rel_error"}]}
    evaluate_resolution_transfer(predict, inputs, truths, field_names) -> dict
        predict(inputs) -> predictions on the 128 x 128 grid; returns {"label": "resolution transfer — not
            claimed", "fields": {name:
        {"mean"}}} and no acceptance verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "pipeline" / "src"))

from pitstudio_pipeline.surrogates.errors import EvaluationError  # noqa: E402
from pitstudio_pipeline.surrogates.fno import evaluate  # noqa: E402

THRESHOLD = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "models"
]["fno_rel_l2_mean_max"]
CELL = 8.0
H_THR = 0.5
T_END = 3600.0
TAILINGS_FIELDS = [f"depth_t{k}" for k in range(1, 9)] + ["depth_max"]


# ------------------------------------------------------------------ FR-011-35 relative L2


@pytest.mark.req("FR-011-35")
@pytest.mark.parametrize("n", [4, 64])
def test_relative_l2_of_a_uniform_offset_by_hand(n: int) -> None:
    truth = np.ones((n, n))
    assert evaluate.relative_l2(truth + 0.1, truth) == pytest.approx(0.1, rel=1e-12)  # 0.1 n / n
    assert evaluate.relative_l2(truth, truth) == 0.0


@pytest.mark.req("FR-011-35")
def test_relative_l2_of_a_single_cell_error_by_hand() -> None:
    truth = np.zeros((4, 4))
    truth[2, 1] = 3.0
    pred = np.zeros((4, 4))
    pred[2, 1] = 3.3
    assert evaluate.relative_l2(pred, truth) == pytest.approx(0.1, rel=1e-12)  # 0.3 / 3.0


@pytest.mark.req("FR-011-35")
def test_relative_l2_is_scale_invariant_and_symmetric_under_sign_of_the_error() -> None:
    rng = np.random.default_rng(1)
    truth = rng.uniform(0.5, 2.0, (16, 16))
    err = rng.normal(0.0, 0.05, (16, 16))
    a = evaluate.relative_l2(truth + err, truth)
    assert evaluate.relative_l2(truth - err, truth) == pytest.approx(a, rel=1e-12)
    assert evaluate.relative_l2(7.0 * (truth + err), 7.0 * truth) == pytest.approx(a, rel=1e-12)
    assert a == pytest.approx(np.linalg.norm(err) / np.linalg.norm(truth), rel=1e-12)


@pytest.mark.req("FR-011-35")
@pytest.mark.parametrize("truth_norm_case", ["zeros", "tiny"])
def test_relative_l2_of_an_empty_solver_field_is_refused(truth_norm_case: str) -> None:
    truth = np.zeros((4, 4)) if truth_norm_case == "zeros" else np.full((4, 4), 1e-11)
    with pytest.raises(EvaluationError, match=r"empty|norm"):
        evaluate.relative_l2(np.ones((4, 4)), truth)


def tailings_set(errors: list[float]) -> tuple[np.ndarray, np.ndarray]:
    """S scenarios, 9 channels of 4 x 4 ones; scenario i of channel `depth_max` is off by errors[i] (relative error
    exactly errors[i])."""
    s = len(errors)
    truth = np.ones((s, 9, 4, 4))
    pred = truth.copy()
    pred[:, 8] += np.array(errors)[:, None, None]
    return pred, truth


@pytest.mark.req("FR-011-35")
def test_per_field_mean_and_90th_percentile_over_the_held_out_scenarios_by_hand() -> None:
    errors = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.09]
    pred, truth = tailings_set(errors)
    rep = evaluate.evaluate_fno(pred, truth, TAILINGS_FIELDS, model="tailings")
    f = rep["fields"]["depth_max"]
    assert f["per_scenario"] == pytest.approx(errors, rel=1e-12)
    assert f["mean"] == pytest.approx(0.054, rel=1e-9)
    assert f["p90"] == pytest.approx(0.09, rel=1e-9)
    assert f["n_included"] == 10
    assert f["n_excluded_empty"] == 0
    assert rep["fields"]["depth_t1"]["mean"] == pytest.approx(0.0, abs=1e-12)  # untouched channel
    assert rep["n_scenarios"] == 10
    assert set(rep["fields"]) == set(TAILINGS_FIELDS)


@pytest.mark.req("FR-011-35")
def test_empty_solver_fields_are_excluded_from_the_mean_and_counted() -> None:
    pred, truth = tailings_set([0.02, 0.04, 0.06, 0.08])
    truth[:, 0] = 0.0  # h(t_1) far from the breach: the solver field is empty in every scenario
    pred[:, 0] = 0.3
    truth[1, 3] = 0.0  # and h(t_4) of one scenario
    pred[1, 3] = 0.1
    rep = evaluate.evaluate_fno(pred, truth, TAILINGS_FIELDS, model="tailings")
    t1 = rep["fields"]["depth_t1"]
    assert t1["n_excluded_empty"] == 4
    assert t1["n_included"] == 0
    assert t1["per_scenario"] == [None] * 4
    assert t1["mean"] is None
    assert t1["p90"] is None
    t4 = rep["fields"]["depth_t4"]
    assert t4["n_excluded_empty"] == 1
    assert t4["n_included"] == 3
    assert t4["per_scenario"][1] is None
    assert rep["fields"]["depth_max"]["mean"] == pytest.approx(0.05, rel=1e-9)  # unaffected


@pytest.mark.req("SC-011-03")
@pytest.mark.parametrize(
    ("errors", "verdict"),
    [
        ([0.04999] * 6, "pass"),
        ([0.0501] * 6, "fail"),
        ([0.0] * 5 + [0.3], "fail"),
        ([0.01, 0.08], "pass"),
        ([0.02, 0.2], "fail"),
    ],
    ids=["below", "above", "one-bad-mean", "mean-0.045", "mean-0.11"],
)
def test_the_tailings_verdict_uses_the_mean_relative_l2_of_h_max_against_the_threshold(
    errors: list[float], verdict: str
) -> None:
    assert THRESHOLD == 0.05
    pred, truth = tailings_set(errors)
    rep = evaluate.evaluate_fno(pred, truth, TAILINGS_FIELDS, model="tailings")
    assert rep["sc_field"] == "depth_max"
    assert rep["threshold"] == THRESHOLD
    assert rep["sc_011_03"] == verdict


@pytest.mark.req("SC-011-03")
def test_only_h_max_decides_the_verdict_not_the_other_depth_snapshots() -> None:
    pred, truth = tailings_set([0.01] * 4)
    pred[:, 3] += 0.9  # h(t_4) is badly predicted: reported, but SC-011-03 is about h_max
    rep = evaluate.evaluate_fno(pred, truth, TAILINGS_FIELDS, model="tailings")
    assert rep["fields"]["depth_t4"]["mean"] > 0.5
    assert rep["sc_011_03"] == "pass"


@pytest.mark.req("SC-011-03")
@pytest.mark.parametrize(("offset", "verdict"), [(0.04, "pass"), (0.06, "fail")])
def test_the_dust_verdict_uses_the_time_averaged_concentration(offset: float, verdict: str) -> None:
    truth = np.ones((5, 1, 4, 4))
    rep = evaluate.evaluate_fno(truth + offset, truth, ["concentration_mean"], model="dust")
    assert rep["sc_field"] == "concentration_mean"
    assert rep["fields"]["concentration_mean"]["mean"] == pytest.approx(offset, rel=1e-9)
    assert rep["sc_011_03"] == verdict


# ------------------------------------------------------------------ FR-011-35 KPIs


def kpi_truth() -> np.ndarray:
    truth = np.zeros((9, 4, 4))
    for k in range(1, 9):
        truth[k - 1, 0, 0] = 0.1 * k
        truth[k - 1, 1, 1] = 1.0 if k >= 2 else 0.0
    truth[8, 0, 0] = 0.8
    truth[8, 1, 1] = 1.0
    return truth


def kpi_args(checkpoints) -> dict:
    return {"cell_size_m": CELL, "h_thr_m": H_THR, "checkpoints": checkpoints, "t_end_s": T_END}


@pytest.mark.req("FR-011-35")
def test_inundated_area_and_maximum_depth_errors_by_hand() -> None:
    truth = kpi_truth()
    pred = truth.copy()
    pred[8, 3, 3] = 0.6  # a third inundated cell in h_max
    pred[8, 1, 1] = 1.2
    out = evaluate.tailings_kpi_errors(pred, truth, **kpi_args([(1, 1), (0, 0)]))
    assert out["area_m2"]["truth"] == pytest.approx(128.0)  # 2 cells x 64 m^2
    assert out["area_m2"]["pred"] == pytest.approx(192.0)
    assert out["area_m2"]["abs_error"] == pytest.approx(64.0)
    assert out["area_m2"]["rel_error"] == pytest.approx(0.5)
    assert out["max_depth_m"]["truth"] == pytest.approx(1.0)
    assert out["max_depth_m"]["pred"] == pytest.approx(1.2)
    assert out["max_depth_m"]["abs_error"] == pytest.approx(0.2)
    assert out["max_depth_m"]["rel_error"] == pytest.approx(0.2)


@pytest.mark.req("FR-011-35")
def test_arrival_times_at_the_checkpoint_cells_by_hand() -> None:
    truth = kpi_truth()
    pred = truth.copy()
    pred[1, 1, 1] = 0.0  # (1, 1) wet at k = 2 in the truth, only from k = 3 in the prediction
    out = evaluate.tailings_kpi_errors(pred, truth, **kpi_args([(1, 1), (0, 0)]))
    a11, a00 = out["arrival_time_s"]
    assert a11["checkpoint"] == (1, 1) or list(a11["checkpoint"]) == [1, 1]
    assert a11["truth"] == pytest.approx(900.0)  # k = 2 at 450 s per snapshot
    assert a11["pred"] == pytest.approx(1350.0)  # k = 3
    assert a11["abs_error"] == pytest.approx(450.0)
    assert a00["truth"] == pytest.approx(2250.0)  # 0.1 k >= 0.5 first at k = 5
    assert a00["pred"] == pytest.approx(2250.0)
    assert a00["abs_error"] == pytest.approx(0.0)


@pytest.mark.req("FR-011-35")
def test_an_arrival_that_never_happens_in_the_prediction_is_none_without_an_error_value() -> None:
    truth = kpi_truth()
    pred = truth.copy()
    pred[:, 1, 1] = 0.0
    out = evaluate.tailings_kpi_errors(pred, truth, **kpi_args([(1, 1)]))
    a = out["arrival_time_s"][0]
    assert a["truth"] == pytest.approx(900.0)
    assert a["pred"] is None
    assert a["abs_error"] is None


@pytest.mark.req("FR-011-35")
def test_the_volume_error_of_every_snapshot_by_hand() -> None:
    truth = kpi_truth()
    out = evaluate.tailings_kpi_errors(truth * 1.05, truth, **kpi_args([(1, 1)]))
    assert out["volume_rel_error"] == pytest.approx(
        [0.05] * 8, rel=1e-9
    )  # (V_hat - V) / V with V(t_1) = 6.4, V(t_2) = 76.8 m^3
    pred = truth.copy()
    pred[1, 1, 1] = 0.0  # h(t_2): volume 0.2 x 64 = 12.8 instead of 76.8
    out2 = evaluate.tailings_kpi_errors(pred, truth, **kpi_args([(1, 1)]))
    assert out2["volume_rel_error"][1] == pytest.approx(abs(12.8 - 76.8) / 76.8)
    assert out2["volume_rel_error"][0] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.req("FR-011-35")
def test_the_receptor_concentration_error_by_hand() -> None:
    truth = np.zeros((1, 4, 4))
    truth[0, 2, 3] = 10.0
    truth[0, 0, 1] = 4.0
    pred = truth.copy()
    pred[0, 2, 3] = 11.0
    pred[0, 0, 1] = 3.0
    out = evaluate.dust_kpi_errors(pred, truth, receptors=[(2, 3), (0, 1)])
    r1, r2 = out["receptors"]
    assert (r1["truth"], r1["pred"]) == (10.0, 11.0)
    assert r1["abs_error"] == pytest.approx(1.0)
    assert r1["rel_error"] == pytest.approx(0.1)
    assert (r2["truth"], r2["pred"]) == (4.0, 3.0)
    assert r2["abs_error"] == pytest.approx(1.0)
    assert r2["rel_error"] == pytest.approx(0.25)


# ------------------------------------------------------------------ FR-011-42 resolution transfer


@pytest.mark.req("FR-011-42")
def test_resolution_transfer_is_evaluated_at_128_and_labelled_not_claimed() -> None:
    rng = np.random.default_rng(2)
    truths = rng.uniform(1.0, 2.0, (3, 2, 128, 128))
    inputs = rng.normal(size=(3, 5, 128, 128))
    seen = []

    def predict(x):
        seen.append(x.shape)
        return truths * 1.1  # relative error exactly 0.1

    out = evaluate.evaluate_resolution_transfer(predict, inputs, truths, ["depth_t1", "depth_max"])
    assert seen == [(3, 5, 128, 128)]
    assert out["label"] == "resolution transfer — not claimed"
    assert out["fields"]["depth_max"]["mean"] == pytest.approx(0.1, rel=1e-9)
    assert "sc_011_03" not in out


@pytest.mark.req("FR-011-42")
@pytest.mark.parametrize("side", [64, 96, 127])
def test_resolution_transfer_needs_128_by_128_solver_fields(side: int) -> None:
    truths = np.ones((2, 1, side, side))
    with pytest.raises(EvaluationError, match="128"):
        evaluate.evaluate_resolution_transfer(lambda x: x, np.ones((2, 5, side, side)), truths, ["depth_max"])


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-35")
@pytest.mark.parametrize(
    "case",
    ["shape-mismatch", "nan-pred", "inf-truth", "no-scenarios", "wrong-field-count", "unknown-model", "ranks"],
)
def test_hostile_inputs_are_refused(case: str) -> None:
    pred, truth = tailings_set([0.01, 0.02])
    names = TAILINGS_FIELDS
    model = "tailings"
    if case == "shape-mismatch":
        pred = pred[:, :, :, :3]
    elif case == "nan-pred":
        pred = pred.copy()
        pred[0, 2, 1, 1] = np.nan
    elif case == "inf-truth":
        truth = truth.copy()
        truth[1, 0, 0, 0] = np.inf
    elif case == "no-scenarios":
        pred, truth = pred[:0], truth[:0]
    elif case == "wrong-field-count":
        names = TAILINGS_FIELDS[:5]
    elif case == "unknown-model":
        model = "snow"
    elif case == "ranks":
        pred, truth = pred[0], truth[0]
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.evaluate_fno(pred, truth, names, model=model)


@pytest.mark.req("FR-011-35")
def test_kpi_functions_refuse_bad_geometry_and_checkpoints() -> None:
    truth = kpi_truth()
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.tailings_kpi_errors(truth, truth, **kpi_args([(4, 0)]))  # checkpoint outside the 4 x 4 grid
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.tailings_kpi_errors(truth, truth, **kpi_args([(-1, 0)]))
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.tailings_kpi_errors(truth, truth, cell_size_m=0.0, h_thr_m=H_THR, checkpoints=[(0, 0)], t_end_s=T_END)
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.tailings_kpi_errors(
            truth, truth, cell_size_m=CELL, h_thr_m=float("nan"), checkpoints=[(0, 0)], t_end_s=T_END
        )
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.tailings_kpi_errors(truth[:5], truth[:5], **kpi_args([(0, 0)]))  # not 9 channels
    with pytest.raises((EvaluationError, ValueError)):
        evaluate.dust_kpi_errors(truth[:1], truth[:1], receptors=[(9, 9)])
