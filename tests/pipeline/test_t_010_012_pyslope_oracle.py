"""T-010-012: Bishop against the pySlope 1.4.0 oracle on the shared planar bench cases.

Requirement: SC-010-05.
Spec: specs/010-slope/spec.md section 5 (SC-010-05), plan.md "Test strategy" (SC-010-05 row) and "Dependencies"
(pySlope 1.4.0, MIT, oracle-only: it is never a runtime dependency; T-010-002 provides the environment).

Expected API (module `pitstudio.slope.lem`, shared with T-010-010): `bishop_fos(section, circle, slices=...)`,
`analyse_section(section)` and `Circle(...)`.

Oracle: pySlope 1.4.0 called directly (`Slope`, `Material`, `add_single_circular_plane`, `update_analysis_options`,
`analyse_slope`, `get_min_FOS`; Bishop's simplified method, validated by its authors against Slide v6 and Hyrcan).
Thresholds: `models.slope_pyslope_fixed_circle_rtol` (0.01) for one fixed circle at 200 slices and
`models.slope_pyslope_search_rtol` (0.02) for the searched minimum, read from specs/000-foundation/thresholds.yaml.
The shared cases are bench slopes (flat crest, one planar face, flat toe; unit weight in kN/m3, c' in kPa, dry): the
20 m, 45 degree, gamma 20, c' 20, phi' 30 case of the plan and four more. The trial circles of the fixed-circle test
enter on the crest and leave on the planar face (never exactly at the toe corner: a circle through the corner stays
below the flat toe ground for a while, so its exit is not the chord end), so the sliding mass is the region between the
ground and the arc (no clipping rule is involved); pySlope's tolerance is set to 1e-9 and its iteration cap to 200.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from pitstudio.slope import lem  # noqa: E402  (first-party import first: the red failure is a missing module)

pyslope = pytest.importorskip("pyslope")  # the oracle environment of T-010-002

THRESHOLDS = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "models"
]
FIXED_RTOL = THRESHOLDS["slope_pyslope_fixed_circle_rtol"]
SEARCH_RTOL = THRESHOLDS["slope_pyslope_search_rtol"]

# (height m, face angle deg, unit weight kN/m3, cohesion kPa, friction angle deg)
CASES = [
    (20.0, 45.0, 20.0, 20.0, 30.0),  # the case named in the plan
    (10.0, 60.0, 18.0, 10.0, 25.0),
    (30.0, 35.0, 22.0, 35.0, 28.0),
    (15.0, 70.0, 19.0, 50.0, 35.0),
    (40.0, 50.0, 24.0, 60.0, 32.0),
]


def _slope(height, angle, gamma, c, phi):
    s = pyslope.Slope(height=height, angle=angle, length=None)
    s.set_materials(pyslope.Material(unit_weight=gamma, friction_angle=phi, cohesion=c, depth_to_bottom=2.0 * height))
    s.update_analysis_options(slices=200, tolerance=1e-9, max_iterations=200)
    return s


def _section(slope, gamma, c, phi) -> dict:
    (x_top, y_top), (x_bot, y_bot) = slope.get_top_coordinates(), slope.get_bottom_coordinates()
    h = y_top - y_bot
    return {
        "schema_version": "1.0",
        "section_id": "pyslope-bench",
        "source": {"kind": "fixture"},
        "ground": [[0.0, y_top], [x_top, y_top], [x_bot, y_bot], [x_bot + 3.0 * h, y_bot]],
        "crest_x_m": x_top,
        "toe_x_m": x_bot,
        "materials": [
            {
                "id": "fill",
                "model": "mohr-coulomb",
                "unit_weight_kn_per_m3": gamma,
                "cohesion_kpa": c,
                "friction_angle_deg": phi,
            }
        ],
        "pore_pressure_ratio": 0.0,
        "analysis": {
            "mode": "baked",
            "methods": ["bishop"],
            "slices": 200,
            "search": {"entry_points": 40, "exit_points": 40, "radius_ratios": 8, "rho_min": 1.02, "rho_max": 4.0},
        },
    }


def _circle(section: dict, entry_x: float, exit_x: float, rho: float) -> lem.Circle:
    xs = [p[0] for p in section["ground"]]
    zs = [p[1] for p in section["ground"]]
    ze, zx = float(np.interp(entry_x, xs, zs)), float(np.interp(exit_x, xs, zs))
    dx, dz = exit_x - entry_x, zx - ze
    length = float(np.hypot(dx, dz))
    half = length / 2
    off = half * np.sqrt(rho**2 - 1)
    return lem.Circle(
        entry_x_m=entry_x,
        exit_x_m=exit_x,
        centre_x_m=(entry_x + exit_x) / 2 + (-dz / length) * off,
        centre_z_m=(ze + zx) / 2 + (dx / length) * off,
        radius_m=rho * half,
    )


def _pyslope_fos(slope) -> float:
    with contextlib.redirect_stderr(io.StringIO()):  # tqdm progress bar
        slope.analyse_slope()
    return float(slope.get_min_FOS())


@pytest.mark.req("SC-010-05")
@pytest.mark.parametrize(("height", "angle", "gamma", "c", "phi"), CASES)
def test_fixed_circle_bishop_agrees_with_pyslope_within_the_threshold(height, angle, gamma, c, phi) -> None:
    probe = _slope(height, angle, gamma, c, phi)
    section = _section(probe, gamma, c, phi)
    x_top, x_bot = section["crest_x_m"], section["toe_x_m"]
    checked = 0
    for entry_frac in (0.3, 0.55, 0.8):
        for exit_frac in (0.3, 0.6, 0.9):
            for rho in (1.3, 2.0):
                circle = _circle(section, entry_frac * x_top, x_top + exit_frac * (x_bot - x_top), rho)
                slope = _slope(height, angle, gamma, c, phi)
                slope.add_single_circular_plane(c_x=circle.centre_x_m, c_y=circle.centre_z_m, radius=circle.radius_m)
                expected = _pyslope_fos(slope)
                got = lem.bishop_fos(section, circle, slices=200).fos
                assert got == pytest.approx(expected, rel=FIXED_RTOL), (entry_frac, exit_frac, rho)
                checked += 1
    assert checked == 18


@pytest.mark.req("SC-010-05")
@pytest.mark.parametrize(("height", "angle", "gamma", "c", "phi"), CASES)
def test_searched_minimum_is_not_above_pyslopes_own_search_by_more_than_the_threshold(
    height, angle, gamma, c, phi
) -> None:
    slope = _slope(height, angle, gamma, c, phi)
    slope.update_analysis_options(iterations=3000)
    own = _pyslope_fos(slope)
    section = _section(slope, gamma, c, phi)
    row = lem.analyse_section(section)["fos"][0]
    assert row["status"] == "ok"
    # the exhaustive 12,792-circle grid must find a surface at least as good as pySlope's random search, up to the
    # threshold (pySlope's own minimum is not a lower bound: it keeps falling as its iteration count grows)
    assert row["fos"] <= own * (1.0 + SEARCH_RTOL)


@pytest.mark.req("SC-010-05")
@pytest.mark.parametrize(("height", "angle", "gamma", "c", "phi"), CASES)
def test_searched_minimum_agrees_with_pyslope_on_the_lowest_trial_circles_of_the_grid(
    height, angle, gamma, c, phi, monkeypatch
) -> None:
    import _slope_lem_ref as ref  # the independent textbook kit, here used only to rank the grid circles

    probe = _slope(height, angle, gamma, c, phi)
    section = _section(probe, gamma, c, phi)
    xs, zs = [p[0] for p in section["ground"]], [p[1] for p in section["ground"]]
    monkeypatch.setattr(ref, "ground_fn", lambda _s: lambda x: np.interp(np.asarray(x, dtype=float), xs, zs))
    circles = ref.grid_circles(section)
    f = ref.bishop_vec(section, circles, 200)  # circles whose arc leaves the ground are rejected by the kit
    lowest = np.argsort(np.where(np.isnan(f), np.inf, f))[:30]
    slope = _slope(height, angle, gamma, c, phi)
    for i in lowest:
        slope.add_single_circular_plane(c_x=float(circles[2][i]), c_y=float(circles[3][i]), radius=float(circles[4][i]))
    oracle = _pyslope_fos(slope)
    assert oracle == pytest.approx(float(f[lowest[0]]), rel=1e-6)  # the kit and pySlope agree on the same circles
    row = lem.analyse_section(section)["fos"][0]
    assert row["fos"] == pytest.approx(oracle, rel=SEARCH_RTOL)
