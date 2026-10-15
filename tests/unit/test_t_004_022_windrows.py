# ruff: noqa: PT018
"""T-004-022: windrows at or above the mid-axle height of the largest haul unit (30 CFR 56.9300(b)).

Requirements: FR-004-18.

Oracle: the regulation text as the rule ("Berms or guardrails shall be at least mid-axle height of the largest
self-propelled mobile equipment which usually travels the roadway", 30 CFR 56.9300(b), Cornell LII copy, spec section 7)
and the mid-axle height declared in the test's asset list; windrow placement is checked geometrically with shapely.

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.windrows.windrow_requirement(assets, fleet, windrow_height_m)` -> object with `height_m` (the windrow
  height), `mid_axle_height_m` (the mid-axle height of the largest haul unit: among the fleet's `haul_truck` assets
  the one with the greatest `mass_kg`) and `governing_asset` (its id). `assets` and `fleet` are the SceneSpec lists.
- `design.windrows.place_windrows(benches, ramp, *, height_m, ramp_width_m)` -> list of `Windrow` with `kind`
  (`"berm"` or `"ramp"`), `bench_index` (the bench whose berm it stands on; None for a ramp windrow), `line`
  (shapely `LineString`, site frame) and `height_m`. One or more berm windrows stand on the edge of every berm (the
  berm below bench k lies between `benches[k].toe` and `benches[k + 1].crest`; the floor bench has no berm) and their
  total length is at least half the berm's edge length; ramp windrows stand on the outer edge of the ramp, at least
  `ramp_width_m / 2` from its centreline, and run along at least 80 % of the ramp.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import design  # noqa: E402

ASSETS = [
    {"id": "haul-truck-220t", "class_label": "haul_truck", "mass_kg": 162000.0, "mid_axle_height_m": 1.6},
    {"id": "haul-truck-90t", "class_label": "haul_truck", "mass_kg": 70000.0, "mid_axle_height_m": 1.3},
    {"id": "water-truck", "class_label": "water_truck", "mass_kg": 60000.0, "mid_axle_height_m": 1.1},
    {"id": "pickup", "class_label": "light_vehicle", "mass_kg": 3000.0, "mid_axle_height_m": 0.35},
    {"id": "big-shovel", "class_label": "shovel", "mass_kg": 900000.0},  # not a roadway vehicle, no mid-axle height
]
FLEET = [{"asset": a["id"], "count": 2} for a in ASSETS]


def _pit():
    benches = design.benches.generate_benches(
        kit.regular_polygon(360, 300.0),
        bench_height_m=15.0,
        face_angle_deg=70.0,
        berm_width_m=10.0,
        rim_z_m=0.0,
        floor_z_m=-60.0,
    )
    ramp = design.ramp.generate_ramp(
        benches, ramp_grade_pct=8.0, ramp_width_m=30.0, rim_z_m=0.0, floor_z_m=-60.0, sample_spacing_m=1.0
    )
    return benches, ramp


@pytest.mark.req("FR-004-18")
def test_both_heights_and_the_governing_asset_are_recorded() -> None:
    req = design.windrows.windrow_requirement(ASSETS, FLEET, 2.5)
    assert (req.height_m, req.mid_axle_height_m, req.governing_asset) == (2.5, 1.6, "haul-truck-220t")
    assert req.height_m >= req.mid_axle_height_m  # 30 CFR 56.9300(b): at least mid-axle height


@pytest.mark.req("FR-004-18")
def test_the_largest_haul_unit_governs_not_the_tallest_or_the_heaviest_machine() -> None:
    assets = [
        {"id": "small", "class_label": "haul_truck", "mass_kg": 100000.0, "mid_axle_height_m": 1.4},
        {"id": "huge", "class_label": "haul_truck", "mass_kg": 360000.0, "mid_axle_height_m": 1.9},
        {"id": "loader", "class_label": "wheel_loader", "mass_kg": 500000.0, "mid_axle_height_m": 2.4},
    ]
    fleet = [{"asset": "small", "count": 1}, {"asset": "huge", "count": 1}, {"asset": "loader", "count": 1}]
    req = design.windrows.windrow_requirement(assets, fleet, 3.0)
    assert (req.mid_axle_height_m, req.governing_asset) == (1.9, "huge")


@pytest.mark.req("FR-004-18")
def test_every_berm_has_windrows_on_its_edge_at_the_required_height() -> None:
    benches, ramp = _pit()
    height = 2.5
    wr = design.windrows.place_windrows(benches, ramp, height_m=height, ramp_width_m=30.0)
    assert wr and all(w.height_m >= 1.6 for w in wr) and all(w.height_m == pytest.approx(height) for w in wr)
    for k in range(len(benches) - 1):  # the floor bench (last) has no berm
        band = benches[k].toe.difference(benches[k + 1].crest)
        mine = [w for w in wr if w.kind == "berm" and w.bench_index == k]
        assert mine, f"no windrow on the berm below bench {k}"
        for w in mine:
            assert band.buffer(1e-6).contains(w.line)  # inside the berm band
            assert w.line.distance(band.boundary) <= 1e-6  # on an edge of the berm
        edge_length = min(benches[k].toe.length, benches[k + 1].crest.length)
        assert sum(w.line.length for w in mine) >= 0.5 * edge_length
    assert not [w for w in wr if w.kind == "berm" and w.bench_index == len(benches) - 1]


@pytest.mark.req("FR-004-18")
def test_the_ramp_has_windrows_on_its_outer_edge() -> None:
    from shapely.geometry import Point

    benches, ramp = _pit()
    wr = [w for w in design.windrows.place_windrows(benches, ramp, height_m=2.0, ramp_width_m=30.0) if w.kind == "ramp"]
    assert wr and all(w.bench_index is None and w.height_m >= 1.6 for w in wr)
    c = np.asarray(ramp.centreline)
    run = np.hypot(*np.diff(c[:, :2], axis=0).T).sum()
    assert sum(w.line.length for w in wr) >= 0.8 * run
    centre = np.asarray(ramp.centreline)[:, :2]
    for w in wr:
        for x, y in list(w.line.coords)[:: max(1, len(w.line.coords) // 50)]:
            nearest = float(np.min(np.hypot(centre[:, 0] - x, centre[:, 1] - y)))
            assert nearest >= 30.0 / 2 - 1e-6, Point(x, y)  # not on the drivable surface
