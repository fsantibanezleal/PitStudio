"""pySlope oracle check of the C1 wall sections (SC-010-05, T-010-002).

pySlope 1.4.0 models one planar bench (height, angle, Mohr-Coulomb layers) and cannot read a DEM polyline or a
Hoek-Brown material. The check therefore compares ``pitstudio.slope.lem`` with pySlope on the planar reduction of each
analysed face (its height and mean angle between crest and toe) with a Mohr-Coulomb material, by the two criteria of
T-010-012: a fixed circle at 200 slices within ``FIXED_RTOL`` and the searched minimum not above the own search of
pySlope by more than ``SEARCH_RTOL`` (the values of thresholds.yaml). pySlope is oracle-only and imported lazily, so
this module loads in any environment; ``check_planar_reduction`` raises ``ImportError`` where pySlope is absent.
"""

from __future__ import annotations

import contextlib
import io
import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from pitstudio.slope import lem

FIXED_RTOL = 0.01
SEARCH_RTOL = 0.02
TRIAL_ENTRY = (0.3, 0.55, 0.8)
TRIAL_EXIT = (0.3, 0.6, 0.9)
TRIAL_RHO = (1.3, 2.0)


def planar_reduction(doc: Mapping[str, Any]) -> dict[str, float]:
    """Height (m) and mean face angle (degrees) between the crest and the toe vertices of the section."""
    x = np.array([p[0] for p in doc["ground"]], dtype=float)
    z = np.array([p[1] for p in doc["ground"]], dtype=float)
    crest, toe = float(doc["crest_x_m"]), float(doc["toe_x_m"])
    height = float(np.interp(crest, x, z) - np.interp(toe, x, z))
    run = toe - crest
    if not (height > 0.0 and run > 0.0):
        raise ValueError("the face needs a positive height and run")
    return {"height_m": height, "angle_deg": math.degrees(math.atan2(height, run)), "run_m": run}


def _slope(pyslope: Any, h: float, angle: float, gamma: float, c: float, phi: float) -> Any:
    s = pyslope.Slope(height=h, angle=angle, length=None)
    s.set_materials(pyslope.Material(unit_weight=gamma, friction_angle=phi, cohesion=c, depth_to_bottom=2.0 * h))
    s.update_analysis_options(slices=200, tolerance=1e-9, max_iterations=200)
    return s


def _fos(slope: Any) -> float:
    with contextlib.redirect_stderr(io.StringIO()):
        slope.analyse_slope()
    return float(slope.get_min_FOS())


def _circle(section: Mapping[str, Any], entry_x: float, exit_x: float, rho: float) -> lem.Circle:
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


def check_planar_reduction(
    doc: Mapping[str, Any], *, gamma: float, cohesion_kpa: float, friction_deg: float, iterations: int = 3000
) -> dict[str, Any]:
    """Compare ``lem`` with pySlope on the planar reduction of the section's face (see the module docstring)."""
    import pyslope

    red = planar_reduction(doc)
    h, angle = red["height_m"], red["angle_deg"]
    probe = _slope(pyslope, h, angle, gamma, cohesion_kpa, friction_deg)
    (x_top, y_top), (x_bot, y_bot) = probe.get_top_coordinates(), probe.get_bottom_coordinates()
    bench = {
        "schema_version": "1.0",
        "section_id": f"{doc.get('section_id', 'section')}-planar-reduction",
        "source": {"kind": "fixture"},
        "ground": [[0.0, y_top], [x_top, y_top], [x_bot, y_bot], [x_bot + 3.0 * (y_top - y_bot), y_bot]],
        "crest_x_m": x_top,
        "toe_x_m": x_bot,
        "materials": [
            {
                "id": "mc",
                "model": "mohr-coulomb",
                "unit_weight_kn_per_m3": gamma,
                "cohesion_kpa": cohesion_kpa,
                "friction_angle_deg": friction_deg,
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
    fixed = []
    for ef in TRIAL_ENTRY:
        for xf in TRIAL_EXIT:
            for rho in TRIAL_RHO:
                circle = _circle(bench, ef * x_top, x_top + xf * (x_bot - x_top), rho)
                s = _slope(pyslope, h, angle, gamma, cohesion_kpa, friction_deg)
                s.add_single_circular_plane(c_x=circle.centre_x_m, c_y=circle.centre_z_m, radius=circle.radius_m)
                oracle = _fos(s)
                mine = float(lem.bishop_fos(bench, circle, slices=200).fos)
                fixed.append({"oracle": oracle, "mine": mine, "rel_diff": abs(mine - oracle) / oracle})
    s = _slope(pyslope, h, angle, gamma, cohesion_kpa, friction_deg)
    s.update_analysis_options(iterations=iterations)
    own = _fos(s)
    row = lem.analyse_section(bench)["fos"][0]
    return {
        "section_id": doc.get("section_id"),
        "planar_reduction": red,
        "material": {"gamma_kn_per_m3": gamma, "cohesion_kpa": cohesion_kpa, "friction_deg": friction_deg},
        "pyslope_version": getattr(pyslope, "__version__", "unknown"),
        "fixed_circles": len(fixed),
        "fixed_max_rel_diff": max(f["rel_diff"] for f in fixed),
        "fixed_rtol": FIXED_RTOL,
        "fixed_pass": all(f["rel_diff"] <= FIXED_RTOL for f in fixed),
        "search": {"mine": float(row["fos"]), "pyslope_own_search": own, "rtol": SEARCH_RTOL},
        "search_pass": bool(row["fos"] <= own * (1.0 + SEARCH_RTOL)),
    }
