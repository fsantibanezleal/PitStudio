# ruff: noqa: PT018
"""T-009-016 (fix): the image-quality measures and the gate of the SDG exposure calibration (FR-009-02, FR-009-05).

Requirements: FR-009-02, FR-009-05, FR-009-08.

Job 89 of 2026-11-22 wrote frames whose exposure was poor (median rgb std 6.4 in the structured arm, 138 of 2,415 frames
flat). The calibration is judged by numbers: flat and clipped frames, rgb std quantiles, annotated frames, history
independence and the transmittance of the fog. These pure functions are the measures; the probes and the gate use them.

Oracles (by hand): Rec. 709 luminance of pure red, green and blue (0.2126, 0.7152, 0.0722 times 255); the Beer-Lambert
transmittance exp(-sigma * d) for sigma = 3 per km at 300 m (exp(-0.9) = 0.4066); quantile midpoints of a sorted list.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import exposure_qa as qa  # noqa: E402


@pytest.mark.req("FR-009-02")
def test_luminance_uses_the_rec_709_weights_on_the_8_bit_values() -> None:
    img = np.zeros((1, 3, 3), np.uint8)
    img[0, 0, 0], img[0, 1, 1], img[0, 2, 2] = 255, 255, 255
    assert qa.luminance(img).ravel().tolist() == pytest.approx([0.2126 * 255, 0.7152 * 255, 0.0722 * 255])


@pytest.mark.req("FR-009-02")
def test_clipped_fraction_counts_luminance_at_most_2_or_at_least_253() -> None:
    img = np.full((10, 10, 3), 128, np.uint8)
    img[:2] = 2  # 20 pixels at the black limit
    img[2:3] = 253  # 10 pixels at the white limit
    img[3:4] = 3  # just above the black limit
    img[4:5] = 252  # just below the white limit
    assert qa.clipped_fraction(img) == pytest.approx(0.30)


@pytest.mark.req("FR-009-05")
def test_a_frame_is_haze_limited_when_the_transmittance_at_the_median_depth_is_below_a_tenth() -> None:
    # exp(-sigma * d) < 0.1  <=>  sigma * d > ln 10 = 2.3026
    assert qa.haze_limited(23.0, 100.2) is True  # 23 per km at 100.2 m: 2.3046
    assert qa.haze_limited(23.0, 100.0) is False  # 2.3000
    assert qa.haze_limited(0.0, 1.0e6) is False
    assert qa.transmittance(3.0, 300.0) == pytest.approx(math.exp(-0.9))


@pytest.mark.req("FR-009-05")
def test_the_median_finite_depth_ignores_infinite_pixels() -> None:
    depth = np.array([[10.0, 20.0, np.inf], [30.0, np.inf, 40.0]], np.float32)
    assert qa.median_finite_depth(depth) == 25.0
    assert math.isnan(qa.median_finite_depth(np.full((2, 2), np.inf, np.float32)))


@pytest.mark.req("FR-009-05")
def test_the_transmittance_measured_from_colours_inverts_the_blend() -> None:
    fog, clear = np.array([140.0, 125.0, 102.0]), np.array([60.0, 90.0, 40.0])
    for t in (0.05, 0.4066, 0.9):
        rendered = t * clear + (1.0 - t) * fog
        assert qa.transmittance_from_colours(rendered, fog, clear) == pytest.approx(t)
    with pytest.raises(ValueError, match="differ"):
        qa.transmittance_from_colours(fog, fog, fog)


@pytest.mark.req("FR-009-02")
def test_quantile_stratified_picks_the_midpoint_quantiles_of_the_sorted_values() -> None:
    values = list(range(100))
    assert qa.stratified_indices(values, 4) == [12, 37, 62, 87]  # quantiles 1/8, 3/8, 5/8, 7/8 of 100 values
    assert qa.stratified_indices(values, 1) == [50]
    with pytest.raises(ValueError, match="only 3"):
        qa.stratified_indices([1, 2, 3], 4)


def _arm(n: int, a: str, b: str, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    return [{"record_id": f"r{i}", "dr": {a: float(rng.uniform(0, 1)), b: float(rng.uniform(0, 1))}} for i in range(n)]


@pytest.mark.req("FR-009-02")
def test_the_gate_sample_spreads_over_both_ranges_without_repeats() -> None:
    rows = _arm(5000, "x", "y", 1)
    chosen = qa.stratified_sample(rows, "x", "y", n_bins=6, per_bin=8)
    assert len(chosen) == 48 and len({r["record_id"] for r in chosen}) == 48
    xs = sorted(r["dr"]["x"] for r in chosen)
    ys = sorted(r["dr"]["y"] for r in chosen)
    for values in (xs, ys):  # every sixth of the range is represented
        counts, _ = np.histogram(values, bins=6, range=(0, 1))
        assert counts.min() >= 4
    assert xs[0] < 0.1 and xs[-1] > 0.9 and ys[0] < 0.1 and ys[-1] > 0.9


def _frames() -> list[dict]:
    base = {"rgb_std": 40.0, "clipped_fraction": 0.0, "annotations": 2, "haze_limited": False}
    return [dict(base) for _ in range(20)]


@pytest.mark.req("FR-009-02")
def test_the_gate_passes_good_frames_and_reports_every_threshold() -> None:
    summary = qa.evaluate_gate(_frames())
    assert summary["passed"] is True
    for key in ("flat_not_haze", "clipped_over_25pct", "rgb_std_median", "rgb_std_p10", "annotated", "haze_limited"):
        assert key in summary["thresholds"]
    assert summary["thresholds"]["flat_not_haze"] == {"value": 0, "limit": 0, "passed": True}


@pytest.mark.req("FR-009-02")
def test_a_flat_frame_that_is_not_haze_limited_fails_the_gate_and_a_haze_limited_one_does_not() -> None:
    frames = _frames()
    frames[0] = {**frames[0], "rgb_std": 0.2, "haze_limited": False}
    assert qa.evaluate_gate(frames)["thresholds"]["flat_not_haze"]["passed"] is False
    frames[0] = {**frames[0], "haze_limited": True}
    summary = qa.evaluate_gate(frames)
    assert summary["thresholds"]["flat_not_haze"]["passed"] is True
    assert summary["thresholds"]["haze_limited"]["value"] == 1  # counted apart, never silently dropped


@pytest.mark.req("FR-009-02")
def test_clipped_frames_over_five_percent_fail_and_exactly_five_percent_pass() -> None:
    frames = _frames()
    frames[0]["clipped_fraction"] = 0.26  # 1 of 20 frames = 5 percent: passes
    assert qa.evaluate_gate(frames)["thresholds"]["clipped_over_25pct"]["passed"] is True
    frames[1]["clipped_fraction"] = 0.30  # 2 of 20 = 10 percent
    assert qa.evaluate_gate(frames)["thresholds"]["clipped_over_25pct"]["passed"] is False
    assert qa.evaluate_gate(frames)["passed"] is False


@pytest.mark.req("FR-009-02")
def test_the_rgb_std_quantiles_and_annotation_share_are_judged_on_the_frames_that_are_not_haze_limited() -> None:
    frames = _frames()
    for i in range(3):  # 3 of 20 frames at std 5 (15 percent): the 10th percentile falls to 5
        frames[i]["rgb_std"] = 5.0
    summary = qa.evaluate_gate(frames)
    assert summary["thresholds"]["rgb_std_p10"]["passed"] is False
    assert summary["thresholds"]["rgb_std_median"]["passed"] is True
    frames = _frames()
    for i in range(5):
        frames[i]["annotations"] = 0  # 15 of 20 = 75 percent annotated, below 78
    assert qa.evaluate_gate(frames)["thresholds"]["annotated"]["passed"] is False
    for i in range(4):
        frames[i]["annotations"] = 0
    frames[4]["annotations"] = 1  # 16 of 20 = 80 percent
    assert qa.evaluate_gate(frames)["thresholds"]["annotated"]["passed"] is True


@pytest.mark.req("FR-009-02")
def test_history_independence_needs_both_the_mean_and_the_std_within_two_levels() -> None:
    same = {"mean": [100.0, 101.9], "std": [30.0, 31.9]}
    assert qa.history_independent(same["mean"], same["std"]) is True
    assert qa.history_independent([100.0, 102.1], [30.0, 30.0]) is False
    assert qa.history_independent([100.0, 100.0], [30.0, 32.1]) is False
