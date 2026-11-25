"""T-012-017 - FR-012-29, FR-012-30, FR-012-45, P-012-06: foreground IoU, per-fold ratios, hostile metric inputs.

Oracles (independent of the code under test):
- hand calculation: 4 x 4 masks with |P| = |G| = 4 and |P n G| = 3 give IoU 3 / (4 + 4 - 3) = 3/5; both empty 1.0;
  disjoint 0.0 (plan 012 test strategy FR-012-29);
- hand calculation of five fold ratios: IoU_TSTR = (0.72, 0.81, 0.76, 0.90, 0.85), IoU_TRTR = (0.80, 0.90, 0.80,
  0.90, 0.85) give rho = (0.90, 0.90, 0.95, 1.00, 1.00), mean 0.95, minimum 0.90, deviations (-0.05, -0.05, 0,
  0.05, 0.05): population standard deviation sqrt(0.01 / 5) = 0.0447213595..., sample sqrt(0.01 / 4) = 0.05
  (plan 012 test strategy FR-012-30: 0.72 / 0.80 = 0.90);
- hand calculation: relative x50 error |11 - 10| / 10 = 0.10 (FR-012-31 definition, used here only to reach the
  FR-012-45 guards);
- a counting formula written in this file (sum of AND over sum of OR) for the IoU property P-012-06.
Tolerances: exact for IoU (P-012-06, ratios of small integers); rtol 1e-12 for the fold statistics (a few float64
divisions).

Expected public API (module `pitstudio_pipeline.fragmentation.metrics`, package under `pipeline/src/`):

    foreground_iou(pred: np.ndarray, truth: np.ndarray) -> float
        |pred & truth| / |pred | truth| over two boolean (H, W) masks; 1.0 when both are empty. Raises ValueError
        naming the argument ("pred" / "truth") if the shapes differ or a mask is not of boolean dtype.
    fold_score(preds: Sequence[np.ndarray], truths: Sequence[np.ndarray]) -> float
        Mean of foreground_iou over the fold's test originals.
    tstr_trtr_ratios(iou_tstr: Sequence[float], iou_trtr: Sequence[float]) -> dict
        {"rho": [rho_f for f = 0..4], "mean": mean rho, "min": min rho, "std": standard deviation of rho}.
    relative_x50_error(x50_hat: float, x50_ref: float) -> float
        |x50_hat - x50_ref| / x50_ref; raises ValueError naming "x50_ref" if it is non-finite or <= 0.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.fragmentation import metrics  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]


def _dihedral(a: np.ndarray) -> list[np.ndarray]:
    return [np.rot90(a, k) for k in range(4)] + [np.rot90(np.fliplr(a), k) for k in range(4)]


def _count_iou(p: np.ndarray, g: np.ndarray) -> float:
    union = int(np.logical_or(p, g).sum())
    return 1.0 if union == 0 else int(np.logical_and(p, g).sum()) / union


# ---------------------------------------------------------------- FR-012-29 foreground IoU


@pytest.mark.req("FR-012-29")
def test_hand_calculated_4x4_iou_is_three_fifths() -> None:
    pred = np.zeros((4, 4), dtype=bool)
    truth = np.zeros((4, 4), dtype=bool)
    pred[0, 0:4] = True  # 4 px
    truth[0, 1:4] = True  # 3 px shared with pred
    truth[1, 0] = True  # 1 px only in truth
    assert metrics.foreground_iou(pred, truth) == 3 / 5


@pytest.mark.req("FR-012-29")
def test_both_empty_is_one_and_disjoint_or_one_sided_is_zero() -> None:
    empty = np.zeros((8, 8), dtype=bool)
    some = empty.copy()
    some[2:4, 2:4] = True
    other = empty.copy()
    other[5:7, 5:7] = True
    assert metrics.foreground_iou(empty, empty) == 1.0
    assert metrics.foreground_iou(some, other) == 0.0
    assert metrics.foreground_iou(some, empty) == 0.0
    assert metrics.foreground_iou(empty, some) == 0.0
    assert metrics.foreground_iou(some, some) == 1.0


@pytest.mark.req("FR-012-29")
def test_iou_on_a_full_512_tile() -> None:
    pred = np.zeros((512, 512), dtype=bool)
    truth = np.zeros((512, 512), dtype=bool)
    pred[:256, :] = True  # 131,072 px
    truth[128:384, :] = True  # 131,072 px, overlap rows 128-255 = 65,536 px
    assert metrics.foreground_iou(pred, truth) == 65536 / (131072 + 131072 - 65536)


@pytest.mark.req("FR-012-29")
def test_fold_score_is_the_mean_over_the_test_originals() -> None:
    a = np.zeros((4, 4), dtype=bool)
    b = a.copy()
    a[0, 0:4] = True
    b[0, 1:4] = True
    b[1, 0] = True
    empty = np.zeros((4, 4), dtype=bool)
    far = np.zeros((4, 4), dtype=bool)
    far[3, 3] = True
    preds = [empty, a, far]
    truths = [empty, b, a]
    assert metrics.fold_score(preds, truths) == pytest.approx((1.0 + 3 / 5 + 0.0) / 3, rel=1e-12)


# ---------------------------------------------------------------- FR-012-30 per-fold ratios

TSTR = [0.72, 0.81, 0.76, 0.90, 0.85]
TRTR = [0.80, 0.90, 0.80, 0.90, 0.85]


@pytest.mark.req("FR-012-30")
def test_per_fold_ratio_mean_minimum_and_spread() -> None:
    out = metrics.tstr_trtr_ratios(TSTR, TRTR)
    assert len(out["rho"]) == 5
    for got, exp in zip(out["rho"], [0.90, 0.90, 0.95, 1.00, 1.00], strict=True):
        assert got == pytest.approx(exp, rel=1e-12)
    assert out["mean"] == pytest.approx(0.95, rel=1e-12)
    assert out["min"] == pytest.approx(0.90, rel=1e-12)
    # FR-012-30 does not say population or sample standard deviation; both hand values are accepted.
    population, sample = math.sqrt(0.01 / 5), math.sqrt(0.01 / 4)
    assert out["std"] == pytest.approx(population, rel=1e-9) or out["std"] == pytest.approx(sample, rel=1e-9)


@pytest.mark.req("FR-012-30")
def test_single_fold_ratio_from_the_plan() -> None:
    out = metrics.tstr_trtr_ratios([0.72, 0.5, 0.5, 0.5, 0.5], [0.80, 0.5, 0.5, 0.5, 0.5])
    assert out["rho"][0] == pytest.approx(0.90, rel=1e-12)
    assert out["min"] == pytest.approx(0.90, rel=1e-12)


@pytest.mark.req("FR-012-30")
def test_identical_arms_give_ratio_one_and_zero_spread() -> None:
    out = metrics.tstr_trtr_ratios(TRTR, TRTR)
    assert list(out["rho"]) == [1.0] * 5
    assert out["mean"] == 1.0
    assert out["min"] == 1.0
    assert out["std"] == 0.0


# ---------------------------------------------------------------- FR-012-45 hostile metric inputs


@pytest.mark.req("FR-012-45")
@pytest.mark.parametrize(
    ("pred_shape", "truth_shape"),
    [((512, 512), (511, 511)), ((512, 512), (512, 511)), ((4, 4), (16,)), ((4, 4), (4, 4, 1))],
)
def test_masks_of_different_shapes_are_rejected(pred_shape, truth_shape) -> None:
    with pytest.raises(ValueError, match=r"pred|truth"):
        metrics.foreground_iou(np.zeros(pred_shape, dtype=bool), np.zeros(truth_shape, dtype=bool))


@pytest.mark.req("FR-012-45")
@pytest.mark.parametrize("dtype", [np.uint8, np.int64, np.float32, np.float64, np.uint16])
@pytest.mark.parametrize("which", ["pred", "truth"])
def test_a_non_boolean_foreground_is_rejected_naming_the_argument(dtype, which: str) -> None:
    good = np.zeros((8, 8), dtype=bool)
    bad = np.zeros((8, 8), dtype=dtype)
    bad[1, 1] = 1
    args = (bad, good) if which == "pred" else (good, bad)
    with pytest.raises(ValueError, match=which):
        metrics.foreground_iou(*args)


@pytest.mark.req("FR-012-45")
def test_fold_score_rejects_a_bad_tile() -> None:
    good = np.zeros((8, 8), dtype=bool)
    with pytest.raises(ValueError, match="truth"):
        metrics.fold_score([good, good], [good, np.zeros((8, 8), dtype=np.uint8)])


@pytest.mark.req("FR-012-45")
def test_relative_x50_error_of_the_hand_example() -> None:
    assert metrics.relative_x50_error(11.0, 10.0) == pytest.approx(0.10, rel=1e-12)
    assert metrics.relative_x50_error(9.0, 10.0) == pytest.approx(0.10, rel=1e-12)


@pytest.mark.req("FR-012-45")
@pytest.mark.parametrize("ref", [0.0, -1.0, -0.0, math.nan, math.inf, -math.inf])
def test_a_non_finite_or_non_positive_reference_x50_is_rejected(ref: float) -> None:
    with pytest.raises(ValueError, match="x50_ref"):
        metrics.relative_x50_error(11.0, ref)


# ---------------------------------------------------------------- P-012-06 IoU invariants


def _mask_pairs():
    return st.integers(1, 64).flatmap(
        lambda h: st.integers(1, 64).flatmap(
            lambda w: st.tuples(hnp.arrays(np.bool_, (h, w)), hnp.arrays(np.bool_, (h, w)))
        )
    )


@pytest.mark.req("P-012-06")
@pytest.mark.req("FR-012-29")
@settings(max_examples=EXAMPLES, deadline=None)
@given(pair=_mask_pairs())
def test_iou_is_symmetric_bounded_and_one_on_identity(pair) -> None:
    p, g = pair
    v = metrics.foreground_iou(p, g)
    assert v == pytest.approx(_count_iou(p, g), rel=1e-15, abs=0)
    assert v == metrics.foreground_iou(g, p)
    assert 0.0 <= v <= 1.0
    assert metrics.foreground_iou(p, p.copy()) == 1.0


@pytest.mark.req("P-012-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(pair=_mask_pairs())
def test_iou_is_invariant_under_the_dihedral_maps(pair) -> None:
    p, g = pair
    v = metrics.foreground_iou(p, g)
    for pt, gt in zip(_dihedral(p), _dihedral(g), strict=True):
        assert metrics.foreground_iou(np.ascontiguousarray(pt), np.ascontiguousarray(gt)) == v


@pytest.mark.req("P-012-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    labels=st.integers(1, 48).flatmap(
        lambda n: st.tuples(
            hnp.arrays(np.uint16, (n, n), elements=st.integers(0, 6)),
            hnp.arrays(np.uint16, (n, n), elements=st.integers(0, 6)),
        )
    ),
    perm=st.permutations([1, 2, 3, 4, 5, 6]),
)
def test_iou_of_label_masks_is_invariant_under_instance_relabelling(labels, perm) -> None:
    a, b = labels
    lut = np.array([0, *perm], dtype=np.uint16)
    v = metrics.foreground_iou(a > 0, b > 0)
    assert metrics.foreground_iou(lut[a] > 0, lut[b] > 0) == v
    assert v == pytest.approx(_count_iou(a > 0, b > 0), rel=1e-15, abs=0)
