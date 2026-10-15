"""Tiles per frame and camera streams per GPU for the detector cells (FR-016-35, FR-016-38, P-016-07, P-016-12)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

TILE_PX = 640
OVERLAP_PX = 64
FRAME_W_PX = 3840
FRAME_H_PX = 2160
FPS = 10
RECALL_SCORE_MIN = 0.5
RECALL_IOU_MIN = 0.5


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def _axis(size: int, tile: int, overlap: int) -> int:
    return 1 if size <= tile else -(-(size - overlap) // (tile - overlap))


def n_tiles(width: int, height: int, *, tile: int = TILE_PX, overlap: int = OVERLAP_PX) -> int:
    """n_x x n_y with n = 1 when the side fits one tile, else ceil((side - overlap) / (tile - overlap))."""
    _positive_int(width, "width")
    _positive_int(height, "height")
    _positive_int(tile, "tile")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or overlap < 0 or tile <= overlap:
        raise ValueError(f"tile ({tile}) must be larger than overlap ({overlap}), which must be >= 0")
    return _axis(width, tile, overlap) * _axis(height, tile, overlap)


def camera_streams(
    tiles_per_s: float,
    *,
    width: int = FRAME_W_PX,
    height: int = FRAME_H_PX,
    tile: int = TILE_PX,
    overlap: int = OVERLAP_PX,
    fps: float = FPS,
) -> int:
    """floor(R / (n_tiles x f)) streams per GPU."""
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"fps must be a positive finite number, got {fps!r}")
    if not isinstance(tiles_per_s, (int, float)) or isinstance(tiles_per_s, bool) or not math.isfinite(tiles_per_s) or tiles_per_s < 0:
        raise ValueError(f"tiles_per_s must be a finite number >= 0, got {tiles_per_s!r}")
    tiles = n_tiles(width, height, tile=tile, overlap=overlap)
    return math.floor(tiles_per_s / (tiles * fps))


def camera_streams_report(
    throughput: Sequence[Mapping[str, Any]],
    recall: float,
    *,
    width: int = FRAME_W_PX,
    height: int = FRAME_H_PX,
    tile: int = TILE_PX,
    overlap: int = OVERLAP_PX,
    fps: float = FPS,
) -> dict[str, Any]:
    """The bench-record `camera_streams` object at the best batch of the throughput sweep."""
    if not throughput:
        raise ValueError("throughput sweep is empty")
    for entry in throughput:
        value = entry["samples_per_s"]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"tiles_per_s of batch {entry.get('size')} is not a finite number >= 0: {value!r}")
    best = max(throughput, key=lambda e: e["samples_per_s"])
    kwargs = {"width": width, "height": height, "tile": tile, "overlap": overlap, "fps": fps}
    return {
        "frame_w_px": width,
        "frame_h_px": height,
        "tile_px": tile,
        "overlap_px": overlap,
        "n_tiles": n_tiles(width, height, tile=tile, overlap=overlap),
        "fps": fps,
        "best_batch": best["size"],
        "tiles_per_s": best["samples_per_s"],
        "streams": camera_streams(best["samples_per_s"], **kwargs),
        "recall": recall,
        "recall_score_min": RECALL_SCORE_MIN,
        "recall_iou_min": RECALL_IOU_MIN,
    }
