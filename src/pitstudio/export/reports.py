"""Layer-1 parity report documents, DC-016-03 (FR-016-04, FR-016-40)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pitstudio.export.comparator import ComparisonResult

LAYER1_TOLERANCES = {"rtol": 1e-3, "atol": 1e-5, "max_abs": 1e-4, "metric_delta_pp_max": None, "mask_iou_min": None}
ARGMAX_GAP = 2e-4


def make_layer1_report(
    result: ComparisonResult,
    *,
    run_id: str,
    git_sha: str,
    model: str,
    variant: str,
    onnx_sha256: str,
    golden_set: Mapping[str, Any],
    fixture: bool = False,
) -> dict[str, Any]:
    """The layer-1 document (fp32, ONNX Runtime CPU) of a comparator result; `fixture: true` only for fixtures."""
    argmax = None
    if result.argmax_rows:
        argmax = {
            "output": "class_scores",
            "gap_threshold": ARGMAX_GAP,
            "rows": result.argmax_rows,
            "rows_small_gap": result.argmax_rows_small_gap,
            "agreement": result.argmax_agreement,
        }
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "git_sha": git_sha,
        "layer": 1,
        "model": model,
        "variant": variant,
        "precision": "fp32",
        "backend": "ort-cpu",
        "tensorrt_version": None,
        "onnx_sha256": onnx_sha256,
        "engine_sha256": None,
        "golden_set": dict(golden_set),
        "tolerances": dict(LAYER1_TOLERANCES),
        "max_abs_error": result.max_abs_error,
        "mismatch_fraction": result.mismatch_fraction,
        "argmax": argmax,
        "metric": None,
        "mask_iou": None,
        "verdict": "pass" if result.verdict == "pass" else "rejected",
    }
    if result.reason:
        report["reason"] = result.reason[:300]
    if fixture:
        report["fixture"] = True
    return report
