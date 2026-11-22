"""The gate of the carved SDG frames (sdg-geometry-2026-11-22): `exposure_qa` thresholds, annotated share and geometry.

Pure NumPy, no Isaac Sim. The exposure thresholds are those of `exposure_qa.evaluate_gate` (flat frames, clipped frames,
rgb std quantiles, haze-limited frames listed apart); the annotated share rises to 85 percent because the table now
constructs visibility (FR-009-54); two geometry checks are added:

- no frame has a median finite depth below `MIN_MEDIAN_DEPTH_M` (the table's `VIEW_NEAR_M`); a frame with no finite depth
  counts as too near, it shows no ground;
- at least `AGREEMENT_SHARE` of the objects the table marks visible have at least `MIN_INSTANCE_PX` visible pixels in the
  render (renderer and table agree on what is seen).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from pitstudio_isaac.sdg import exposure_qa
from pitstudio_isaac.sdg.scene_render import MIN_INSTANCE_PX

ANNOTATED_SHARE = 0.85
MIN_MEDIAN_DEPTH_M = 10.0
AGREEMENT_SHARE = 0.90


def evaluate_gate(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Every threshold of the gate on frame measures (`exposure_qa.evaluate_gate` keys plus `median_depth_m`, `objects`)."""
    base = exposure_qa.evaluate_gate(frames)
    thresholds = dict(base["thresholds"])
    n = len(frames)
    annotated = sum(1 for f in frames if int(f["annotations"]) > 0)
    thresholds["annotated"] = {
        "value": annotated / n,
        "limit": ANNOTATED_SHARE,
        "passed": annotated / n >= ANNOTATED_SHARE,
    }
    near = sum(
        1 for f in frames if math.isnan(float(f["median_depth_m"])) or float(f["median_depth_m"]) < MIN_MEDIAN_DEPTH_M
    )
    thresholds["near_median_depth"] = {"value": near, "limit": 0, "passed": near == 0}
    seen = [o for f in frames for o in f["objects"] if o["table_visible"]]
    agree = sum(1 for o in seen if int(o["visible_px"]) >= MIN_INSTANCE_PX)
    share = agree / len(seen) if seen else 1.0
    thresholds["table_render_agreement"] = {
        "value": share,
        "limit": AGREEMENT_SHARE,
        "objects": len(seen),
        "passed": share >= AGREEMENT_SHARE,
    }
    return {"frames": n, "thresholds": thresholds, "passed": all(t["passed"] for t in thresholds.values())}
