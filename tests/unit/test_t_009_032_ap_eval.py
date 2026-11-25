# ruff: noqa: E501
"""T-009-032 (unit half) - FR-009-22, FR-009-23: box and mask AP with cluster-bootstrap intervals.

Oracles (independent of the code under test):
- hand calculation of the COCO protocol (101-point interpolated precision, maxDets 100, area "all", IoU 0.50:0.05:0.95), each value
  also confirmed against `pycocotools` while writing this file (tolerance 1e-9):
    * one ground truth, one true positive (IoU 1) and one false positive: the TP ranked first gives AP50 = AP50:95 = 1.0; ranked
      second gives precision 1/2 at recall 1, so every one of the 101 interpolated points is 0.5 -> 0.5;
    * two ground truths in two images, detections ranked TP (r .5, p 1), FP (r .5, p 1/2), TP (r 1, p 2/3): the interpolated
      precision is 1 for the 51 recall points 0.00 .. 0.50 and 2/3 for the 50 points 0.51 .. 1.00 -> AP = (51 + 50 * 2/3) / 101 = 253/303;
    * a box of IoU exactly 0.5 matches at the 0.50 threshold only (IoU >= t, pycocotools) -> AP50 = 1.0, AP50:95 = 1/10 = 0.1; a box
      of IoU 81/100 = 0.81 matches the 7 thresholds 0.50 .. 0.80 -> AP50:95 = 0.7 (0.85 > 0.81; no threshold sits within 0.01 of 0.81);
    * 120 detections in one image: only the 100 best are scored (maxDets 100): the TP ranked 100th gives precision 1/100 -> AP50 = 0.01,
      ranked 101st it is dropped -> 0.0;
    * 8 x 8 masks: ground truth a 6 x 6 polygon (36 px), detection 6 x 5 = 30 px inside it -> IoU 30/36 = 0.8333 -> (1.0, 0.7); ground
      truth 4 x 4 (16 px), detection 4 x 2 = 8 px -> IoU 0.5 -> (1.0, 0.1);
- the unweighted mean over the classes with >= `min_support` instances (spec 009 FR-009-22, default 100): 100 instances qualify, 99 do not;
- reference implementation `pycocotools` COCOeval called directly in `_p009_ap_kit.ref_eval` on seeded random fixtures (boxes and RLE masks);
- cluster bootstrap (percentile, seeded): with 2 test scenario seeds of 5 images each, one all-detected and one all-missed, the resampled
  statistic is 1 (both clusters perfect), 0.505 (51/101: one of each) or 0 with probabilities 1/4, 1/2, 1/4, so the 95 % percentile
  interval is exactly [0, 1]; an image-level bootstrap would give a lower bound above 0 (P(all 10 images missed) = 1/1024 < 2.5 %),
  so the case proves the CLUSTER resampling; identical perfect clusters give the degenerate interval [1, 1]; a higher level can only widen
  the interval for the same seed (same resamples); determinism for a fixed seed.

Expected public API (module `pitstudio_pipeline.perception.evaluate`, package under `pipeline/src/`; `pycocotools` is used inside):

    ClassMetrics                     frozen dataclass: support: int (ground-truth instances of the class), ap50: float | None,
                                     ap50_95: float | None (None when support == 0)
    BoxEval / MaskEval               frozen dataclasses with per_class: dict[int, ClassMetrics] (a key for every category id of the ground
                                     truth document), map50: float | None, map50_95: float | None (unweighted means over the classes whose
                                     support >= min_support; None when none qualifies), classes_included: tuple[int, ...] (ascending);
                                     MaskEval also `descriptive: bool`
    evaluate_boxes(gt: Mapping, detections: Sequence[Mapping], *, min_support: int = 100) -> BoxEval
        gt is a COCO document (images, annotations, categories); detections are {"image_id", "category_id", "bbox": [x, y, w, h],
        "score"}. COCO protocol as above via pycocotools (iouType "bbox"). An empty detection list is allowed: every class with support has
        AP 0.0. No image-bounds check here (validate_predictions of T-009-033 does the input checks). Inputs are not modified.
        ValueError (message names the argument) for min_support < 1 or a non-int.
    evaluate_masks(gt: Mapping, detections: Sequence[Mapping], *, family: str, min_support: int = 100) -> MaskEval
        as above with iouType "segm": each detection carries "segmentation" as a binary numpy array (H, W) (bool or uint8) or an RLE dict;
        ground-truth segmentation are COCO polygons. `descriptive` is False for family "pit" and True for "crusher" (crusher mask metrics are
        outside the acceptance, FR-009-23); ValueError (message contains "family") for any other family and ValueError (message contains
        "segmentation") for a detection without one.
    BootstrapResult                  frozen dataclass: map50: tuple[float, float], per_class: dict[int, dict[str, tuple[float, float]]]
                                     (keys "ap50", "ap50_95"; classes with support >= 1 only)
    bootstrap_intervals(gt: Mapping, detections: Sequence[Mapping], image_cluster: Mapping[int, int], *, resamples: int = 2000,
                        level: float = 0.95, seed: int, min_support: int = 100, iou_type: str = "bbox") -> BootstrapResult
        Cluster bootstrap: `image_cluster` maps every image id to its test scenario seed; each of `resamples` draws samples the cluster set with
        replacement (numpy default_rng(seed)), pools the images of the drawn clusters (an image of a cluster drawn twice counts twice), evaluates
        the COCO protocol and records mAP50 over the classes included in the POINT estimate (fixed set) and every class's AP50 / AP50:95; the
        interval is the percentile interval [(1 - level) / 2, (1 + level) / 2] of those values. Deterministic for a given seed.
        ValueError (message names the argument) for resamples < 1, level outside (0, 1), an image id missing from image_cluster, or a non-int seed.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_ap_kit as kit  # noqa: E402
from pitstudio_pipeline.perception import evaluate as ev  # noqa: E402

TOL = 1e-9


def _one(gt_box=(10, 10, 20, 20), cat: int = 1) -> dict:
    return kit.gt_doc([kit.image(1)], [kit.annotation(1, 1, cat, gt_box)])


def _ap(gt: dict, dets: list, cat: int = 1, **kw) -> tuple[float, float]:
    res = ev.evaluate_boxes(gt, dets, min_support=kw.pop("min_support", 1))
    m = res.per_class[cat]
    return m.ap50, m.ap50_95


TP = lambda s: kit.detection(1, 1, (10, 10, 20, 20), s)  # noqa: E731 - exact box of the ground truth
FP = lambda s: kit.detection(1, 1, (60, 60, 20, 20), s)  # noqa: E731 - far from it


# ---------------------------------------------------------------- FR-009-22: hand calculations


@pytest.mark.req("FR-009-22")
def test_a_true_positive_ranked_before_a_false_positive_gives_ap_one() -> None:
    a50, a = _ap(_one(), [TP(0.9), FP(0.8)])
    assert a50 == pytest.approx(1.0, abs=TOL)
    assert a == pytest.approx(1.0, abs=TOL)


@pytest.mark.req("FR-009-22")
def test_a_true_positive_ranked_after_a_false_positive_gives_ap_one_half() -> None:
    a50, a = _ap(_one(), [FP(0.9), TP(0.8)])
    assert a50 == pytest.approx(0.5, abs=TOL)
    assert a == pytest.approx(0.5, abs=TOL)


@pytest.mark.req("FR-009-22")
def test_two_ground_truths_with_a_false_positive_in_between_give_253_over_303() -> None:
    gt = kit.gt_doc(
        [kit.image(1), kit.image(2)],
        [kit.annotation(1, 1, 1, (10, 10, 20, 20)), kit.annotation(2, 2, 1, (10, 10, 20, 20))],
    )
    dets = [
        kit.detection(1, 1, (10, 10, 20, 20), 0.9),
        kit.detection(1, 1, (60, 60, 20, 20), 0.8),
        kit.detection(2, 1, (10, 10, 20, 20), 0.7),
    ]
    a50, a = _ap(gt, dets)
    assert a50 == pytest.approx(253 / 303, abs=TOL)
    assert a == pytest.approx(253 / 303, abs=TOL)  # both detections match at every threshold: same value


@pytest.mark.req("FR-009-22")
def test_the_input_order_of_the_detections_does_not_matter() -> None:
    gt = kit.gt_doc(
        [kit.image(1), kit.image(2)],
        [kit.annotation(1, 1, 1, (10, 10, 20, 20)), kit.annotation(2, 2, 1, (10, 10, 20, 20))],
    )
    dets = [
        kit.detection(1, 1, (10, 10, 20, 20), 0.9),
        kit.detection(1, 1, (60, 60, 20, 20), 0.8),
        kit.detection(2, 1, (10, 10, 20, 20), 0.7),
    ]
    assert _ap(gt, list(reversed(dets)))[0] == pytest.approx(253 / 303, abs=TOL)


@pytest.mark.req("FR-009-22")
def test_a_box_of_iou_exactly_one_half_matches_only_the_first_threshold() -> None:
    gt = _one((0, 0, 10, 10))
    a50, a = _ap(gt, [kit.detection(1, 1, (0, 0, 10, 5), 0.9)])
    assert a50 == pytest.approx(1.0, abs=TOL)
    assert a == pytest.approx(0.1, abs=TOL)  # 1 threshold of 10


@pytest.mark.req("FR-009-22")
def test_a_box_of_iou_0_81_matches_seven_of_ten_thresholds() -> None:
    gt = _one((0, 0, 10, 10))
    a50, a = _ap(gt, [kit.detection(1, 1, (0, 0, 9, 9), 0.9)])
    assert a50 == pytest.approx(1.0, abs=TOL)
    assert a == pytest.approx(0.7, abs=TOL)  # thresholds 0.50 .. 0.80


@pytest.mark.req("FR-009-22")
@pytest.mark.parametrize(("rank", "expected"), [(100, 0.01), (101, 0.0)])
def test_only_the_hundred_best_detections_of_an_image_are_scored(rank: int, expected: float) -> None:
    gt = _one()
    dets = [
        kit.detection(1, 1, (60 + (i % 5), 60 + (i // 5) % 5, 5, 5), 0.99 - 0.001 * i) for i in range(120)
    ]  # all false positives
    dets[rank - 1] = kit.detection(1, 1, (10, 10, 20, 20), 0.99 - 0.001 * (rank - 1))  # the true positive at its rank
    assert _ap(gt, dets)[0] == pytest.approx(expected, abs=TOL)


@pytest.mark.req("FR-009-22")
def test_no_detections_gives_ap_zero_for_every_class_with_ground_truth() -> None:
    gt = kit.gt_doc(
        [kit.image(1)], [kit.annotation(1, 1, 1, (10, 10, 20, 20)), kit.annotation(2, 1, 4, (50, 50, 5, 5))]
    )
    res = ev.evaluate_boxes(gt, [], min_support=1)
    assert res.per_class[1] == ev.ClassMetrics(support=1, ap50=0.0, ap50_95=0.0)
    assert res.per_class[4] == ev.ClassMetrics(support=1, ap50=0.0, ap50_95=0.0)
    assert res.per_class[2] == ev.ClassMetrics(support=0, ap50=None, ap50_95=None)
    assert res.map50 == 0.0
    assert res.classes_included == (1, 4)


@pytest.mark.req("FR-009-22")
def test_a_class_without_ground_truth_has_no_ap_and_does_not_enter_the_mean() -> None:
    gt = _one()
    dets = [TP(0.9), kit.detection(1, 3, (5, 5, 10, 10), 0.8)]  # a class-3 detection with no class-3 ground truth
    res = ev.evaluate_boxes(gt, dets, min_support=1)
    assert res.per_class[3] == ev.ClassMetrics(support=0, ap50=None, ap50_95=None)
    assert res.classes_included == (1,)
    assert res.map50 == pytest.approx(1.0, abs=TOL)
    assert res.map50_95 == pytest.approx(1.0, abs=TOL)
    assert set(res.per_class) == {1, 2, 3, 4, 5}


@pytest.mark.req("FR-009-22")
def test_the_map_is_the_unweighted_mean_over_classes_with_at_least_100_instances() -> None:
    images = [kit.image(i) for i in range(1, 101)]
    anns = [
        kit.annotation(i, i, 1, (10, 10, 20, 20)) for i in range(1, 100 + 1)
    ]  # class 1: 100 instances, all detected
    anns += [
        kit.annotation(100 + i, i, 2, (50, 50, 10, 10)) for i in range(1, 100)
    ]  # class 2: 99 instances, none detected
    dets = [kit.detection(i, 1, (10, 10, 20, 20), 0.5 + i / 1000) for i in range(1, 101)]
    res = ev.evaluate_boxes(kit.gt_doc(images, anns), dets)  # default min_support = 100
    assert res.per_class[1].support == 100
    assert res.per_class[2].support == 99
    assert res.per_class[1].ap50 == pytest.approx(1.0, abs=TOL)
    assert res.per_class[2].ap50 == pytest.approx(0.0, abs=TOL)  # still reported per class
    assert res.classes_included == (1,)
    assert res.map50 == pytest.approx(1.0, abs=TOL)
    low = ev.evaluate_boxes(kit.gt_doc(images, anns), dets, min_support=99)
    assert low.classes_included == (1, 2)
    assert low.map50 == pytest.approx(0.5, abs=TOL)


@pytest.mark.req("FR-009-22")
def test_when_no_class_has_enough_instances_the_map_is_none() -> None:
    res = ev.evaluate_boxes(_one(), [TP(0.9)])
    assert res.map50 is None
    assert res.map50_95 is None
    assert res.classes_included == ()
    assert res.per_class[1].ap50 == pytest.approx(1.0, abs=TOL)


@pytest.mark.req("FR-009-22")
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6])
def test_boxes_equal_the_pycocotools_reference_on_random_fixtures(seed: int) -> None:
    gt, dets = kit.random_fixture(seed, n_images=12, max_boxes=8)
    ref = kit.ref_eval(gt, dets, "bbox")
    got = ev.evaluate_boxes(gt, dets, min_support=1)
    for cid, (r50, r) in ref.items():
        assert got.per_class[cid].ap50 == (pytest.approx(r50, abs=TOL) if r50 is not None else None)
        assert got.per_class[cid].ap50_95 == (pytest.approx(r, abs=TOL) if r is not None else None)
    present = [v for v in ref.values() if v[0] is not None]
    assert got.map50 == pytest.approx(sum(v[0] for v in present) / len(present), abs=TOL)
    assert got.map50_95 == pytest.approx(sum(v[1] for v in present) / len(present), abs=TOL)
    assert got.classes_included == tuple(sorted(c for c, v in ref.items() if v[0] is not None))


@pytest.mark.req("FR-009-22")
def test_the_inputs_are_not_modified() -> None:
    gt, dets = kit.random_fixture(9, n_images=6, max_boxes=5)
    gt0, dets0 = copy.deepcopy(gt), copy.deepcopy(dets)
    ev.evaluate_boxes(gt, dets, min_support=1)
    assert gt == gt0
    assert dets == dets0


@pytest.mark.req("FR-009-22")
@pytest.mark.parametrize("bad", [0, -1, 1.5, "100", None, True])
def test_a_bad_min_support_is_rejected(bad: object) -> None:
    with pytest.raises(ValueError, match="min_support"):
        ev.evaluate_boxes(_one(), [TP(0.9)], min_support=bad)  # type: ignore[arg-type]


# ---------------------------------------------------------------- FR-009-23: masks


def _mask(rows: slice, cols: slice, size: int = 8) -> np.ndarray:
    m = np.zeros((size, size), dtype=np.uint8)
    m[rows, cols] = 1
    return m


def _mask_gt(x: int, y: int, w: int, h: int) -> dict:
    return kit.gt_doc([kit.image(1, 8, 8)], [kit.annotation(1, 1, 5, (x, y, w, h))])


def _mdet(mask: object, score: float = 0.9) -> dict:
    return {"image_id": 1, "category_id": 5, "segmentation": mask, "score": score}


@pytest.mark.req("FR-009-23")
def test_a_30_pixel_mask_inside_a_36_pixel_polygon_matches_seven_thresholds() -> None:
    res = ev.evaluate_masks(_mask_gt(0, 0, 6, 6), [_mdet(_mask(slice(0, 6), slice(0, 5)))], family="pit", min_support=1)
    assert res.per_class[5].ap50 == pytest.approx(1.0, abs=TOL)
    assert res.per_class[5].ap50_95 == pytest.approx(0.7, abs=TOL)
    assert res.map50 == pytest.approx(1.0, abs=TOL)
    assert res.descriptive is False


@pytest.mark.req("FR-009-23")
def test_a_mask_of_iou_exactly_one_half_matches_the_first_threshold_only() -> None:
    res = ev.evaluate_masks(_mask_gt(0, 0, 4, 4), [_mdet(_mask(slice(0, 4), slice(0, 2)))], family="pit", min_support=1)
    assert res.per_class[5].ap50 == pytest.approx(1.0, abs=TOL)
    assert res.per_class[5].ap50_95 == pytest.approx(0.1, abs=TOL)


@pytest.mark.req("FR-009-23")
def test_a_disjoint_mask_scores_zero_and_boolean_arrays_and_rle_dicts_are_equivalent() -> None:
    gt = _mask_gt(0, 0, 4, 4)
    far = _mask(slice(5, 8), slice(5, 8))
    assert ev.evaluate_masks(gt, [_mdet(far)], family="pit", min_support=1).per_class[5].ap50 == 0.0
    arr = _mask(slice(0, 4), slice(0, 4))
    a = ev.evaluate_masks(gt, [_mdet(arr.astype(bool))], family="pit", min_support=1)
    b = ev.evaluate_masks(gt, [_mdet(arr)], family="pit", min_support=1)
    c = ev.evaluate_masks(gt, [_mdet(kit.rle_of(arr))], family="pit", min_support=1)
    assert a == b == c
    assert a.per_class[5].ap50_95 == pytest.approx(1.0, abs=TOL)


@pytest.mark.req("FR-009-23")
def test_crusher_family_mask_metrics_are_descriptive_and_other_families_are_refused() -> None:
    gt = _mask_gt(0, 0, 4, 4)
    d = [_mdet(_mask(slice(0, 4), slice(0, 4)))]
    assert ev.evaluate_masks(gt, d, family="crusher", min_support=1).descriptive is True
    for bad in ("", "Pit", "pooled", None):
        with pytest.raises(ValueError, match="family"):
            ev.evaluate_masks(gt, d, family=bad, min_support=1)  # type: ignore[arg-type]


@pytest.mark.req("FR-009-23")
def test_a_detection_without_a_segmentation_is_refused() -> None:
    with pytest.raises(ValueError, match="segmentation"):
        ev.evaluate_masks(
            _mask_gt(0, 0, 4, 4),
            [{"image_id": 1, "category_id": 5, "score": 0.9, "bbox": [0, 0, 4, 4]}],
            family="pit",
            min_support=1,
        )


@pytest.mark.req("FR-009-23")
@pytest.mark.parametrize("seed", [11, 12, 13, 14])
def test_masks_equal_the_pycocotools_reference_on_random_fixtures(seed: int) -> None:
    rng = np.random.default_rng(seed)
    size, images, anns, dets = 64, [], [], []
    for i in range(1, 9):
        images.append(kit.image(i, size, size))
        for j in range(int(rng.integers(0, 4))):
            x, y = (int(v) for v in rng.integers(0, 40, size=2))
            w, h = (int(v) for v in rng.integers(6, 20, size=2))
            c = int(rng.integers(1, 6))
            anns.append(kit.annotation(100 * i + j, i, c, (x, y, w, h)))
            if rng.random() < 0.8:
                m = np.zeros((size, size), dtype=np.uint8)
                dx, dy, dw, dh = (int(v) for v in rng.integers(-2, 3, size=4))
                m[max(0, y + dy) : y + h + dh, max(0, x + dx) : x + w + dw] = 1
                if m.any():
                    dets.append({"image_id": i, "category_id": c, "segmentation": m, "score": 0.0})
    scores = (rng.permutation(len(dets)) + 1.0) / (len(dets) + 1.0)
    for d, s in zip(dets, scores, strict=True):
        d["score"] = float(s)
    gt = kit.gt_doc(images, anns)
    ref_dets = [{**d, "segmentation": kit.rle_of(d["segmentation"])} for d in dets]
    ref = kit.ref_eval(gt, ref_dets, "segm")
    got = ev.evaluate_masks(gt, dets, family="pit", min_support=1)
    for cid, (r50, r) in ref.items():
        assert got.per_class[cid].ap50 == (pytest.approx(r50, abs=TOL) if r50 is not None else None)
        assert got.per_class[cid].ap50_95 == (pytest.approx(r, abs=TOL) if r is not None else None)


# ---------------------------------------------------------------- FR-009-22: cluster bootstrap


def _clustered(n_per_cluster: int, perfect: list[bool]) -> tuple[dict, list, dict]:
    """One cluster (= scenario seed) per entry of `perfect`; `n_per_cluster` images each with one class-1 box; a cluster is either
    fully detected (a perfect detection per image) or fully missed (no detection)."""
    images, anns, dets, cluster = [], [], [], {}
    iid = 0
    for seed_id, ok in enumerate(perfect):
        for _ in range(n_per_cluster):
            iid += 1
            images.append(kit.image(iid))
            anns.append(kit.annotation(iid, iid, 1, (10, 10, 20, 20)))
            cluster[iid] = 1000 + seed_id
            if ok:
                dets.append(kit.detection(iid, 1, (10, 10, 20, 20), 0.5 + iid / 10_000))
    return kit.gt_doc(images, anns), dets, cluster


@pytest.mark.req("FR-009-22")
def test_two_clusters_of_five_images_one_perfect_one_missed_give_the_interval_zero_one() -> None:
    gt, dets, cluster = _clustered(5, [True, False])
    r = ev.bootstrap_intervals(gt, dets, cluster, seed=90210, min_support=1)
    assert r.map50 == pytest.approx((0.0, 1.0), abs=TOL)
    assert r.per_class[1]["ap50"] == pytest.approx((0.0, 1.0), abs=TOL)
    assert r.per_class[1]["ap50_95"] == pytest.approx((0.0, 1.0), abs=TOL)
    assert set(r.per_class) == {1}  # only classes with support


@pytest.mark.req("FR-009-22")
def test_identical_perfect_clusters_give_the_degenerate_interval() -> None:
    gt, dets, cluster = _clustered(3, [True] * 6)
    r = ev.bootstrap_intervals(gt, dets, cluster, seed=1, min_support=1, resamples=300)
    assert r.map50 == (pytest.approx(1.0, abs=TOL), pytest.approx(1.0, abs=TOL))


@pytest.mark.req("FR-009-22")
def test_the_bootstrap_is_deterministic_for_a_seed_and_the_wider_level_contains_the_narrower() -> None:
    gt, dets, cluster = _clustered(2, [True, True, False, True, False, True])
    a = ev.bootstrap_intervals(gt, dets, cluster, seed=5, min_support=1, resamples=400)
    b = ev.bootstrap_intervals(gt, dets, cluster, seed=5, min_support=1, resamples=400)
    assert a == b
    narrow = ev.bootstrap_intervals(gt, dets, cluster, seed=5, min_support=1, resamples=400, level=0.5)
    assert a.map50[0] <= narrow.map50[0] <= narrow.map50[1] <= a.map50[1]
    assert 0.0 <= a.map50[0] <= a.map50[1] <= 1.0


@pytest.mark.req("FR-009-22")
def test_the_interval_on_a_random_fixture_is_ordered_and_inside_the_unit_range() -> None:
    gt, dets = kit.random_fixture(21, n_images=24, max_boxes=6)
    cluster = {i: 7000 + (i - 1) // 3 for i in range(1, 25)}  # 8 clusters of 3 images
    r = ev.bootstrap_intervals(gt, dets, cluster, seed=3, min_support=1, resamples=200)
    lo, hi = r.map50
    assert 0.0 <= lo <= hi <= 1.0
    for per in r.per_class.values():
        for a, b in per.values():
            assert 0.0 <= a <= b <= 1.0


@pytest.mark.req("FR-009-22")
def test_hostile_bootstrap_arguments_are_rejected() -> None:
    gt, dets, cluster = _clustered(1, [True, False])
    base = {"seed": 1, "min_support": 1, "resamples": 10}
    for kwargs, arg in [
        ({"resamples": 0}, "resamples"),
        ({"level": 0.0}, "level"),
        ({"level": 1.0}, "level"),
        ({"level": float("nan")}, "level"),
        ({"seed": "1"}, "seed"),
    ]:
        with pytest.raises(ValueError, match=arg):
            ev.bootstrap_intervals(gt, dets, cluster, **{**base, **kwargs})
    with pytest.raises(ValueError, match="image_cluster"):
        ev.bootstrap_intervals(gt, dets, {1: 1000}, **base)
