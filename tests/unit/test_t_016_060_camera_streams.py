"""T-016-060: tile count and streams per GPU; hostile stream inputs (unit, hostile, property).

Requirements: FR-016-35, FR-016-38, P-016-07, P-016-12.

Spec: specs/016-export-acceleration/spec.md
- FR-016-35: camera streams per GPU for each detector cell = floor(R / (n_tiles x f)), with R the measured tiles per
  second at the best batch of the sweep, n_tiles = n_x n_y where n_x = 1 if W <= t else ceil((W - o) / (t - o))
  (likewise n_y with H), t = 640 px, o = 64 px, W x H = 3,840 x 2,160 px, f = 10 frames/s, together with the recall
  of that variant at score >= 0.5 and IoU >= 0.5 on the pit-family held-out set (spec 009);
- FR-016-38: a non-positive frame size, a tile size <= the overlap, a non-positive frame rate, or a non-finite or
  negative throughput raises `ValueError` naming the argument;
- P-016-07: n_tiles(W, H) = n_tiles(H, W), is non-decreasing in W and H, equals 1 for W, H <= t, and equals 28 for
  3,840 x 2,160; P-016-12: streams are non-increasing in f and in the frame size and non-decreasing in R (R in
  [0, 10^5] tiles/s, f in [1, 60] frames/s).
plan.md test strategy rows FR-016-35 (R = 2,800 tiles/s, 28 tiles, 10 frames/s -> 10 streams), FR-016-38 (W = 0, t = o =
64, f = 0, R = NaN -> `ValueError`), P-016-07 / P-016-12.

Oracles:
- hand calculation: n_x = ceil((3,840 - 64) / 576) = ceil(6.555...) = 7 and n_y = ceil((2,160 - 64) / 576) =
  ceil(3.638...) = 4, so 28 tiles; floor(2,800 / (28 x 10)) = 10; the boundary frames 640 / 641 / 1,216 / 1,217 px by
  hand (1, 2, 2, 3 tiles per axis);
- an independent integer expression of the ceiling written in the test (`-(-a // b)`);
- the spec's own bench-record example `contracts/examples/bench-record.valid.json`: its `camera_streams` object (best
  batch 64 at 666.6667 samples/s on 28 tiles at 10 frames/s: floor(2.38) = 2 streams, recall 0.83) is the expected
  output of `camera_streams_report`.

Expected public API (module `pitstudio.accel.streams`, root environment, pure Python):
    TILE_PX = 640; OVERLAP_PX = 64; FRAME_W_PX = 3840; FRAME_H_PX = 2160; FPS = 10
    n_tiles(width: int, height: int, *, tile: int = 640, overlap: int = 64) -> int
    camera_streams(tiles_per_s: float, *, width: int = 3840, height: int = 2160, tile: int = 640, overlap: int = 64,
                   fps: float = 10) -> int
        floor(tiles_per_s / (n_tiles * fps)); raises ValueError whose message contains the argument name `width`,
        `height`, `tile`, `fps` or `tiles_per_s` for the FR-016-38 conditions (a tile size <= overlap names `tile`).
    camera_streams_report(throughput: Sequence[Mapping], recall: float, *, ...same keywords...) -> dict
        the bench-record `camera_streams` object: frame_w_px, frame_h_px, tile_px, overlap_px, n_tiles, fps,
        best_batch (the `size` of the throughput entry with the largest `samples_per_s`), tiles_per_s (that value),
        streams, recall, recall_score_min 0.5, recall_iou_min 0.5; ValueError for an empty throughput list.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.accel.streams import camera_streams, camera_streams_report, n_tiles

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "016-export-acceleration" / "contracts" / "examples"


def _axis(size: int, tile: int = 640, overlap: int = 64) -> int:
    """Independent integer expression of n_x: 1 if size <= tile else ceil((size - overlap) / (tile - overlap))."""
    return 1 if size <= tile else -(-(size - overlap) // (tile - overlap))


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-35
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-35")
def test_a_4k_frame_needs_28_tiles_by_hand() -> None:
    assert _axis(3840) == 7
    assert _axis(2160) == 4
    assert n_tiles(3840, 2160) == 28


@pytest.mark.req("FR-016-35")
@pytest.mark.parametrize(("size", "per_axis"), [(1, 1), (640, 1), (641, 2), (1216, 2), (1217, 3), (1792, 3), (1793, 4)])
def test_tiles_per_axis_at_the_boundaries_by_hand(size: int, per_axis: int) -> None:
    # 576 = 640 - 64 is the stride: 1,216 = 64 + 2 x 576 is exactly two tiles, one more pixel needs a third
    assert n_tiles(size, 1) == per_axis
    assert n_tiles(1, size) == per_axis
    assert n_tiles(size, size) == per_axis * per_axis


@pytest.mark.req("FR-016-35")
def test_2800_tiles_per_second_on_28_tiles_at_10_fps_is_10_streams() -> None:
    assert camera_streams(2800.0) == 10
    assert camera_streams(2799.999) == 9  # the floor
    assert camera_streams(279.9) == 0
    assert camera_streams(0.0) == 0
    assert camera_streams(2800.0, fps=20) == 5


@pytest.mark.req("FR-016-35")
def test_other_frame_sizes_and_tile_settings_by_hand() -> None:
    # 1,920 x 1,080: n_x = ceil(1856 / 576) = 4, n_y = ceil(1016 / 576) = 2 -> 8 tiles; 800 / (8 x 10) = 10
    assert n_tiles(1920, 1080) == 8
    assert camera_streams(800.0, width=1920, height=1080) == 10
    # tile 512, overlap 0 on 1,024 x 512: 2 x 1 tiles
    assert n_tiles(1024, 512, tile=512, overlap=0) == 2


@pytest.mark.req("FR-016-35")
def test_the_report_for_the_spec_example_throughput_is_the_example_camera_streams_object() -> None:
    record = json.loads((EX / "bench-record.valid.json").read_text(encoding="utf-8"))
    report = camera_streams_report(record["throughput"], record["camera_streams"]["recall"])
    assert report == record["camera_streams"]
    assert report["best_batch"] == 64
    assert report["streams"] == math.floor(666.6667 / 280)


@pytest.mark.req("FR-016-35")
def test_the_best_batch_is_the_one_with_the_largest_throughput_not_the_largest_batch() -> None:
    throughput = [
        {"sweep": "batch", "size": 1, "iterations": 100, "elapsed_s": 1.0, "samples_per_s": 100.0},
        {"sweep": "batch", "size": 16, "iterations": 100, "elapsed_s": 1.0, "samples_per_s": 5600.0},
        {"sweep": "batch", "size": 64, "iterations": 100, "elapsed_s": 1.0, "samples_per_s": 5000.0},
    ]
    report = camera_streams_report(throughput, 0.9)
    assert (report["best_batch"], report["tiles_per_s"], report["streams"]) == (16, 5600.0, 20)
    assert report["recall"] == 0.9
    assert (report["recall_score_min"], report["recall_iou_min"]) == (0.5, 0.5)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-38
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-38")
@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"width": 0}, "width"),
        ({"width": -3840}, "width"),
        ({"height": 0}, "height"),
        ({"height": -1}, "height"),
        ({"tile": 64, "overlap": 64}, "tile"),
        ({"tile": 32, "overlap": 64}, "tile"),
        ({"fps": 0}, "fps"),
        ({"fps": -10}, "fps"),
        ({"fps": float("nan")}, "fps"),
    ],
)
def test_hostile_stream_arguments_raise_value_error_naming_the_argument(kwargs: dict, name: str) -> None:
    with pytest.raises(ValueError, match=name):
        camera_streams(2800.0, **kwargs)


@pytest.mark.req("FR-016-38")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1.0])
def test_a_non_finite_or_negative_throughput_raises_value_error_naming_it(bad: float) -> None:
    with pytest.raises(ValueError, match="tiles_per_s"):
        camera_streams(bad)


@pytest.mark.req("FR-016-38")
def test_n_tiles_has_the_same_guards() -> None:
    with pytest.raises(ValueError, match="width"):
        n_tiles(0, 2160)
    with pytest.raises(ValueError, match="height"):
        n_tiles(3840, -1)
    with pytest.raises(ValueError, match="tile"):
        n_tiles(3840, 2160, tile=64, overlap=64)


@pytest.mark.req("FR-016-38")
def test_the_report_refuses_an_empty_or_non_finite_throughput() -> None:
    with pytest.raises(ValueError, match=r"."):
        camera_streams_report([], 0.8)
    with pytest.raises(ValueError, match="tiles_per_s"):
        camera_streams_report(
            [{"sweep": "batch", "size": 1, "iterations": 1, "elapsed_s": 1.0, "samples_per_s": float("nan")}], 0.8
        )


# ----------------------------------------------------------------------------------------------------------------------
# P-016-07 and P-016-12
# ----------------------------------------------------------------------------------------------------------------------

dim = st.integers(min_value=1, max_value=16_384)


@pytest.mark.req("P-016-07")
@settings(max_examples=200, deadline=None)
@given(w=dim, h=dim)
def test_n_tiles_is_symmetric_and_matches_the_independent_formula(w, h):
    assert n_tiles(w, h) == n_tiles(h, w) == _axis(w) * _axis(h)


@pytest.mark.req("P-016-07")
@settings(max_examples=200, deadline=None)
@given(w=dim, h=dim, dw=st.integers(0, 4000), dh=st.integers(0, 4000))
def test_n_tiles_is_non_decreasing_in_both_dimensions(w, h, dw, dh):
    assert n_tiles(w + dw, h + dh) >= n_tiles(w, h)


@pytest.mark.req("P-016-07")
@settings(max_examples=200, deadline=None)
@given(w=st.integers(1, 640), h=st.integers(1, 640))
def test_frames_that_fit_one_tile_need_exactly_one(w, h):
    assert n_tiles(w, h) == 1


@pytest.mark.req("P-016-07")
def test_the_4k_frame_needs_28_tiles_and_swapped_28_too() -> None:
    assert n_tiles(3840, 2160) == 28 == n_tiles(2160, 3840)


@pytest.mark.req("P-016-12")
@settings(max_examples=200, deadline=None)
@given(
    r=st.floats(0, 1e5),
    f=st.floats(1, 60),
    df=st.floats(0, 60),
    dr=st.floats(0, 1e5),
    w=st.integers(641, 8000),
    h=st.integers(641, 8000),
    dw=st.integers(0, 3000),
    dh=st.integers(0, 3000),
)
def test_streams_are_non_increasing_in_fps_and_frame_size_and_non_decreasing_in_throughput(r, f, df, dr, w, h, dw, dh):
    base = camera_streams(r, width=w, height=h, fps=f)
    assert camera_streams(r, width=w, height=h, fps=f + df) <= base
    assert camera_streams(r, width=w + dw, height=h + dh, fps=f) <= base
    assert camera_streams(r + dr, width=w, height=h, fps=f) >= base
    assert base >= 0
    assert abs(base - math.floor(r / (n_tiles(w, h) * f))) <= 1  # the closed form, up to the rounding of the division
