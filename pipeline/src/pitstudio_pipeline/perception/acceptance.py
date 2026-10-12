"""Pre-registered acceptance rows of the detection evaluation report (FR-009-24, SC-009-01 ... SC-009-06).

Each criterion pins its model, precision, statistic and threshold (the schema pins them too). A class with fewer than
`min_support` test instances in the statistic's support makes the criterion "not evaluable (insufficient support)"
with the
class and its count, instead of pass or fail.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

NOT_EVALUABLE = "not evaluable (insufficient support)"
CORRUPTIONS = ("dust", "night", "rain")

# criterion -> (model, precision, statistic, threshold, direction); direction "min": value >= threshold, "max": value
# <= threshold
_CRITERIA: dict[str, tuple[str | None, str | None, str, float, str]] = {
    "SC-009-01": ("d-fine-s", "fp32", "map50", 0.8, "min"),
    "SC-009-02": ("d-fine-n", "fp32", "map50", 0.7, "min"),
    "SC-009-05": ("rf-detr-seg-n", "fp32", "mask_ap50", 0.7, "min"),
    "SC-009-06": ("rf-detr-seg-n", "fp16", "abs_delta_mask_ap50_pp", 1.0, "max"),
    "SC-009-03": (None, None, "delta_rel_pct", 10.0, "max"),
}
_ROBUSTNESS_MODELS = ("d-fine-n", "d-fine-s")
_PRECISIONS = ("fp32", "fp16", "int8")


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def not_run_row(
    criterion: str,
    reason: str,
    *,
    model: str | None = None,
    precision: str | None = None,
    corruption: str | None = None,
    severity: int | None = None,
) -> dict[str, Any]:
    """A row of a criterion that was not run: pinned statistic and threshold, verdict `not run`, and the reason."""
    if criterion not in _CRITERIA:
        raise ValueError(f"criterion must be one of {sorted(_CRITERIA)}, got {criterion!r}")
    pinned_model, pinned_precision, statistic, threshold, _ = _CRITERIA[criterion]
    row: dict[str, Any] = {
        "criterion": criterion,
        "model": model if criterion == "SC-009-03" else pinned_model,
        "precision": precision if criterion == "SC-009-03" else pinned_precision,
        "statistic": statistic,
        "threshold": threshold,
        "verdict": "not run",
        "reason": reason[:300],
    }
    if criterion == "SC-009-03":
        row["corruption"], row["severity"] = corruption, severity
    return row


def acceptance_row(
    criterion: str,
    *,
    value: float | None,
    support: Sequence[tuple[str, str, int]],
    model: str | None = None,
    precision: str | None = None,
    corruption: str | None = None,
    severity: int | None = None,
    min_support: int = 100,
) -> dict[str, Any]:
    """One row of the `acceptance` array of DC-009-05; ValueError names the offending argument."""
    if criterion not in _CRITERIA:
        raise ValueError(f"criterion must be one of {sorted(_CRITERIA)}, got {criterion!r}")
    if not isinstance(min_support, int) or isinstance(min_support, bool) or min_support < 1:
        raise ValueError(f"min_support must be an int >= 1, got {min_support!r}")
    pinned_model, pinned_precision, statistic, threshold, direction = _CRITERIA[criterion]
    if criterion == "SC-009-03":
        if model not in _ROBUSTNESS_MODELS:
            raise ValueError(f"model must be one of {_ROBUSTNESS_MODELS} for {criterion}, got {model!r}")
        if precision not in _PRECISIONS:
            raise ValueError(f"precision must be one of {_PRECISIONS} for {criterion}, got {precision!r}")
        if corruption not in CORRUPTIONS:
            raise ValueError(f"corruption must be one of {CORRUPTIONS} for {criterion}, got {corruption!r}")
        if severity not in (1, 2) or isinstance(severity, bool):
            raise ValueError(f"severity must be 1 or 2 for {criterion}, got {severity!r}")
        row_model, row_precision = model, precision
    else:
        if model not in (None, pinned_model):
            raise ValueError(f"model of {criterion} is {pinned_model!r}, got {model!r}")
        if precision not in (None, pinned_precision):
            raise ValueError(f"precision of {criterion} is {pinned_precision!r}, got {precision!r}")
        if corruption is not None or severity is not None:
            raise ValueError(
                f"corruption and severity belong to SC-009-03 only, got {corruption!r} / {severity!r} for {criterion}"
            )
        row_model, row_precision = pinned_model, pinned_precision
    row: dict[str, Any] = {
        "criterion": criterion,
        "model": row_model,
        "precision": row_precision,
        "statistic": statistic,
        "threshold": threshold,
    }
    if criterion == "SC-009-03":
        row["corruption"], row["severity"] = corruption, severity
    shortfalls = [
        {"family": family, "class": cls, "count": int(count)}
        for family, cls, count in support
        if 1 <= int(count) < min_support
    ]
    if shortfalls:
        row["verdict"] = NOT_EVALUABLE
        row["insufficient_support"] = shortfalls
        return row
    if not _is_number(value) or not math.isfinite(value):  # type: ignore[arg-type]
        raise ValueError(f"value must be a finite number when no class is short of support, got {value!r}")
    assert value is not None
    row["value"] = float(value)
    ok = value >= threshold if direction == "min" else value <= threshold
    row["verdict"] = "pass" if ok else "fail"
    return row
