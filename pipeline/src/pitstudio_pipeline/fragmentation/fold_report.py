"""Per-fold TRTR evaluation report of D1 (spec 012): foreground IoU, instance PSD curves and training curves.

CPU only. For each fold of the on-disk five-fold run the fold's TRTR U-Net (`best.pt`) segments the fold's test originals,
the foreground IoU of every file is recomputed (FR-012-29) and compared with the value the training run stored, the
instances are decoded (FR-012-19) and the instance PSD of FR-012-24 (equivalent-circle diameter in pixels,
area-weighted) is pooled over the fold's test originals for the ground truth and for the prediction.

Only metrics leave this module (FR-012-38): no image, mask, crop or thumbnail is written.
"""
# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from pitstudio_pipeline.fragmentation import psd as psdmod
from pitstudio_pipeline.fragmentation.labels import decode_instances
from pitstudio_pipeline.fragmentation.metrics import foreground_iou
from pitstudio_pipeline.fragmentation.unet import build_unet, infer, normalise

ATTRIBUTION = "Metrics computed on Mendeley Data set 78ht3pjsr4, CC BY 4.0; no image is redistributed."
SIZE_BASIS = (
    "equivalent-circle diameter 2 sqrt(A / pi) of each instance, in pixels of the 512 x 512 image (the pixel scale of the "
    "real images is not recorded, so no metre value is claimed); passing = area of instances up to that size over the "
    "total instance area (FR-012-24)"
)
GRID_POINTS = 90
GRID_RANGE_PX = (2.0, 400.0)
OVERSIZE_FACTOR = 2.0  # oversize limit = 2 x the pooled ground-truth x50 of all test originals (px)
IOU_TOLERANCE = 1e-4  # the run stored per-file IoU rounded to 5 decimals


def load_fold_model(best_pt: Path) -> nn.Module:
    """The TRTR U-Net of a fold from its state dict; no weight download (`encoder_weights=None`)."""
    model = build_unet(encoder_weights=None)
    model.load_state_dict(torch.load(best_pt, map_location="cpu", weights_only=True))
    return model.eval()


def predict_instances(model: nn.Module, images: np.ndarray, *, batch: int = 4) -> list[tuple[np.ndarray, np.ndarray]]:
    """(instances int32, foreground bool) of each (H, W, 3) uint8 image, by FR-012-19 on the softmax of the model."""
    out: list[tuple[np.ndarray, np.ndarray]] = []
    with torch.inference_mode():
        for start in range(0, len(images), batch):
            x = torch.stack([normalise(img) for img in images[start : start + batch]])
            probs = infer(model, x).numpy()
            out.extend(decode_instances(p) for p in probs)
    return out


def size_grid() -> np.ndarray:
    return np.geomspace(GRID_RANGE_PX[0], GRID_RANGE_PX[1], GRID_POINTS)


def passing_on_grid(psd: psdmod.Psd, grid: np.ndarray) -> list[float]:
    """Area passing fraction at each grid size (step function of the passing points)."""
    index = np.searchsorted(psd.sizes, grid, side="right") - 1
    return [float(psd.passing[i]) if i >= 0 else 0.0 for i in index]


def _summary(areas: np.ndarray, limit_px: float) -> dict[str, Any]:
    psd, fit = psdmod.fit_instances(areas)
    if psd is None:
        return {"n_instances": int(areas.size), "status": "no-fit"}
    return {
        "n_instances": psd.n_instances,
        "total_area_px": psd.total_area_px,
        "p20_px": psdmod.weighted_quantile(psd, 0.2),
        "p50_px": psdmod.weighted_quantile(psd, 0.5),
        "p80_px": psdmod.weighted_quantile(psd, 0.8),
        "oversize_share": psdmod.oversize_share(psd, limit_px),
        "swebrec_fit": {"status": fit.status, "x50_px": fit.x50, "b": fit.b, "x_max_px": fit.x_max, "rmse": fit.rmse},
    }


def _x50(areas: np.ndarray) -> float | None:
    psd, fit = psdmod.fit_instances(areas)
    return fit.x50 if psd is not None and fit.status == "ok" else None


def evaluate_files(
    model: nn.Module, images: np.ndarray, labels: np.ndarray, files: Sequence[int], *, batch: int = 4
) -> list[dict[str, Any]]:
    """Per test file (1-based number): recomputed foreground IoU, ground-truth and predicted instance areas (px)."""
    picks = [int(f) - 1 for f in files]
    predictions = predict_instances(model, np.stack([images[i] for i in picks]), batch=batch)
    rows = []
    for number, i, (instances, foreground) in zip(files, picks, predictions, strict=True):
        truth = np.asarray(labels[i])
        rows.append(
            {
                "file": int(number),
                "iou": foreground_iou(foreground, truth > 0),
                "gt_areas": psdmod.instance_areas(truth.astype(np.int64)),
                "pred_areas": psdmod.instance_areas(instances),
            }
        )
    return rows


def fold_section(result: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], limit_px: float) -> dict[str, Any]:
    """The report entry of one fold from the stored `result.json` and the evaluated rows."""
    stored = result["test_fg_iou_per_file"]
    diffs = [abs(r["iou"] - stored[str(r["file"])]) for r in rows]
    gt = np.concatenate([r["gt_areas"] for r in rows])
    pred = np.concatenate([r["pred_areas"] for r in rows])
    grid = size_grid()
    errors = []
    no_fit = {"ground_truth": 0, "unet": 0}
    for r in rows:
        x_gt, x_pred = _x50(r["gt_areas"]), _x50(r["pred_areas"])
        no_fit["ground_truth"] += x_gt is None
        no_fit["unet"] += x_pred is None
        # FR-012-25: a no-fit image counts with relative error 1.0; FR-012-31: |x_hat - x_ref| / x_ref against the truth fit
        if x_gt is not None:
            errors.append(1.0 if x_pred is None else abs(x_pred - x_gt) / x_gt)
    gt_psd, pred_psd = psdmod.image_psd(gt), psdmod.image_psd(pred)
    return {
        "fold": int(result["fold"]),
        "n_train": int(result["n_train"]),
        "n_val": int(result["n_val"]),
        "n_test": int(result["n_test"]),
        "test_fg_iou_mean_run": float(result["test_fg_iou_mean"]),
        "test_fg_iou_mean_recomputed": float(np.mean([r["iou"] for r in rows])),
        "iou_max_abs_difference_vs_run": float(max(diffs)),
        "iou_files_reproduced": int(sum(d <= IOU_TOLERANCE for d in diffs)),
        "gt": _summary(gt, limit_px),
        "unet": _summary(pred, limit_px),
        "x50_relative_error_mean": float(np.mean(errors)) if errors else None,
        "x50_relative_error_median": float(np.median(errors)) if errors else None,
        "x50_images_no_fit": no_fit,
        "psd_curve": {
            "size_px": [float(x) for x in grid],
            "gt_passing": passing_on_grid(gt_psd, grid),
            "unet_passing": passing_on_grid(pred_psd, grid),
        },
    }


def training_curves(metrics_jsonl: Path) -> dict[str, list[float]]:
    """Epoch, loss and validation foreground IoU of a fold from its `metrics.jsonl`."""
    rows = [json.loads(line) for line in metrics_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = [r for r in rows if "val_fg_iou" in r and "epoch" in r]
    return {
        "epoch": [int(r["epoch"]) for r in rows],
        "loss": [float(r["loss"]) for r in rows],
        "val_fg_iou": [float(r["val_fg_iou"]) for r in rows],
    }


def build_report(
    run_dir: Path,
    images: np.ndarray,
    labels: np.ndarray,
    *,
    loader: Callable[[Path], nn.Module] = load_fold_model,
    folds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """The D1 per-fold report of the run folder `run_dir` (fold0..foldN with best.pt, result.json, metrics.jsonl)."""
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    numbers = list(range(len(summary["folds"]))) if folds is None else list(folds)
    results = {n: json.loads((run_dir / f"fold{n}" / "result.json").read_text(encoding="utf-8")) for n in numbers}
    evaluated = {}
    for n in numbers:
        files = sorted(int(k) for k in results[n]["test_fg_iou_per_file"])
        evaluated[n] = evaluate_files(loader(run_dir / f"fold{n}" / "best.pt"), images, labels, files)
    pooled_gt = np.concatenate([r["gt_areas"] for n in numbers for r in evaluated[n]])
    limit = OVERSIZE_FACTOR * float(psdmod.weighted_quantile(psdmod.image_psd(pooled_gt), 0.5))
    sections = [fold_section(results[n], evaluated[n], limit) for n in numbers]
    for n, section in zip(numbers, sections, strict=True):
        section["training"] = training_curves(run_dir / f"fold{n}" / "metrics.jsonl")
    ious = [s["test_fg_iou_mean_recomputed"] for s in sections]
    pooled_pred = np.concatenate([r["pred_areas"] for n in numbers for r in evaluated[n]])
    grid = size_grid()
    return {
        "arm": summary["arm"],
        "label": "real images (Mendeley Data 78ht3pjsr4, CC BY 4.0); metrics only, no image is published",
        "attribution": ATTRIBUTION,
        "size_basis": SIZE_BASIS,
        "oversize_limit_px": limit,
        "oversize_rule": f"area share of instances larger than {OVERSIZE_FACTOR:g} x the pooled ground-truth P50 of all test originals",
        "device": "cpu",
        "run_summary": {k: summary[k] for k in ("mean", "std", "min")},
        "recomputed_mean_iou": float(np.mean(ious)),
        "iou_max_abs_difference_vs_run": float(max(s["iou_max_abs_difference_vs_run"] for s in sections)),
        "pooled": {
            "n_test": int(sum(s["n_test"] for s in sections)),
            "gt": _summary(pooled_gt, limit),
            "unet": _summary(pooled_pred, limit),
            "psd_curve": {
                "size_px": [float(x) for x in grid],
                "gt_passing": passing_on_grid(psdmod.image_psd(pooled_gt), grid),
                "unet_passing": passing_on_grid(psdmod.image_psd(pooled_pred), grid),
            },
        },
        "folds": sections,
    }


def write_report(report: Mapping[str, Any], path: Path) -> None:
    text = json.dumps(report, indent=1, sort_keys=True, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m pitstudio_pipeline.fragmentation.fold_report --run-dir DIR --data DIR --out FILE` (CPU)."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--run-dir", type=Path, required=True, help="folder with summary.json and fold0..foldN")
    parser.add_argument("--data", type=Path, required=True, help="folder with images.npy and labels.npy")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=0, help="torch CPU threads (0 = torch default)")
    args = parser.parse_args(argv)
    if args.threads:
        torch.set_num_threads(args.threads)
    images = np.load(args.data / "images.npy", mmap_mode="r")
    labels = np.load(args.data / "labels.npy", mmap_mode="r")
    report = build_report(args.run_dir, images, labels)
    write_report(report, args.out)
    print(
        f"wrote {args.out}: mean IoU {report['recomputed_mean_iou']:.5f}, max |diff| to the run {report['iou_max_abs_difference_vs_run']:.2e}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
