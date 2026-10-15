"""Layer-4 parity of every engine against the stored PyTorch fp32 golden outputs (FR-016-30)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio.export.comparator import compare

RTOL, ATOL = 1e-3, 1e-5
METRIC_DELTA_MAX_PP = 1.0
MASK_IOU_MIN = 0.99


@dataclass(frozen=True)
class CellParity:
    verdict: str
    reason: str | None
    max_abs_error: float | None = None
    mismatch_fraction: float | None = None
    metric_delta_pp: float | None = None
    mask_iou: float | None = None


def check_cell(
    *,
    precision: str,
    reference: Sequence[np.ndarray] | None = None,
    candidate: Sequence[np.ndarray] | None = None,
    tf32_cleared: bool = True,
    metric: Mapping[str, Any] | None = None,
    mask_iou: float | None = None,
    requires_mask_iou: bool = False,
    requires_robustness: bool = False,
    robustness_ok: bool | None = None,
) -> CellParity:
    """fp32: elementwise rtol 1e-3 / atol 1e-5; fp16, int8 and fp8: task metric within 1 pp (and mask IoU, robustness)."""
    if precision == "fp32":
        if not tf32_cleared:
            return CellParity("rejected", "TF32 was not cleared on the engine build or the reference run")
        if reference is None or candidate is None:
            return CellParity("rejected", "reference or candidate outputs are missing")
        result = compare(reference, candidate, rtol=RTOL, atol=ATOL, max_abs=math.inf)
        if result.verdict == "pass":
            return CellParity("pass", None, result.max_abs_error, result.mismatch_fraction)
        return CellParity("rejected", result.reason, result.max_abs_error, result.mismatch_fraction)

    if metric is None:
        return CellParity("rejected", "task metric was not measured")
    delta = metric["variant"] - metric["fp32"]
    reasons: list[str] = []
    if not math.isfinite(delta):
        reasons.append("task metric is not finite")
    elif abs(delta) > METRIC_DELTA_MAX_PP:
        reasons.append(f"task metric changed by {delta:+.3g} pp, more than {METRIC_DELTA_MAX_PP:g} pp")
    if requires_mask_iou:
        if mask_iou is None or not math.isfinite(mask_iou):
            reasons.append("mask IoU was not measured")
        elif mask_iou < MASK_IOU_MIN:
            reasons.append(f"mask IoU {mask_iou:.3f} is below {MASK_IOU_MIN}")
    if requires_robustness and robustness_ok is not True:
        reasons.append("detector robustness criterion " + ("failed" if robustness_ok is False else "was not evaluated"))
    if reasons:
        return CellParity("rejected", "; ".join(reasons), None, None, delta, mask_iou)
    return CellParity("pass", None, None, None, delta, mask_iou)


def make_parity_report(
    cell: CellParity,
    *,
    precision: str,
    run_id: str,
    git_sha: str,
    model: str,
    backend: str,
    tensorrt_version: str | None,
    onnx_sha256: str,
    engine_sha256: str | None,
    golden_set: Mapping[str, Any],
    metric: Mapping[str, Any] | None = None,
    variant: str = "deployed",
    fixture: bool = False,
) -> dict[str, Any]:
    """The DC-016-03 document of layer 4 with the constant tolerances of the precision."""
    fp32 = precision == "fp32"
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "git_sha": git_sha,
        "layer": 4,
        "model": model,
        "variant": variant,
        "precision": precision,
        "backend": backend,
        "tensorrt_version": tensorrt_version,
        "onnx_sha256": onnx_sha256,
        "engine_sha256": engine_sha256,
        "golden_set": dict(golden_set),
        "tolerances": {
            "rtol": RTOL if fp32 else None,
            "atol": ATOL if fp32 else None,
            "max_abs": None,
            "metric_delta_pp_max": None if fp32 else 1,
            "mask_iou_min": None if fp32 else MASK_IOU_MIN,
        },
        "max_abs_error": cell.max_abs_error,
        "mismatch_fraction": cell.mismatch_fraction,
        "argmax": None,
        "metric": None
        if metric is None
        else {"id": metric["id"], "unit": "pct", "fp32": metric["fp32"], "variant": metric["variant"], "delta_pp": cell.metric_delta_pp},
        "mask_iou": cell.mask_iou,
        "verdict": cell.verdict,
    }
    if cell.reason:
        report["reason"] = cell.reason[:300]
    if fixture:
        report["fixture"] = True
    return report
