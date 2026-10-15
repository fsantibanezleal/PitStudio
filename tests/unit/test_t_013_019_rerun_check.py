# ruff: noqa: E501, PT018, PT011
"""T-013-019: statistical re-run check (point count +/- 1 %, Chamfer <= 3 sigma, PSNR >= 40 dB).

Requirements: FR-013-34.

Oracle: analytical clouds whose symmetric mean Chamfer distance is known by construction (a unit lattice shifted by delta, whose
nearest neighbour of every point is its own shifted copy at distance delta, because every other lattice point is at least
1 - delta away), `scene_kit`-style brute force for random clouds, PSNR by hand (10 log10(255^2 / MSE)), and the thresholds of
`specs/000-foundation/thresholds.yaml` (`sensors.rerun_point_count_rel_max` 0.01, `sensors.rerun_chamfer_over_range_accuracy_max`
3, `sensors.rerun_psnr_db_min` 40). The symmetric mean Chamfer distance is the mean of the two directed mean nearest-neighbour
distances, 0.5 (mean_{a in A} min_b |a - b| + mean_{b in B} min_a |a - b|).

Expected API (package `pitstudio_rtx.rerun`, first-party code importable from `studio/rtx/src`; NumPy only):
- `rerun.chamfer(a, b)`: symmetric mean Chamfer distance of two (n, 3) float arrays (empty input raises `ValueError`).
- `rerun.psnr_db(a, b, peak=255.0)`: PSNR in dB of two equal-shape arrays (`math.inf` when identical; shape mismatch raises
  `ValueError`).
- `rerun.rerun_check(original, rerun, *, range_accuracy_m, thresholds=None) -> dict`: `original` and `rerun` are dicts with
  `lidar` (a list of per-frame dicts with `points`, an (n, 3) array of the valid returns) and `images` (a list of uint8 arrays).
  Frames and images are compared pairwise in order (different numbers raise `ValueError`). Returns `{"class": "statistical",
  "rerun_check": "pass" | "fail", "failing": None | {"measure": "point_count" | "chamfer" | "psnr", "index": int, "value":
  float}}`: `pass` only if every frame's valid point count differs by at most `rerun_point_count_rel_max` (relative to the
  original), every cloud's Chamfer distance is at most `rerun_chamfer_over_range_accuracy_max` x `range_accuracy_m`, and every
  image's PSNR is at least `rerun_psnr_db_min`; `failing` names the first failing measure. `thresholds` (default: read from
  `specs/000-foundation/thresholds.yaml`, section `sensors`) uses the same three key names without the `sensors.` prefix.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import rerun  # noqa: E402

SIGMA = 0.05  # range accuracy (m)


def _lattice(n: int = 8) -> np.ndarray:
    g = np.arange(n, dtype=np.float64)
    return np.stack(np.meshgrid(g, g, g, indexing="ij"), axis=-1).reshape(-1, 3)


def _frame(points: np.ndarray) -> dict:
    return {"points": points}


def _case(shift: float = 0.0, extra: int = 0, image_delta: int = 0):
    a = _lattice()
    b = a + np.array([shift, 0.0, 0.0])
    if extra:
        b = np.vstack([b, b[:extra] + 0.001])
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    return ({"lidar": [_frame(a)], "images": [img]}, {"lidar": [_frame(b)], "images": [img + np.uint8(image_delta)]})


@pytest.mark.req("FR-013-34")
def test_the_thresholds_in_the_repository_are_the_spec_values() -> None:
    doc = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))
    sensors = doc["sensors"]
    assert (
        sensors["rerun_point_count_rel_max"],
        sensors["rerun_chamfer_over_range_accuracy_max"],
        sensors["rerun_psnr_db_min"],
    ) == (0.01, 3, 40)


@pytest.mark.req("FR-013-34")
@pytest.mark.parametrize("delta", [0.0, 0.05, 0.1, 0.25])
def test_chamfer_of_a_shifted_lattice_is_the_shift(delta: float) -> None:
    a = _lattice()
    assert rerun.chamfer(a, a + np.array([delta, 0.0, 0.0])) == pytest.approx(delta, abs=1e-12)
    assert rerun.chamfer(a, a) == 0.0


@pytest.mark.req("FR-013-34")
def test_chamfer_matches_the_brute_force_reference_on_random_clouds() -> None:
    rng = np.random.default_rng(8)
    a, b = rng.uniform(0, 10, (300, 3)), rng.uniform(0, 10, (400, 3))
    assert rerun.chamfer(a, b) == pytest.approx(kit.chamfer_ref(a, b), rel=1e-9)
    assert rerun.chamfer(a, b) == pytest.approx(rerun.chamfer(b, a), rel=1e-12)  # symmetric


@pytest.mark.req("FR-013-34")
def test_psnr_by_hand() -> None:
    a = np.zeros((10, 10), dtype=np.uint8)
    b = a.copy()
    b[:, :5] = 3  # half the pixels differ by 3: MSE = 4.5
    assert rerun.psnr_db(a, b) == pytest.approx(10 * math.log10(255.0**2 / 4.5), abs=1e-9)  # 40.60 dB
    assert rerun.psnr_db(a, a) == math.inf
    assert rerun.psnr_db(a, a + np.uint8(1)) == pytest.approx(10 * math.log10(255.0**2), abs=1e-9)  # MSE 1: 48.13 dB


@pytest.mark.req("FR-013-34")
def test_a_matching_rerun_passes_and_is_statistical() -> None:
    original, again = _case(shift=0.1, image_delta=1)  # Chamfer 0.1 <= 3 x 0.05; PSNR 48.13 dB
    result = rerun.rerun_check(original, again, range_accuracy_m=SIGMA)
    assert result == {"class": "statistical", "rerun_check": "pass", "failing": None}


@pytest.mark.req("FR-013-34")
@pytest.mark.parametrize(("shift", "outcome"), [(0.149, "pass"), (0.151, "fail")])
def test_chamfer_boundary_is_three_range_accuracies(shift: float, outcome: str) -> None:
    original, again = _case(shift=shift)
    result = rerun.rerun_check(original, again, range_accuracy_m=SIGMA)
    assert result["rerun_check"] == outcome
    if outcome == "fail":
        assert result["failing"]["measure"] == "chamfer" and result["failing"]["index"] == 0
        assert result["failing"]["value"] == pytest.approx(shift, abs=1e-12)


@pytest.mark.req("FR-013-34")
@pytest.mark.parametrize(("extra", "outcome"), [(0, "pass"), (5, "pass"), (10, "fail")])
def test_point_count_boundary_is_one_percent(extra: int, outcome: str) -> None:
    """512 points; +5 is 0.98 % (pass), +10 is 1.95 % (fail)."""
    original, again = _case(extra=extra)
    result = rerun.rerun_check(original, again, range_accuracy_m=1.0)  # a loose Chamfer bound isolates the count rule
    assert result["rerun_check"] == outcome
    if outcome == "fail":
        assert result["failing"]["measure"] == "point_count" and result["failing"]["value"] == pytest.approx(10 / 512)


@pytest.mark.req("FR-013-34")
def test_the_count_difference_is_relative_to_the_original_exactly_at_one_percent() -> None:
    a = np.zeros((1000, 3))
    ok = rerun.rerun_check(
        {"lidar": [_frame(a)], "images": []},
        {"lidar": [_frame(np.zeros((1010, 3)))], "images": []},
        range_accuracy_m=1.0,
    )
    bad = rerun.rerun_check(
        {"lidar": [_frame(a)], "images": []},
        {"lidar": [_frame(np.zeros((1011, 3)))], "images": []},
        range_accuracy_m=1.0,
    )
    assert ok["rerun_check"] == "pass" and bad["rerun_check"] == "fail"


@pytest.mark.req("FR-013-34")
@pytest.mark.parametrize(("delta", "outcome"), [(1, "pass"), (3, "fail")])
def test_psnr_boundary_is_forty_db(delta: int, outcome: str) -> None:
    """A constant offset of 1 gives MSE 1 (48.13 dB: pass); an offset of 3 gives MSE 9 (38.59 dB: fail)."""
    original, again = _case(image_delta=delta)
    result = rerun.rerun_check(original, again, range_accuracy_m=SIGMA)
    assert result["rerun_check"] == outcome
    if outcome == "fail":
        assert result["failing"]["measure"] == "psnr"
        assert result["failing"]["value"] == pytest.approx(10 * math.log10(255.0**2 / 9.0), abs=1e-9)


@pytest.mark.req("FR-013-34")
def test_the_first_failing_measure_and_frame_are_named() -> None:
    a = _lattice()
    good, bad = _frame(a), _frame(a + np.array([0.5, 0.0, 0.0]))
    original = {"lidar": [good, good, good], "images": []}
    again = {"lidar": [good, bad, bad], "images": []}
    result = rerun.rerun_check(original, again, range_accuracy_m=SIGMA)
    assert (
        result["rerun_check"] == "fail"
        and result["failing"]["measure"] == "chamfer"
        and result["failing"]["index"] == 1
    )


@pytest.mark.req("FR-013-34")
def test_custom_thresholds_replace_the_repository_values() -> None:
    original, again = _case(shift=0.2, image_delta=3)  # fails with the defaults (Chamfer 0.2 > 0.15; PSNR 38.6 dB)
    assert rerun.rerun_check(original, again, range_accuracy_m=SIGMA)["rerun_check"] == "fail"
    loose = {"rerun_point_count_rel_max": 0.5, "rerun_chamfer_over_range_accuracy_max": 10, "rerun_psnr_db_min": 30}
    assert rerun.rerun_check(original, again, range_accuracy_m=SIGMA, thresholds=loose)["rerun_check"] == "pass"


@pytest.mark.req("FR-013-34")
def test_hostile_inputs_raise_value_error() -> None:
    a = _lattice()
    for bad in (np.zeros((0, 3)), np.array([[np.nan, 0.0, 0.0]])):
        with pytest.raises(ValueError):
            rerun.chamfer(a, bad)
    with pytest.raises(ValueError):
        rerun.psnr_db(np.zeros((4, 4), np.uint8), np.zeros((4, 5), np.uint8))
    with pytest.raises(ValueError):
        rerun.rerun_check({"lidar": [_frame(a)], "images": []}, {"lidar": [], "images": []}, range_accuracy_m=SIGMA)
    with pytest.raises(ValueError):
        rerun.rerun_check({"lidar": [], "images": []}, {"lidar": [], "images": []}, range_accuracy_m=0.0)
