"""T-010-103: the pySlope oracle check of the C1 wall sections (SC-010-05, T-010-002).

Requirement: SC-010-05. Runs in the root environment, where the oracle group (pySlope 1.4.0) is installed; the module
under test, `pitstudio_pipeline.slope.c1_oracle`, imports only numpy and `pitstudio.slope.lem` and is loaded from
`pipeline/src`.

Expected API: `planar_reduction(doc) -> {"height_m", "angle_deg", "run_m"}` of the crest and toe vertices of a
section; `check_planar_reduction(doc, *, gamma, cohesion_kpa, friction_deg)` -> a record whose `fixed_pass` and
`search_pass` hold for a bench section (the criteria of T-010-012).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pipeline" / "src"))

from pitstudio_pipeline.slope import c1_oracle  # noqa: E402


def _doc():
    return {
        "section_id": "bench",
        "ground": [[0.0, 120.0], [50.0, 120.0], [90.0, 80.0], [200.0, 80.0]],
        "crest_x_m": 50.0,
        "toe_x_m": 90.0,
    }


@pytest.mark.req("SC-010-05")
def test_the_planar_reduction_takes_height_and_mean_angle_between_crest_and_toe() -> None:
    red = c1_oracle.planar_reduction(_doc())
    assert red["height_m"] == pytest.approx(40.0) and red["run_m"] == pytest.approx(40.0)
    assert red["angle_deg"] == pytest.approx(45.0)
    bad = _doc() | {"toe_x_m": 50.0}
    with pytest.raises(ValueError):
        c1_oracle.planar_reduction(bad)
    assert math.isfinite(red["angle_deg"])


@pytest.mark.req("SC-010-05")
def test_the_solver_agrees_with_pyslope_on_the_planar_reduction_of_a_bench_section() -> None:
    pytest.importorskip("pyslope")
    out = c1_oracle.check_planar_reduction(_doc(), gamma=26.0, cohesion_kpa=150.0, friction_deg=38.0, iterations=600)
    assert out["fixed_circles"] == 18
    assert out["fixed_pass"], out["fixed_max_rel_diff"]
    assert out["search_pass"], out["search"]
