"""T-010-102: C1 wall sections from the 3DEP DEM with FoS, slip circle and PoF distribution (C1-U4 of the 2026-11-23 plan).

Requirements: FR-010-01, FR-010-02, FR-010-03, FR-010-06.
Spec: specs/010-slope/spec.md section 3.1. Runs in the `pipeline/` environment.

Expected API (module `pitstudio_pipeline.slope.c1_walls`):
- `choose_face(ground, *, drop_m) -> (crest_x, toe_x)`: on the simplified ground polyline [[x, z], ...] (high side first)
  the pair of vertices (i, j), j after i, with the first j that is at least `drop_m` below i, that has the steepest mean
  angle atan(drop / run); ties go to the lowest i. ValueError when no vertex pair drops by `drop_m`. The extractor of
  FR-010-06 takes the steepest single run, which on a 1 m DEM is a bench scarp of a few metres (the reason of this
  rule); the face chosen here is the steepest stretch of one inter-ramp height.
- `wall_section(section, *, drop_m, mode, pof_settings, material, distributions) -> dict`: the extracted section with
  `crest_x_m` and `toe_x_m` of `choose_face`, the material, the analysis mode ("live" or "baked"), the methods bishop and
  spencer and the `analysis.pof` settings; the result validates against `slope-section.schema.json`.
- `pof_distribution(section, *, n, k, seed) -> dict`: `probability_of_failure` plus `min_factors` (the per-sample
  minimum Bishop factor over the K candidates, length n, finite) from the same draws; `failures`, `pof` and
  `wilson_95` equal those of `pof.probability_of_failure(section, n=n, candidates=k, seed=seed)`.
- `histogram(values, *, bins) -> dict` with `edges` (bins + 1), `counts` (sum = len(values)) and `centres`.
"""

from __future__ import annotations

import numpy as np
import pytest

from pitstudio.slope import pof, section
from pitstudio_pipeline.slope import c1_walls

MATERIAL = {
    "id": "monzonite",
    "model": "hoek-brown",
    "unit_weight_kn_per_m3": 26.0,
    "gsi": 50,
    "m_i": 10,
    "sigma_ci_mpa": 60.0,
    "disturbance_d": 0.7,
}
DISTRIBUTIONS = [
    {
        "material_id": "monzonite",
        "parameter": "gsi",
        "distribution": "normal",
        "mean": 50,
        "sd": 5,
        "truncate_lower": 10,
        "truncate_upper": 100,
    },
    {"material_id": "monzonite", "parameter": "sigma_ci_mpa", "distribution": "lognormal", "mean": 60.0, "cv": 0.3},
]


def _extracted(ground=None):
    ground = ground or [[0.0, 200.0], [100.0, 200.0], [160.0, 120.0], [300.0, 118.0], [400.0, 60.0], [500.0, 55.0]]
    return {
        "schema_version": "1.0",
        "section_id": "dem-s1",
        "source": {"kind": "fixture"},
        "ground": ground,
        "crest_x_m": 100.0,
        "toe_x_m": 160.0,
        "materials": [
            {"id": "m", "model": "mohr-coulomb", "unit_weight_kn_per_m3": 20.0, "cohesion_kpa": 20.0, "friction_angle_deg": 30.0}
        ],
        "pore_pressure_ratio": 0.0,
        "analysis": {
            "mode": "baked",
            "methods": ["bishop"],
            "slices": 200,
            "search": {"entry_points": 40, "exit_points": 40, "radius_ratios": 8, "rho_min": 1.02, "rho_max": 4.0},
        },
    }


@pytest.mark.req("FR-010-06")
def test_the_face_is_the_steepest_stretch_that_drops_by_the_inter_ramp_height() -> None:
    ground = [[0.0, 200.0], [100.0, 200.0], [160.0, 120.0], [300.0, 118.0], [400.0, 60.0], [500.0, 55.0]]
    # 80 m drop over 60 m (53 deg) then a flat bench then 58 m over 100 m: with drop_m 70 the first descent wins
    assert c1_walls.choose_face(ground, drop_m=70.0) == (100.0, 160.0)
    # asking for 100 m the steepest pair that reaches it starts at the crest and ends where 100 m are lost
    crest, toe = c1_walls.choose_face(ground, drop_m=100.0)
    assert crest == 100.0 and toe == 400.0


@pytest.mark.req("FR-010-06")
def test_no_pair_dropping_by_the_height_is_refused() -> None:
    with pytest.raises(ValueError, match="drop"):
        c1_walls.choose_face([[0.0, 10.0], [50.0, 5.0], [100.0, 4.0]], drop_m=100.0)


@pytest.mark.req("FR-010-02")
def test_the_wall_section_is_valid_hoek_brown_with_the_chosen_face_and_the_pof_settings() -> None:
    doc = c1_walls.wall_section(
        _extracted(),
        drop_m=70.0,
        mode="live",
        pof_settings={"samples": 20, "candidates": 4, "seed": 7},
        material=MATERIAL,
        distributions=DISTRIBUTIONS,
    )
    assert (doc["crest_x_m"], doc["toe_x_m"]) == (100.0, 160.0)
    assert doc["materials"] == [MATERIAL]
    assert doc["analysis"]["mode"] == "live" and doc["analysis"]["methods"] == ["bishop", "spencer"]
    assert doc["analysis"]["slices"] == 50
    assert doc["analysis"]["pof"]["samples"] == 20 and doc["analysis"]["pof"]["distributions"] == DISTRIBUTIONS
    section.parse_section(doc)  # raises InvalidSectionError when it does not validate
    base = _extracted()
    c1_walls.wall_section(
        base, drop_m=70.0, mode="live", pof_settings={"samples": 20, "candidates": 4, "seed": 7},
        material=MATERIAL, distributions=DISTRIBUTIONS,
    )
    assert base["crest_x_m"] == 100.0 and base["materials"][0]["id"] == "m"  # the input is not modified


@pytest.mark.req("FR-010-03")
def test_the_distribution_run_has_the_pof_of_the_library_and_a_finite_minimum_per_sample() -> None:
    doc = c1_walls.wall_section(
        _extracted(),
        drop_m=70.0,
        mode="live",
        pof_settings={"samples": 30, "candidates": 3, "seed": 11},
        material={
            "id": "m",
            "model": "mohr-coulomb",
            "unit_weight_kn_per_m3": 20.0,
            "cohesion_kpa": 15.0,
            "friction_angle_deg": 28.0,
        },
        distributions=[
            {
                "material_id": "m",
                "parameter": "cohesion_kpa",
                "distribution": "normal",
                "mean": 15.0,
                "sd": 4.0,
                "truncate_lower": 0.0,
            },
            {
                "material_id": "m",
                "parameter": "friction_angle_deg",
                "distribution": "normal",
                "mean": 28.0,
                "sd": 3.0,
                "truncate_lower": 5.0,
                "truncate_upper": 60.0,
            },
        ],
    )
    got = c1_walls.pof_distribution(doc, n=30, k=3, seed=11)
    ref = pof.probability_of_failure(doc, n=30, candidates=3, seed=11)
    assert (got["failures"], got["pof"], got["wilson_95"]) == (ref["failures"], ref["pof"], ref["wilson_95"])
    mins = np.asarray(got["min_factors"])
    assert mins.shape == (30,) and np.all(np.isfinite(mins)) and int((mins < 1.0).sum()) == got["failures"]


@pytest.mark.req("FR-010-03")
def test_the_histogram_counts_every_value_once_and_has_edges_and_centres() -> None:
    values = [1.0, 1.5, 1.5, 2.0, 3.0]
    h = c1_walls.histogram(values, bins=4)
    assert len(h["edges"]) == 5 and len(h["centres"]) == 4 and sum(h["counts"]) == 5
    assert h["edges"][0] == 1.0 and h["edges"][-1] == 3.0
    assert h["counts"][-1] >= 1  # the maximum falls in the last bin
