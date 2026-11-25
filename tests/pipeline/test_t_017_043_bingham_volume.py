"""T-017-043: the real Bingham 2018 -> 2023 volume over the area of interest (pipeline).

Requirements: FR-017-34.

Spec: specs/017-planning-survey/spec.md FR-017-34: the E2 real result is the 2018 -> 2023 V_cut, V_fill and V_net
(m^3) over
the Bingham pit area of interest (the Tang & Werner mining-footprint polygon intersected with the 3DEP query box, the
overlap ratio reported; the site label stays provisional when no polygon intersects), with its uncertainty bounds,
inputs
and digests, labelled "measurement, not validation". plan.md test strategy row FR-017-34: a fixture polygon pair
with a
known overlap ratio; contract of the result. The real 3DEP files and the Tang & Werner polygon are not fetched by the
tests (UNVERIFIED here); fixtures stand in for them.

Oracles:
- a 10 x 10 grid of 10 m cells (A_c = 100 m^2), flat before surface 50 m, after surface 48 m everywhere (a uniform 2 m
  cut) except a fill block in the upper right (+1.5 m on the four cells with centres x, y >= 85 ... which lie
  outside the
  area of interest and so must not contribute);
- the footprint triangle (0, 0), (100, 0), (0, 100) (area 5,000 m^2) clipped by the query box x in [0, 50], y in
  [0, 100]:
  the intersection is the quadrilateral (0, 0), (50, 0), (50, 50), (0, 100) with area 5,000 - 1,250 = 3,750 m^2, so
  the
  overlap ratio is 3,750 / 5,000 = 0.75 by hand; the cells whose centres lie strictly inside the quadrilateral are
  counted
  by an independent loop in the test (35 of them: 9 + 8 + 7 + 6 + 5 over the five columns x = 5, 15, 25, 35, 45), so
  V_cut = 35 x 100 x 2 = 7,000 m^3, V_fill = 0, V_net = -7,000 m^3;
- the uncertainty bounds from the spec formulas by hand: N = 35, A_c = 100, sigma_0 = 0.1 m, sigma_1 = 0.1 m:
  sqrt(0.02) = 0.141421356: uncorrelated 100 x sqrt(35) x 0.141421356, correlated 100 x 35 x 0.141421356;
- the DC-017-04 schema (`jsonschema`) and the spec's valid real-volume example (the metadata block of the fixture is
  copied from it).

Expected public API (module `pitstudio.survey.real_volume`, root environment, numpy only):
    clip_polygon(subject: np.ndarray, box: np.ndarray) -> np.ndarray     # the part of `subject` inside the
    axis-aligned
        rectangle `box` (4 vertices), an (m, 2) array (m = 0 when they do not intersect)
    polygon_area(vertices: np.ndarray) -> float                           # shoelace, absolute value
    real_volume(before: Surface, after: Surface, *, footprint: np.ndarray, query_box: np.ndarray, meta: Mapping) ->
    dict
        `meta` = {"id", "licence", "surfaces": {"before": {...}, "after": {...}}, "resampling",
        "vertical_transform"} as in
        the DC-017-04 real volume; returns the DC-017-04 volume object: scope "real", method "dem-differencing",
        status
        "ok", label "measurement, not validation", the surfaces and licence of `meta`, grid {cell_m, shape [ny, nx],
        origin_m, crs (of the after surface)}, polygon {vertices (the clipped area of interest), source
        "mining-footprint
        polygon intersected with the 3DEP query box", overlap_ratio = area(clipped) / area(footprint)}, v_cut_m3,
        v_fill_m3, v_net_m3, cells {valid, nodata, nodata_fraction}, uncertainty_m3 {uncorrelated, correlated}.
        When the
        footprint and the box do not intersect the area of interest is the whole query box, overlap_ratio is 0.0
        and the
        source text contains "provisional".
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest
from pitstudio.survey.difference import Surface
from pitstudio.survey.real_volume import clip_polygon, polygon_area, real_volume

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs/017-planning-survey/contracts/examples/survey-volume.valid.json"
REAL = json.loads(EX.read_text("utf-8"))["volumes"][0]
SCHEMA = json.loads((ROOT / "contracts" / "survey-volume.schema.json").read_text("utf-8"))
FOOTPRINT = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 100.0]])
BOX = np.array([[0.0, 0.0], [50.0, 0.0], [50.0, 100.0], [0.0, 100.0]])
EXPECTED_AOI = {(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 100.0)}


def _surfaces() -> tuple[Surface, Surface]:
    z0 = np.full((10, 10), 50.0)
    z1 = np.full((10, 10), 48.0)
    z1[8:, 8:] = 51.5  # four cells with centres x, y in {85, 95}: a fill block far outside the area of interest
    return (
        Surface(z=z0, origin_xy=(0.0, 0.0), cell_size_m=10.0, nodata=None),
        Surface(z=z1, origin_xy=(0.0, 0.0), cell_size_m=10.0, nodata=None),
    )


def _meta() -> dict:
    meta = {k: copy.deepcopy(REAL[k]) for k in ("id", "licence", "surfaces", "resampling", "vertical_transform")}
    for side in ("before", "after"):
        meta["surfaces"][side]["rmse_z_m"] = 0.1
    return meta


def _errors(volume: dict) -> list:
    from jsonschema import Draft202012Validator

    return list(Draft202012Validator(SCHEMA).iter_errors({"schema_version": "1.0", "volumes": [volume]}))


def _centres_inside_quad() -> int:
    """Independent count of the cell centres strictly inside (0,0)-(50,0)-(50,50)-(0,100)."""
    n = 0
    for i in range(10):
        for j in range(10):
            x, y = 10 * j + 5, 10 * i + 5
            if 0 < x < 50 and 0 < y < 100 - x:
                n += 1
    return n


# ----------------------------------------------------------------------------------------------------------------------
# the geometry
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-34")
def test_the_footprint_clipped_by_the_query_box_is_the_hand_quadrilateral() -> None:
    clipped = clip_polygon(FOOTPRINT, BOX)
    assert {(float(x), float(y)) for x, y in clipped} == EXPECTED_AOI
    assert polygon_area(clipped) == pytest.approx(3750.0, rel=1e-12)
    assert polygon_area(FOOTPRINT) == pytest.approx(5000.0, rel=1e-12)


@pytest.mark.req("FR-017-34")
def test_a_footprint_inside_the_box_is_unchanged_and_a_disjoint_one_is_empty() -> None:
    inside = clip_polygon(FOOTPRINT, np.array([[-10.0, -10.0], [200.0, -10.0], [200.0, 200.0], [-10.0, 200.0]]))
    assert polygon_area(inside) == pytest.approx(5000.0, rel=1e-12)
    far = clip_polygon(FOOTPRINT, np.array([[500.0, 500.0], [600.0, 500.0], [600.0, 600.0], [500.0, 600.0]]))
    assert len(far) == 0
    assert polygon_area(far) == 0.0


# ----------------------------------------------------------------------------------------------------------------------
# the result
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-34")
def test_the_real_volume_over_the_area_of_interest_by_hand() -> None:
    before, after = _surfaces()
    assert _centres_inside_quad() == 35
    v = real_volume(before, after, footprint=FOOTPRINT, query_box=BOX, meta=_meta())
    assert v["v_cut_m3"] == pytest.approx(7000.0, rel=1e-12)
    assert v["v_fill_m3"] == 0.0  # the fill block lies outside the area of interest
    assert v["v_net_m3"] == pytest.approx(-7000.0, rel=1e-12)
    assert v["cells"] == {"valid": 35, "nodata": 0, "nodata_fraction": 0.0}
    assert v["polygon"]["overlap_ratio"] == pytest.approx(0.75, rel=1e-12)
    assert {(float(x), float(y)) for x, y in v["polygon"]["vertices"]} == EXPECTED_AOI
    assert v["polygon"]["source"] == "mining-footprint polygon intersected with the 3DEP query box"


@pytest.mark.req("FR-017-34")
def test_the_uncertainty_bounds_follow_the_spec_formulas() -> None:
    before, after = _surfaces()
    v = real_volume(before, after, footprint=FOOTPRINT, query_box=BOX, meta=_meta())
    sigma = math.sqrt(0.1**2 + 0.1**2)
    assert v["uncertainty_m3"]["uncorrelated"] == pytest.approx(100.0 * math.sqrt(35) * sigma, rel=1e-12)
    assert v["uncertainty_m3"]["correlated"] == pytest.approx(100.0 * 35 * sigma, rel=1e-12)


@pytest.mark.req("FR-017-34")
def test_the_result_carries_the_label_inputs_digests_grid_and_validates_against_dc_017_04() -> None:
    before, after = _surfaces()
    v = real_volume(before, after, footprint=FOOTPRINT, query_box=BOX, meta=_meta())
    assert (v["scope"], v["method"], v["status"]) == ("real", "dem-differencing", "ok")
    assert v["label"] == "measurement, not validation"
    assert v["surfaces"] == _meta()["surfaces"]  # inputs, digests, projects, datum and RMSEz as given
    assert v["licence"] == REAL["licence"]
    assert v["grid"] == {
        "cell_m": 10.0,
        "shape": [10, 10],
        "origin_m": [0.0, 0.0],
        "crs": REAL["surfaces"]["after"]["crs"],
    }
    assert _errors(v) == []


@pytest.mark.req("FR-017-34")
def test_a_footprint_that_does_not_intersect_the_box_leaves_the_site_provisional() -> None:
    before, after = _surfaces()
    far_footprint = FOOTPRINT + 10_000.0
    v = real_volume(before, after, footprint=far_footprint, query_box=BOX, meta=_meta())
    assert v["polygon"]["overlap_ratio"] == 0.0
    assert "provisional" in v["polygon"]["source"]
    assert polygon_area(np.array(v["polygon"]["vertices"])) == pytest.approx(5000.0, rel=1e-12)  # the whole query box
    assert v["label"] == "measurement, not validation"
    assert _errors(v) == []


@pytest.mark.req("FR-017-34")
def test_a_full_overlap_gives_ratio_one() -> None:
    before, after = _surfaces()
    big_box = np.array([[-5.0, -5.0], [150.0, -5.0], [150.0, 150.0], [-5.0, 150.0]])
    v = real_volume(before, after, footprint=FOOTPRINT, query_box=big_box, meta=_meta())
    assert v["polygon"]["overlap_ratio"] == pytest.approx(1.0, rel=1e-12)
