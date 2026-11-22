"""Per-frame VMAF scores: mean, 5th percentile and the libvmaf JSON log reader (FR-006-02, P-006-05)."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence


# ---------------------------------------------------------------------------------------------------------------------
# aggregation of per-frame scores
# ---------------------------------------------------------------------------------------------------------------------
def aggregate_vmaf(scores: Sequence[float]) -> tuple[float, float]:
    """Mean (exact sum, order independent) and 5th percentile (Hyndman-Fan type 7) of per-frame scores."""
    values = [float(s) for s in scores]
    if not values:
        raise ValueError("no VMAF scores")
    if not all(math.isfinite(v) for v in values):
        raise ValueError("a VMAF score is not finite")
    mean = math.fsum(values) / len(values)
    ordered = sorted(values)
    h = (len(ordered) - 1) * 0.05
    j = math.floor(h)
    p5 = ordered[-1] if j + 1 >= len(ordered) else ordered[j] + (h - j) * (ordered[j + 1] - ordered[j])
    return mean, p5


def parse_vmaf_log(text: str, *, expected_frames: int | None = None) -> list[float]:
    """The per-frame scores `frames[*].metrics.vmaf` of a libvmaf JSON log, in frameNum order."""
    doc = json.loads(text)
    frames = doc.get("frames") if isinstance(doc, dict) else None
    if not isinstance(frames, list) or not frames:
        raise ValueError("the VMAF log has no frames")
    by_index: dict[int, float] = {}
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError("a VMAF log frame is not an object")
        index, metrics = frame.get("frameNum"), frame.get("metrics")
        score = metrics.get("vmaf") if isinstance(metrics, dict) else None
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("a VMAF log frame has no valid frameNum")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError(f"frame {index} has no finite metrics.vmaf")
        if index in by_index:
            raise ValueError(f"duplicate frameNum {index}")
        by_index[index] = float(score)
    if sorted(by_index) != list(range(len(by_index))):
        raise ValueError("the VMAF log is missing a frame")
    if expected_frames is not None and len(by_index) != expected_frames:
        raise ValueError(f"the VMAF log has {len(by_index)} frames, the source has {expected_frames}")
    return [by_index[i] for i in range(len(by_index))]
