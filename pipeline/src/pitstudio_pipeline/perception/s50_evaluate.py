"""The stage `s50_evaluate`: the detection evaluation report DC-009-05 from held-out test predictions.

For every prediction set (model, precision, training arm) it computes box AP per family (pit, crusher, pooled) and class,
the mask AP of RF-DETR-Seg-N, cluster-bootstrap intervals, the pre-registered acceptance rows (SC-009-01 ... SC-009-06),
the corruption curves, the paired DR ablation (FR-009-31) and the optional real probe (FR-009-33). It states what it did not
do: a fixture index gives a `fixture` report (FR-009-51); models named by the evaluation but absent give a `partial` report
with no pooled metric, no ablation and no pass or fail verdict (FR-009-52); a stale image fails `input-stale` before any
metric (FR-009-53); hostile predictions are refused before any metric (FR-009-43). The report is deterministic.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_pipeline.perception import evaluate as ev
from pitstudio_pipeline.perception import probe as probe_mod
from pitstudio_pipeline.perception.ablation import paired_cluster_bootstrap
from pitstudio_pipeline.perception.acceptance import NOT_EVALUABLE, acceptance_row, not_run_row
from pitstudio_pipeline.perception.classes import CLASSES
from pitstudio_pipeline.perception.honesty import HONESTY_LABEL, NOT_MEASURED
from pitstudio_pipeline.perception.robustness import ARMS, MODELS, PRECISIONS, corruption_rows, sc03_rows
from pitstudio_pipeline.perception.stages import check_index_fresh

SCHEMA_VERSION = "1.1"
FAMILIES = ("pit", "crusher")
_NAMES = dict(CLASSES)
_PARTIAL_REASON = "partial evaluation: a model or arm named by the evaluation has no evaluated checkpoint"
_DEFAULT_RESAMPLES = 2000
_DEFAULT_ABLATION_RESAMPLES = 10000
_LEVEL = 0.95


@dataclass(frozen=True)
class S50Result:
    """The report, whether it is partial and whether it comes from a fixture index."""

    report: dict[str, Any]
    partial: bool
    fixture: bool


@dataclass
class _Set:
    """One prediction set with its matched per-image results."""

    key: tuple[str, str, str]  # model, precision, arm
    detections: list[Mapping[str, Any]]
    provenance: dict[str, Any]
    fixture: bool
    box: ev.Prepared | None = None
    mask: ev.Prepared | None = None


def _seed(base: int, *labels: object) -> int:
    digest = hashlib.sha256(("|".join([str(base), *map(str, labels)])).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**63)


def _pycocotools_version() -> str:
    from importlib import metadata

    try:
        return metadata.version("pycocotools")
    except metadata.PackageNotFoundError:  # pragma: no cover - the package is a dependency of this lane
        return "unknown"


def _triple(value: object, name: str) -> tuple[str, str, str]:
    if not isinstance(value, list | tuple) or len(value) != 3:
        raise ValueError(f"{name} entry {value!r} must be a (model, precision, arm) triple")
    model, precision, arm = value
    if model not in MODELS or precision not in PRECISIONS or arm not in ARMS:
        raise ValueError(f"{name} entry {value!r} must be (model in {MODELS}, precision in {PRECISIONS}, arm in {ARMS})")
    return model, precision, arm


def _parse_expected(spec: Mapping[str, Any], present: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    raw = spec.get("expected")
    if raw is None:
        return list(present)  # the evaluation names what it was given
    if not isinstance(raw, list):
        raise ValueError(f"expected must be a list of (model, precision, arm) triples, got {raw!r}")
    out = [_triple(t, "expected") for t in raw]
    if len(set(out)) != len(out):
        raise ValueError("expected lists a (model, precision, arm) triple twice")
    return out


def _gt_counts(gt: Mapping[str, Any], image_ids: set[int]) -> dict[int, int]:
    counts = dict.fromkeys(sorted(int(c["id"]) for c in gt["categories"]), 0)
    for a in gt["annotations"]:
        if int(a["image_id"]) in image_ids:
            counts[int(a["category_id"])] += 1
    return counts


def _interval(pair: tuple[float, float]) -> dict[str, float]:
    return {"lower": float(pair[0]), "upper": float(pair[1])}


def run_s50_evaluate(spec: Mapping[str, Any]) -> S50Result:
    """Evaluate the prediction sets of `spec` and return the DC-009-05 report; see the module docstring."""
    gt = spec["gt"]
    if spec.get("index_records") is not None and spec.get("root") is not None:
        check_index_fresh(spec["index_records"], Path(spec["root"]))  # FR-009-53: before any evaluation
    min_support = spec.get("min_support", 100)
    if not isinstance(min_support, int) or isinstance(min_support, bool) or min_support < 1:
        raise ValueError(f"min_support must be an int >= 1, got {min_support!r}")
    boot_spec = spec.get("bootstrap", {})
    base_seed = int(boot_spec["seed"])
    resamples = int(boot_spec.get("resamples", _DEFAULT_RESAMPLES))
    ablation_resamples = int(boot_spec.get("ablation_resamples", _DEFAULT_ABLATION_RESAMPLES))
    image_ids = sorted(int(im["id"]) for im in gt["images"])
    family = {int(k): v for k, v in spec["image_family"].items()}
    cluster = {int(k): int(v) for k, v in spec["image_cluster"].items()}
    if any(family.get(i) not in FAMILIES for i in image_ids):
        raise ValueError(f"image_family must map every test image to one of {FAMILIES}")
    family_ids = {f: [i for i in image_ids if family[i] == f] for f in FAMILIES}
    families_to_score = {"pit": family_ids["pit"], "crusher": family_ids["crusher"], "pooled": image_ids}

    # ---- the prediction sets, checked before any metric (FR-009-43)
    sets: list[_Set] = []
    for pred in spec["predictions"]:
        key = _triple((pred.get("model"), pred.get("precision"), pred.get("arm")), "predictions")
        if any(s.key == key for s in sets):
            raise ValueError(f"predictions holds two sets for {key}")
        dets = list(pred["detections"])
        ev.validate_predictions(gt, dets, require_bbox=key[0] != "rf-detr-seg-n")
        sets.append(_Set(key, dets, dict(pred.get("provenance") or {}), bool(pred.get("fixture", False))))
    by_key = {s.key: s for s in sets}
    arm_s, arm_u = by_key.get(("d-fine-s", "fp32", "S")), by_key.get(("d-fine-s", "fp32", "U"))
    if arm_s is not None and arm_u is not None:
        ev.validate_arm_coverage(
            next(p["image_ids"] for p in spec["predictions"] if (p["model"], p["precision"], p["arm"]) == arm_s.key),
            next(p["image_ids"] for p in spec["predictions"] if (p["model"], p["precision"], p["arm"]) == arm_u.key),
        )
    corruption_sets = list(spec.get("corruption_predictions", []))
    for cp in corruption_sets:
        ev.validate_predictions(gt, list(cp["detections"]), require_bbox=cp["model"] != "rf-detr-seg-n")

    # ---- availability: expected models, partial, fixture
    expected = _parse_expected(spec, [s.key for s in sets])
    partial = any(k not in by_key for k in expected)
    fixture = bool(spec.get("fixture", False)) or any(s.fixture for s in sets)
    models: list[dict[str, Any]] = []
    for key in [*expected, *[s.key for s in sets if s.key not in expected]]:
        entry: dict[str, Any] = {"model": key[0], "precision": key[1], "arm": key[2]}
        if key in by_key:
            entry["status"] = "evaluated"
            entry["provenance"] = by_key[key].provenance
        else:
            entry["status"] = "not run (absent)"
        models.append(entry)

    # ---- metrics per set
    probe_selection = None
    if spec.get("probe") is not None:
        p = spec["probe"]
        probe_selection = probe_mod.load_probe(p["images"], p["licence_records"], annotations_b=p.get("annotations_b"))
    per_class: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    point: dict[tuple[str, str, str, str, str], float | None] = {}  # (model, precision, arm, family, task) -> map50
    support_of: dict[tuple[str, str, str, str, str], dict[int, int]] = {}
    for s in sets:
        model, precision, arm = s.key
        tasks: list[tuple[str, str]] = []
        if model != "rf-detr-seg-n" or all(d.get("bbox") is not None for d in s.detections):
            tasks.append(("box", "bbox"))
        if model == "rf-detr-seg-n" and all(d.get("segmentation") is not None for d in s.detections) and s.detections:
            tasks.append(("mask", "segm"))
        for task, iou_type in tasks:
            prep = ev.prepare(gt, s.detections, iou_type)
            if task == "box":
                s.box = prep
            else:
                s.mask = prep
            for fam, ids in families_to_score.items():
                if not ids or (partial and fam == "pooled") or (task == "mask" and fam == "pooled"):
                    continue
                per, map50, _, included = ev.metrics_on(prep, ids, min_support)
                boot = ev.bootstrap_prepared(
                    prep,
                    ids,
                    cluster,
                    resamples=resamples,
                    level=_LEVEL,
                    seed=_seed(base_seed, model, precision, arm, fam, task),
                    min_support=min_support,
                )
                descriptive = task == "mask" and fam == "crusher"
                for cid in sorted(per):
                    m = per[cid]
                    row: dict[str, Any] = {
                        "model": model,
                        "precision": precision,
                        "training_arm": arm,
                        "family": fam,
                        "task": task,
                        "class": _NAMES[cid],
                        "support": m.support,
                        "descriptive": descriptive,
                        "honesty_label": HONESTY_LABEL,
                        "sim_to_real": "measured" if probe_selection is not None and cid in probe_mod.PROBE_CLASSES else NOT_MEASURED,
                    }
                    if m.support > 0:
                        row["ap50"], row["ap50_95"] = float(m.ap50), float(m.ap50_95)  # type: ignore[arg-type]
                        row["ap50_interval"] = _interval(boot.per_class[cid]["ap50"])
                        row["ap50_95_interval"] = _interval(boot.per_class[cid]["ap50_95"])
                    per_class.append(row)
                srow: dict[str, Any] = {
                    "model": model,
                    "precision": precision,
                    "training_arm": arm,
                    "family": fam,
                    "task": task,
                    "metric": "mask_ap50" if task == "mask" else "map50",
                    "classes_included": [_NAMES[c] for c in included],
                    "descriptive": descriptive,
                }
                if included:
                    srow["value"] = float(map50)  # type: ignore[arg-type]
                    srow["interval"] = _interval(boot.map50)
                summary.append(srow)
                point[(model, precision, arm, fam, task)] = map50
                support_of[(model, precision, arm, fam, task)] = {c: per[c].support for c in per}

    # ---- corruption curves (pooled mAP50 of the detectors, pit mask AP50 of RF-DETR-Seg-N; descriptive)
    corruption: list[dict[str, Any]] = []
    if not partial:
        clean: dict[tuple[str, str, str], float] = {}
        for s in sets:
            task, fam = ("mask", "pit") if s.key[0] == "rf-detr-seg-n" else ("box", "pooled")
            m = point.get((*s.key, fam, task))
            if m is not None and m > 0:
                clean[s.key] = m
        corrupted: dict[tuple[str, str, str, str, int], float] = {}
        for cp in corruption_sets:
            key = (cp["model"], cp["precision"], cp["arm"], cp["corruption"], int(cp["severity"]))
            task, iou_type, ids = (
                ("mask", "segm", family_ids["pit"]) if cp["model"] == "rf-detr-seg-n" else ("box", "bbox", image_ids)
            )
            prep = ev.prepare(gt, list(cp["detections"]), iou_type)
            _, m, _, _ = ev.metrics_on(prep, ids, min_support)
            if m is not None:
                corrupted[key] = float(m)
        corruption = corruption_rows(clean, corrupted)

    # ---- the paired DR ablation (FR-009-31)
    ablation: dict[str, Any] | None = None
    pit_ids = family_ids["pit"]
    if (
        not partial
        and arm_s is not None
        and arm_u is not None
        and arm_s.box is not None
        and arm_u.box is not None
        and len(ev.cluster_images(pit_ids, cluster)) >= 2
    ):
        ablation = _ablation(
            gt, arm_s, arm_u, pit_ids, cluster, min_support, ablation_resamples, _seed(base_seed, "ablation"), spec
        )

    # ---- acceptance
    acceptance = _acceptance(gt, image_ids, family_ids, by_key, point, support_of, corruption, min_support, partial)

    families_status: list[dict[str, Any]] = []
    given = spec.get("family_status", {})
    for f in FAMILIES:
        if f in given and given[f].get("status") == "not run":
            families_status.append({"family": f, "status": "not run", "reason": str(given[f]["reason"])[:300]})
        elif not family_ids[f]:
            families_status.append(
                {"family": f, "status": "not run", "reason": "no held-out test image of this family"}
            )
        else:
            families_status.append({"family": f, "status": "run"})

    order = {n: i for i, n in enumerate(_NAMES.values())}
    per_class.sort(
        key=lambda r: (r["model"], r["precision"], r["training_arm"], r["family"], r["task"], order[r["class"]])
    )
    summary.sort(key=lambda r: (r["model"], r["precision"], r["training_arm"], r["family"], r["task"]))
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": spec["run_id"],
        "test_data": "synthetic held-out",
        "honesty_label": HONESTY_LABEL,
        "sim_to_real": NOT_MEASURED,
        "protocol": {
            "implementation": "pycocotools",
            "implementation_version": _pycocotools_version(),
            "iou_thresholds": "0.50:0.05:0.95",
            "recall_points": 101,
            "max_dets": 100,
            "area": "all",
            "min_support": min_support,
        },
        "bootstrap": {
            "resamples": resamples,
            "method": "cluster-percentile",
            "cluster": "test-scenario-seed",
            "level": _LEVEL,
            "seed": base_seed,
        },
        "families": families_status,
        "per_class": per_class,
        "summary": summary,
        "corruption": corruption,
        "acceptance": acceptance,
        "models": models,
    }
    if ablation is not None:
        report["dr_ablation"] = ablation
    if partial:
        report["partial"] = True
    if fixture:
        report["fixture"] = True
    if probe_selection is not None:
        p = spec["probe"]
        keep = {int(i["id"]) for i in probe_selection.included}
        report["real_probe"] = probe_mod.evaluate_probe(
            images=list(probe_selection.included),
            annotations_a=[a for a in p["annotations_a"] if int(a["image_id"]) in keep],
            annotations_b=[a for a in p["annotations_b"] if int(a["image_id"]) in keep],
            predictions={m: [d for d in dets if int(d["image_id"]) in keep] for m, dets in p["predictions"].items()},
            seed=base_seed,
            excluded_images=len(probe_selection.excluded),
            resamples=int(p.get("resamples", resamples)),
        )
        report["sim_to_real"] = "measured"
    return S50Result(report=report, partial=partial, fixture=fixture)


def _ablation(
    gt: Mapping[str, Any],
    arm_s: _Set,
    arm_u: _Set,
    pit_ids: list[int],
    cluster: Mapping[int, int],
    min_support: int,
    resamples: int,
    seed: int,
    spec: Mapping[str, Any],
) -> dict[str, Any]:
    assert arm_s.box is not None and arm_u.box is not None
    _, _, _, included = ev.metrics_on(arm_s.box, pit_ids, min_support)
    scorers = {a: ev.ClusterScorer(a_set.box, pit_ids, cluster) for a, a_set in (("S", arm_s), ("U", arm_u))}  # type: ignore[arg-type]
    keys = list(scorers["S"].clusters)
    points = {
        "S": ev.metrics_on(arm_s.box, pit_ids, min_support)[1],
        "U": ev.metrics_on(arm_u.box, pit_ids, min_support)[1],
    }

    def stat(arm: str):
        def f(cluster_list: Sequence[int]) -> float:
            if list(cluster_list) == keys and points[arm] is not None:
                return float(points[arm])  # type: ignore[arg-type]  # the point estimate is the per-class rows' mean
            return scorers[arm].map50(cluster_list, included)

        return f

    result = paired_cluster_bootstrap(keys, stat("S"), stat("U"), resamples=resamples, level=_LEVEL, seed=seed)
    return {
        "model": "d-fine-s",
        "precision": "fp32",
        "metric": "map50",
        "family": "pit",
        "arm_a": "S",
        "arm_b": "U",
        "difference": float(result.difference),
        "interval": {"lower": float(result.lower), "upper": float(result.upper)},
        "bootstrap": result.bootstrap_record,
        "verdict": result.verdict,
        "training_runs_per_arm": int(spec.get("training_runs_per_arm", 1)),
        "test_seeds": len(keys),
        "test_images": len(pit_ids),
    }


def _acceptance(
    gt: Mapping[str, Any],
    image_ids: list[int],
    family_ids: Mapping[str, list[int]],
    by_key: Mapping[tuple[str, str, str], _Set],
    point: Mapping[tuple[str, str, str, str, str], float | None],
    support_of: Mapping[tuple[str, str, str, str, str], dict[int, int]],
    corruption: list[dict[str, Any]],
    min_support: int,
    partial: bool,
) -> list[dict[str, Any]]:
    pooled_counts = _gt_counts(gt, set(image_ids))
    pooled_support = [("pooled", _NAMES[c], n) for c, n in sorted(pooled_counts.items())]
    rows: list[dict[str, Any]] = []

    def evaluate(criterion: str, key: tuple[str, str, str, str, str], family_label: str, **kw: Any) -> dict[str, Any]:
        sup = support_of.get(key)
        if sup is None:
            model, precision, arm = key[:3]
            return not_run_row(criterion, f"{model} {precision} arm {arm} was not evaluated", **kw)
        support = [(family_label, _NAMES[c], n) for c, n in sorted(sup.items())]
        value = point.get(key)
        if value is None and not any(1 <= n < min_support for _, _, n in support):
            return not_run_row(criterion, "no class has test instances to average over", **kw)
        return acceptance_row(criterion, value=value, support=support, min_support=min_support, **kw)

    if partial:
        for c in ("SC-009-01", "SC-009-02", "SC-009-05", "SC-009-06"):
            rows.append(not_run_row(c, _PARTIAL_REASON))
        rows += sc03_rows([], support=pooled_support, reason=_PARTIAL_REASON)
        return rows
    rows.append(evaluate("SC-009-01", ("d-fine-s", "fp32", "S", "pooled", "box"), "pooled"))
    rows.append(evaluate("SC-009-02", ("d-fine-n", "fp32", "S", "pooled", "box"), "pooled"))
    rows.append(evaluate("SC-009-05", ("rf-detr-seg-n", "fp32", "S", "pit", "mask"), "pit"))
    k32 = ("rf-detr-seg-n", "fp32", "S", "pit", "mask")
    k16 = ("rf-detr-seg-n", "fp16", "S", "pit", "mask")
    m32, m16 = point.get(k32), point.get(k16)
    if m32 is None or m16 is None:
        rows.append(not_run_row("SC-009-06", "RF-DETR-Seg-N fp32 and fp16 mask AP50 on the pit family are both needed"))
    else:
        support = [("pit", _NAMES[c], n) for c, n in sorted(support_of[k16].items())]
        rows.append(acceptance_row("SC-009-06", value=100.0 * abs(m16 - m32), support=support, min_support=min_support))
    rows += sc03_rows(corruption, support=pooled_support)
    return rows
