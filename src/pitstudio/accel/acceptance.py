"""Engine acceptance on the bench records and the matrix wall time (SC-016-01, NFR-016-02).

Verdicts are recomputed from the numbers in each record; a stored `status` or `parity.verdict` is never trusted.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MATRIX_WALL_S_MAX = 8 * 3600.0
MATRIX_STAGE_PREFIXES = ("s62_accel", "s64_bench")
RTOL, ATOL = 1e-3, 1e-5
METRIC_DELTA_MAX_PP = 1.0
MASK_IOU_MIN = 0.99
NEEDS_REASON = ("rejected", "build-failed", "not_run")


@dataclass(frozen=True)
class EngineAcceptance:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class MatrixTime:
    wall_s: float
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _name(record: Mapping[str, Any]) -> str:
    return f"{record.get('model')} / {record.get('backend')} / {record.get('precision')} / {record.get('tensorrt_version')}"


def _pass_problems(record: Mapping[str, Any]) -> list[str]:
    name = _name(record)
    parity = record.get("parity")
    if not isinstance(parity, Mapping):
        return [f"{name}: pass without parity numbers (parity missing)"]
    problems = []
    if record.get("precision") == "fp32":
        if parity.get("rtol") != RTOL or parity.get("atol") != ATOL:
            problems.append(f"{name}: parity tolerances {parity.get('rtol')} / {parity.get('atol')} are not 1e-3 / 1e-5")
        if parity.get("mismatch_fraction") != 0:
            problems.append(f"{name}: parity mismatch fraction {parity.get('mismatch_fraction')} is not 0")
        if parity.get("max_abs_error") is None:
            problems.append(f"{name}: parity maximum error was not measured")
        if parity.get("tf32_cleared") is False:
            problems.append(f"{name}: parity measured without clearing TF32")
    else:
        delta = parity.get("metric_delta_pp")
        if not isinstance(delta, (int, float)) or not abs(delta) <= METRIC_DELTA_MAX_PP:
            problems.append(f"{name}: parity metric change {delta} pp is not within {METRIC_DELTA_MAX_PP:g} pp")
        iou = parity.get("mask_iou")
        if iou is not None and not iou >= MASK_IOU_MIN:
            problems.append(f"{name}: parity mask IoU {iou} is below {MASK_IOU_MIN}")
    if parity.get("verdict") != "pass":
        problems.append(f"{name}: status pass but the parity verdict is {parity.get('verdict')!r}")
    return problems


def engine_acceptance(
    records: Sequence[Mapping[str, Any]], expected_cells: Sequence[tuple[str, str, str, str | None]]
) -> EngineAcceptance:
    """No cell dropped, every `pass` backed by its numbers, every other status explained by a reason."""
    by_cell = {(r.get("model"), r.get("backend"), r.get("precision"), r.get("tensorrt_version")): r for r in records}
    problems: list[str] = []
    for cell in expected_cells:
        if cell not in by_cell:
            problems.append(f"{cell[0]} / {cell[1]} / {cell[2]} / {cell[3]}: cell missing from the records")
    for record in records:
        status = record.get("status")
        if status == "pass":
            problems.extend(_pass_problems(record))
        elif status in NEEDS_REASON and not record.get("reason"):
            problems.append(f"{_name(record)}: status {status} without a reason")
    return EngineAcceptance(problems)


def matrix_wall_time(run_manifest: Mapping[str, Any]) -> MatrixTime:
    """Sum of the wall time of the s62_accel and s64_bench stages; at most 8 h, every cell cached or not recorded."""
    total = 0.0
    problems: list[str] = []
    for stage in run_manifest.get("stages", []):
        key = str(stage.get("key", ""))
        if not key.startswith(MATRIX_STAGE_PREFIXES):
            continue
        wall = stage.get("wall_s")
        if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(wall) or wall < 0:
            problems.append(f"{key}: wall time {wall!r} is not a finite number >= 0")
        else:
            total += float(wall)
        if stage.get("cache") not in ("hit", "miss"):
            problems.append(f"{key}: cache state {stage.get('cache')!r} is not hit or miss")
    if total > MATRIX_WALL_S_MAX:
        problems.append(f"matrix wall time {total:.1f} s exceeds {MATRIX_WALL_S_MAX:.0f} s (8 h)")
    return MatrixTime(total, problems)
