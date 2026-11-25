"""Box and mask AP with cluster-bootstrap intervals, and the checks on prediction inputs (FR-009-22, FR-009-23,
FR-009-43).

The protocol is the COCO one as implemented by `pycocotools`: IoU thresholds 0.50:0.05:0.95, 101 recall points,
`maxDets` 100,
area "all". `pycocotools` does the per-image matching (`COCOeval.evaluate`); the accumulation over images is the same
arithmetic as `COCOeval.accumulate`, redone here over cached per-image results so that a bootstrap resample (which pools
images, one image possibly several times) costs a concatenation and a sort instead of a full evaluation. Tests compare
every value with `COCOeval` called directly.
"""

from __future__ import annotations

import contextlib
import copy
import io
import math
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

CATEGORY_IDS = (1, 2, 3, 4, 5)
MAX_DETECTIONS_PER_IMAGE = 300  # spec 009 FR-009-43 (the D-FINE and RF-DETR heads output at most 300 / 100 queries)
_MAX_DETS = 100  # COCO maxDets
_RECALL = np.linspace(0.0, 1.0, 101)  # the grid of COCOeval.accumulate (np.linspace(.0, 1.00, 101))
_N_IOU = 10  # 0.50:0.05:0.95


# ----------------------------------------------------------------------------------------------------------------
# input checks (FR-009-43)
# ----------------------------------------------------------------------------------------------------------------
class PredictionError(ValueError):
    """A prediction input is rejected and no metric is computed from it.

    `code`: schema, non-finite, unknown-image, unknown-category, too-many-detections or arms-mismatch; `reason` names
    the
    offending id, count or field; `index` is the position of the offending detection (None for set-level errors).
    """

    def __init__(self, code: str, reason: str, index: int | None = None) -> None:
        self.code, self.reason, self.index = code, reason, index
        where = f" (detection {index})" if index is not None else ""
        super().__init__(f"{code}{where}: {reason}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def validate_predictions(
    gt: Mapping[str, Any], detections: Sequence[Mapping[str, Any]], *, require_bbox: bool = True
) -> None:
    """Check a detection list against the test set `gt`; raise `PredictionError` for the first bad detection.

    Per detection, in order: it is a mapping with int `image_id` and `category_id`, a 4-number `bbox` (unless
    `require_bbox` is False, for mask detections) and a numeric `score` (schema); score and box are finite (non-finite);
    the image is a test image (unknown-image); the category is in 1..5 (unknown-category). Then at most 300 detections
    per
    image (too-many-detections).
    """
    image_ids = {im["id"] for im in gt["images"]}
    per_image: Counter[int] = Counter()
    for i, det in enumerate(detections):
        if not isinstance(det, Mapping):
            raise PredictionError("schema", f"detection {i} is not an object", i)
        if not _is_int(det.get("image_id")) or not _is_int(det.get("category_id")) or not _is_number(det.get("score")):
            raise PredictionError("schema", "image_id and category_id must be ints and score a number", i)
        bbox = det.get("bbox")
        if (require_bbox or bbox is not None) and (
            not isinstance(bbox, list | tuple) or len(bbox) != 4 or not all(_is_number(v) for v in bbox)
        ):
            raise PredictionError("schema", "bbox must be 4 numbers [x, y, w, h]", i)
        values = [det["score"], *(bbox if isinstance(bbox, list | tuple) else [])]
        if not all(math.isfinite(v) for v in values):
            raise PredictionError("non-finite", "score or box holds a NaN or infinity", i)
        if det["image_id"] not in image_ids:
            raise PredictionError("unknown-image", f"image id {det['image_id']} is not a test image", i)
        if det["category_id"] not in CATEGORY_IDS:
            raise PredictionError("unknown-category", f"category id {det['category_id']} is not one of 1..5", i)
        per_image[det["image_id"]] += 1
    for image_id, count in per_image.items():
        if count > MAX_DETECTIONS_PER_IMAGE:
            raise PredictionError(
                "too-many-detections", f"image {image_id} has {count} detections, more than {MAX_DETECTIONS_PER_IMAGE}"
            )


def validate_arm_coverage(image_ids_a: Collection[int], image_ids_b: Collection[int]) -> None:
    """The two arms of the DR ablation must cover the same test images; `arms-mismatch` lists the difference."""
    a, b = set(image_ids_a), set(image_ids_b)
    if a != b or not a:
        raise PredictionError(
            "arms-mismatch",
            f"the arms cover different test images: only in the first {sorted(a - b)}, "
            f"only in the second {sorted(b - a)}",
        )


# ----------------------------------------------------------------------------------------------------------------
# COCO protocol over cached per-image results
# ----------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ClassMetrics:
    """Ground-truth instances of a class and its AP50 / AP50:95 (None when the class has no instance)."""

    support: int
    ap50: float | None
    ap50_95: float | None


@dataclass(frozen=True)
class BoxEval:
    """Box AP per class and the unweighted mean over the classes with at least `min_support` instances."""

    per_class: dict[int, ClassMetrics]
    map50: float | None
    map50_95: float | None
    classes_included: tuple[int, ...]


@dataclass(frozen=True)
class MaskEval:
    """Mask AP, as `BoxEval`; `descriptive` is True for the crusher family (outside the acceptance, FR-009-23)."""

    per_class: dict[int, ClassMetrics]
    map50: float | None
    map50_95: float | None
    classes_included: tuple[int, ...]
    descriptive: bool


@dataclass(frozen=True)
class BootstrapResult:
    """95 % (by default) cluster-bootstrap intervals of mAP50 and of every supported class's AP50 and AP50:95."""

    map50: tuple[float, float]
    per_class: dict[int, dict[str, tuple[float, float]]]


class _Entry:
    """Per-image, per-class evaluation result: detection scores (descending), matches and ignores per IoU threshold."""

    __slots__ = ("dt_ignore", "dt_matches", "dt_scores", "npig")

    def __init__(self, scores: np.ndarray, matches: np.ndarray, ignore: np.ndarray, npig: int) -> None:
        self.dt_scores, self.dt_matches, self.dt_ignore, self.npig = scores, matches, ignore, npig


class Prepared:
    """Per-image results of one prediction set: `entries[category id][image id]` and the category ids."""

    def __init__(self, image_ids: list[int], cat_ids: list[int], entries: dict[int, dict[int, _Entry]]) -> None:
        self.image_ids, self.cat_ids, self.entries = image_ids, cat_ids, entries

    def support(self, image_ids: Sequence[int] | None = None) -> dict[int, int]:
        ids = self.image_ids if image_ids is None else image_ids
        return {c: sum(self.entries[c][i].npig for i in ids if i in self.entries[c]) for c in self.cat_ids}


def _check_min_support(min_support: object) -> int:
    if not _is_int(min_support) or min_support < 1:  # type: ignore[operator]
        raise ValueError(f"min_support must be an int >= 1, got {min_support!r}")
    return int(min_support)  # type: ignore[arg-type]


def _to_rle(segmentation: Any, height: int, width: int) -> dict[str, Any]:
    from pycocotools import mask as mask_utils

    if isinstance(segmentation, np.ndarray):
        if segmentation.shape != (height, width):
            raise ValueError(f"segmentation mask has shape {segmentation.shape}, the image is {height} x {width}")
        return mask_utils.encode(np.asfortranarray(segmentation.astype(np.uint8)))  # type: ignore[no-any-return]
    if isinstance(segmentation, Mapping) and "counts" in segmentation and "size" in segmentation:
        return dict(segmentation)
    raise ValueError("segmentation must be a binary numpy array or an RLE dict")


def prepare(gt: Mapping[str, Any], detections: Sequence[Mapping[str, Any]], iou_type: str = "bbox") -> Prepared:
    """Match detections to ground truth image by image (pycocotools) and cache the per-image, per-class results."""
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    cat_ids = sorted(int(c["id"]) for c in gt["categories"])
    image_ids = sorted(int(im["id"]) for im in gt["images"])
    empty = (np.zeros(0), np.zeros((_N_IOU, 0)), np.zeros((_N_IOU, 0), dtype=bool))
    npig = {c: Counter() for c in cat_ids}
    for a in gt["annotations"]:
        if not a.get("iscrowd", 0):
            npig[int(a["category_id"])][int(a["image_id"])] += 1
    entries: dict[int, dict[int, _Entry]] = {c: {} for c in cat_ids}
    results: list[Any] = []
    if detections:
        sizes = {int(im["id"]): (int(im["height"]), int(im["width"])) for im in gt["images"]}
        dets: list[dict[str, Any]] = []
        for d in detections:
            item = {"image_id": int(d["image_id"]), "category_id": int(d["category_id"]), "score": float(d["score"])}
            if iou_type == "segm":
                item["segmentation"] = _to_rle(d["segmentation"], *sizes[item["image_id"]])
            else:
                item["bbox"] = [float(v) for v in d["bbox"]]
            dets.append(item)
        with contextlib.redirect_stdout(io.StringIO()):
            coco_gt = COCO()
            coco_gt.dataset = copy.deepcopy(dict(gt))
            coco_gt.createIndex()
            coco_dt = coco_gt.loadRes(dets)
            ev = COCOeval(coco_gt, coco_dt, iou_type)
            ev.params.maxDets = [_MAX_DETS]
            ev.params.areaRng = [[0.0, 1e10]]
            ev.params.areaRngLbl = ["all"]
            ev.params.imgIds = image_ids
            ev.params.catIds = cat_ids
            ev.evaluate()
        results = ev.evalImgs  # [category][area][image] flat; one area range
    n_img = len(image_ids)
    for k, c in enumerate(cat_ids):
        for j, image_id in enumerate(image_ids):
            n_gt = npig[c][image_id]
            res = results[k * n_img + j] if results else None
            if res is None:
                if n_gt:
                    entries[c][image_id] = _Entry(*empty, n_gt)
                continue
            entries[c][image_id] = _Entry(
                np.asarray(res["dtScores"], dtype=np.float64),
                np.asarray(res["dtMatches"], dtype=np.float64),
                np.asarray(res["dtIgnore"], dtype=bool),
                int((np.asarray(res["gtIgnore"]) == 0).sum()),
            )
    return Prepared(image_ids, cat_ids, entries)


def _accumulate(entries: Sequence[_Entry]) -> tuple[float, float] | None:
    """AP50 and AP50:95 of one class over per-image results (COCOeval.accumulate); None without ground truth."""
    npig = sum(e.npig for e in entries)
    if npig == 0:
        return None
    parts = [e for e in entries if e.dt_scores.size]
    if parts:
        scores = np.concatenate([e.dt_scores for e in parts])
        order = np.argsort(-scores, kind="mergesort")
        matches = np.concatenate([e.dt_matches for e in parts], axis=1)[:, order]
        ignore = np.concatenate([e.dt_ignore for e in parts], axis=1)[:, order]
        tps = np.logical_and(matches > 0, np.logical_not(ignore))
        fps = np.logical_and(matches == 0, np.logical_not(ignore))
        tp_sum = np.cumsum(tps, axis=1).astype(np.float64)
        fp_sum = np.cumsum(fps, axis=1).astype(np.float64)
    else:
        tp_sum = fp_sum = np.zeros((_N_IOU, 0))
    eps = np.spacing(1)
    ap = np.zeros(_N_IOU)
    for t in range(_N_IOU):
        tp, fp = tp_sum[t], fp_sum[t]
        nd = tp.size
        q = np.zeros(101)
        if nd:
            rc = tp / npig
            pr = tp / (fp + tp + eps)
            pr = np.maximum.accumulate(pr[::-1])[::-1]  # the precision envelope: monotone decreasing from the right
            idx = np.searchsorted(rc, _RECALL, side="left")
            valid = idx < nd
            q[valid] = pr[idx[valid]]
        ap[t] = q.mean()
    return float(ap[0]), float(ap.mean())


def _entries_of(prep: Prepared, cat: int, image_ids: Sequence[int]) -> list[_Entry]:
    table = prep.entries[cat]
    return [table[i] for i in image_ids if i in table]


def _merge(entries: Sequence[_Entry]) -> _Entry:
    """One block holding the detections and the ground-truth count of several per-image results."""
    parts = [e for e in entries if e.dt_scores.size]
    npig = sum(e.npig for e in entries)
    if not parts:
        return _Entry(np.zeros(0), np.zeros((_N_IOU, 0)), np.zeros((_N_IOU, 0), dtype=bool), npig)
    return _Entry(
        np.concatenate([e.dt_scores for e in parts]),
        np.concatenate([e.dt_matches for e in parts], axis=1),
        np.concatenate([e.dt_ignore for e in parts], axis=1),
        npig,
    )


def metrics_on(
    prep: Prepared, image_ids: Sequence[int] | None, min_support: int
) -> tuple[dict[int, ClassMetrics], float | None, float | None, tuple[int, ...]]:
    """Per-class metrics, mAP50, mAP50:95 and the included classes over `image_ids` (default: every image of `prep`)."""
    ids = prep.image_ids if image_ids is None else sorted(image_ids)
    per_class: dict[int, ClassMetrics] = {}
    for c in prep.cat_ids:
        entries = _entries_of(prep, c, ids)
        support = sum(e.npig for e in entries)
        ap = _accumulate(entries)
        per_class[c] = ClassMetrics(support, *(ap if ap is not None else (None, None)))
    included = tuple(c for c in prep.cat_ids if per_class[c].support >= min_support)
    if not included:
        return per_class, None, None, ()
    map50 = float(np.mean([per_class[c].ap50 for c in included]))
    map50_95 = float(np.mean([per_class[c].ap50_95 for c in included]))
    return per_class, map50, map50_95, included


def evaluate_boxes(
    gt: Mapping[str, Any], detections: Sequence[Mapping[str, Any]], *, min_support: int = 100
) -> BoxEval:
    """Box AP50 and AP50:95 per class and the mean over classes with at least `min_support` instances."""
    min_support = _check_min_support(min_support)
    validate_predictions(gt, detections)
    per_class, map50, map50_95, included = metrics_on(prepare(gt, detections, "bbox"), None, min_support)
    return BoxEval(per_class, map50, map50_95, included)


def evaluate_masks(
    gt: Mapping[str, Any], detections: Sequence[Mapping[str, Any]], *, family: str, min_support: int = 100
) -> MaskEval:
    """Mask AP (mask IoU) as `evaluate_boxes`; crusher-family mask metrics are descriptive (FR-009-23)."""
    if family not in ("pit", "crusher"):
        raise ValueError(f"family must be 'pit' or 'crusher', got {family!r}")
    min_support = _check_min_support(min_support)
    validate_predictions(gt, detections, require_bbox=False)
    for i, d in enumerate(detections):
        if d.get("segmentation") is None:
            raise PredictionError("schema", f"detection {i} has no segmentation", i)
    per_class, map50, map50_95, included = metrics_on(prepare(gt, detections, "segm"), None, min_support)
    return MaskEval(per_class, map50, map50_95, included, descriptive=family == "crusher")


# ----------------------------------------------------------------------------------------------------------------
# cluster bootstrap
# ----------------------------------------------------------------------------------------------------------------
def cluster_images(image_ids: Sequence[int], image_cluster: Mapping[int, int]) -> dict[int, list[int]]:
    """Group image ids by cluster (test scenario seed), clusters ordered by seed, images ascending; ValueError if an id
    has no cluster."""
    clusters: dict[int, list[int]] = {}
    for i in sorted(image_ids):
        if i not in image_cluster:
            raise ValueError(f"image_cluster has no entry for image id {i}")
        clusters.setdefault(int(image_cluster[i]), []).append(i)
    return dict(sorted(clusters.items()))


class ClusterScorer:
    """AP over any multiset of clusters (test scenario seeds) of one prediction set, from per-cluster merged blocks.

    A cluster listed twice counts twice, exactly as an image of a cluster drawn twice by a bootstrap resample.
    """

    def __init__(self, prep: Prepared, image_ids: Sequence[int], image_cluster: Mapping[int, int]) -> None:
        self.prep = prep
        self.clusters = cluster_images(image_ids, image_cluster)
        self.blocks = {
            c: {k: _merge(_entries_of(prep, c, ids)) for k, ids in self.clusters.items()} for c in prep.cat_ids
        }

    def per_class(self, cluster_list: Sequence[int]) -> dict[int, tuple[float, float] | None]:
        """(AP50, AP50:95) of every class over `cluster_list`; None where the resample has no instance of it."""
        return {c: _accumulate([self.blocks[c][k] for k in cluster_list]) for c in self.prep.cat_ids}

    def map50(self, cluster_list: Sequence[int], classes: Sequence[int]) -> float:
        """Mean AP50 over `classes` (those with an instance in the resample) for `cluster_list`."""
        values = []
        for c in classes:
            ap = _accumulate([self.blocks[c][k] for k in cluster_list])
            if ap is not None:
                values.append(ap[0])
        return float(np.mean(values)) if values else 0.0


def _check_bootstrap_args(resamples: object, level: object, seed: object) -> None:
    if not _is_int(resamples) or resamples < 1:  # type: ignore[operator]
        raise ValueError(f"resamples must be an int >= 1, got {resamples!r}")
    if not isinstance(level, int | float) or isinstance(level, bool) or not (0.0 < level < 1.0):
        raise ValueError(f"level must be in (0, 1), got {level!r}")
    if not _is_int(seed):
        raise ValueError(f"seed must be an int, got {seed!r}")


def bootstrap_prepared(
    prep: Prepared,
    image_ids: Sequence[int] | None,
    image_cluster: Mapping[int, int],
    *,
    resamples: int,
    level: float,
    seed: int,
    min_support: int,
) -> BootstrapResult:
    """Cluster-bootstrap percentile intervals over the images `image_ids` of an already matched prediction set."""
    _check_bootstrap_args(resamples, level, seed)
    ids = prep.image_ids if image_ids is None else list(image_ids)
    _, _, _, included = metrics_on(prep, ids, min_support)
    support = prep.support(ids)
    supported = [c for c in prep.cat_ids if support[c] >= 1]
    scorer = ClusterScorer(prep, ids, image_cluster)
    keys = list(scorer.clusters)
    rng = np.random.default_rng(seed)
    values: dict[int, list[tuple[float, float]]] = {c: [] for c in supported}
    map50: list[float] = []
    for _ in range(resamples):
        drawn = [keys[int(j)] for j in rng.integers(0, len(keys), size=len(keys))]
        row: dict[int, tuple[float, float] | None] = {}
        for c in supported:
            row[c] = _accumulate([scorer.blocks[c][k] for k in drawn])
            if row[c] is not None:
                values[c].append(row[c])  # type: ignore[arg-type]
        in_set = [row[c][0] for c in included if row.get(c) is not None]  # type: ignore[index]
        if in_set:
            map50.append(float(np.mean(in_set)))
    lo_p, hi_p = 100.0 * (1.0 - level) / 2.0, 100.0 * (1.0 + level) / 2.0

    def interval(samples: Sequence[float]) -> tuple[float, float]:
        if not samples:
            return (0.0, 0.0)
        lo, hi = np.percentile(np.asarray(samples, dtype=np.float64), [lo_p, hi_p])
        return (float(lo), float(hi))

    per_class = {
        c: {"ap50": interval([v[0] for v in values[c]]), "ap50_95": interval([v[1] for v in values[c]])}
        for c in supported
    }
    return BootstrapResult(map50=interval(map50), per_class=per_class)


def bootstrap_intervals(
    gt: Mapping[str, Any],
    detections: Sequence[Mapping[str, Any]],
    image_cluster: Mapping[int, int],
    *,
    resamples: int = 2000,
    level: float = 0.95,
    seed: int,
    min_support: int = 100,
    iou_type: str = "bbox",
) -> BootstrapResult:
    """Cluster-bootstrap percentile intervals of mAP50 (over the classes of the point estimate) and of every class's AP.

    Each resample draws the clusters (test scenario seeds) with replacement, pools their images (an image of a cluster
    drawn twice counts twice) and evaluates the COCO protocol; the interval is the percentile interval of the values.
    """
    _check_bootstrap_args(resamples, level, seed)
    min_support = _check_min_support(min_support)
    if iou_type not in ("bbox", "segm"):
        raise ValueError(f"iou_type must be 'bbox' or 'segm', got {iou_type!r}")
    validate_predictions(gt, detections, require_bbox=iou_type == "bbox")
    cluster_images([int(im["id"]) for im in gt["images"]], image_cluster)  # every image needs a cluster
    prep = prepare(gt, detections, iou_type)
    return bootstrap_prepared(
        prep, None, image_cluster, resamples=resamples, level=level, seed=seed, min_support=min_support
    )
