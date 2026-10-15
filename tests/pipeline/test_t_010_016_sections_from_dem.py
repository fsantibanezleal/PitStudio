"""T-010-016: reference sections cut from a DEM (`s10_preprocess`, spec 010 C1).

Requirement: FR-010-06.
Spec: specs/010-slope/spec.md section 3.1 (FR-010-06); plan.md row FR-010-06 ("analytic DEM -> known profile;
Douglas-Peucker on a hand-drawn polyline"). Runs in the `pipeline/` environment (tifffile, numpy, jsonschema).

Expected API (module `pitstudio_pipeline.slope.sections`):
- `douglas_peucker(points, tolerance) -> np.ndarray`: (N, 2) polyline to the subset of vertices (both ends kept, order
  kept)
  such that every dropped vertex is within `tolerance` of the simplified polyline; a vertex is kept when its distance to
  the chord is > tolerance. ValueError for fewer than 2 points, non-finite coordinates, tolerance <= 0 or non-finite.
- `read_dem(path) -> Dem` for a north-up GeoTIFF (area registration: pixel (row, col) has its centre at
  x = x0 + (col + 0.5) cell, y = y0 - (row + 0.5) cell; tags 33550 pixel scale, 33922 tie point, 34735 GeoKeys, 42113
  nodata): attributes `z` (float64 2-D), `x0`, `y0`, `cell`, `crs` ("EPSG:<code>"),
odata`, `sha256` (hex of the file).
- `sample_profile(dem, start_xy, end_xy, spacing=1.0) -> (distance, z)`: bilinear interpolation at distance 0,
  spacing, ...
  along the line (the end point is included when the length is a multiple of the spacing). ValueError when a sample
  falls
  outside the DEM or on a nodata cell.
- `extract_sections(dem_path, *, source_id, site_label, wall_line, half_length_m, defaults, n_sections=3)
  -> SectionsResult(sections: list[dict], manifest: dict)`: n_sections section lines, centred at the fractions (k +
  0.5) / n of
  the wall line (two map points), perpendicular to it, 2 * half_length_m long, oriented so that distance 0 is on the
  higher
  side (the face then descends towards +x of the section); profile sampled at 1 m and simplified with tolerance 0.25 m;
  one DC-010-01 document per line (`source.kind` "dem", `source_id`, `dem_sha256`, `crs`, `profile_start_m`,
  `profile_end_m`, `sample_spacing_m` 1, `simplify_tolerance_m` 0.25, `site_label`; `ground` the simplified [distance,
  z]
  vertices; `crest_x_m` and `toe_x_m` the ends of the steepest descending run; materials, pore-pressure ratio and
  analysis
  from `defaults`). `manifest` = {"stage": "s10_preprocess", "inputs": [{"path": <file name>, "sha256": ...}],
  "dem_sha256",
  "site_label", "sections": [{"section_id", "profile_start_m", "profile_end_m"}]}. n_sections < 3 raises ValueError.

Oracle: an analytic DEM written by the test (a flat bench at z = 60, a planar face of known drop over a run of 20 m, a
flat
toe at z = 40; wall along the y axis; kinks and sample points at pixel centres so that bilinear interpolation is
exact) gives
the profile by hand: vertices (0, 60), (30, 60), (50, 60 - drop), (70, 60 - drop); Douglas-Peucker checked on a
hand-drawn
polyline and by its defining guarantee (Hypothesis); the SHA-256 by `hashlib`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import tifffile
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio_pipeline.slope import sections

EPSG = 32612


def _write_dem(path: Path, drop: float, *, hole: tuple[int, int] | None = None) -> None:
    """100 x 100 m DEM, 1 m cells, x0 = 0, y0 = 100; bench z = 60 for x <= 40.5, face to 60 - drop at x = 60.5, toe
    flat."""
    cols = np.arange(100) + 0.5
    x = cols
    z_row = np.where(x <= 40.5, 60.0, np.where(x >= 60.5, 60.0 - drop, 60.0 - drop * (x - 40.5) / 20.0))
    z = np.tile(z_row, (100, 1)).astype("float32")
    if hole is not None:
        z[hole] = -9999.0
    tifffile.imwrite(
        path,
        z,
        photometric="minisblack",
        extratags=[
            (33550, "d", 3, (1.0, 1.0, 0.0), True),
            (33922, "d", 6, (0.0, 0.0, 0.0, 0.0, 100.0, 0.0), True),
            (34735, "H", 16, (1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, EPSG), True),
            (42113, "s", 0, "-9999", True),
        ],
    )


def _defaults() -> dict:
    sec = ref.planar_section()
    return {
        "materials": sec["materials"],
        "pore_pressure_ratio": 0.0,
        "analysis": sec["analysis"],
    }


# wall along x = 45.5, y from 20.5 to 80.5; centres at y = 30.5, 50.5, 70.5; section lines run x = 10.5 -> 80.5
WALL = ((45.5, 20.5), (45.5, 80.5))


# ---------------------------------------------------------------------------------------------------------------------
# Douglas-Peucker


@pytest.mark.req("FR-010-06")
def test_douglas_peucker_on_a_hand_drawn_polyline_keeps_the_two_corners() -> None:
    pts = np.array([(0, 0), (1, 0.1), (2, -0.1), (3, 0.05), (4, 0), (4.1, 1), (4.0, 2), (4.05, 3), (4, 4)], dtype=float)
    # chord (0,0)-(4,4): the farthest vertex is (4,0) at 4 / sqrt(2) = 2.83; both legs then have deviations <= 0.1 <
    # 0.25
    out = sections.douglas_peucker(pts, 0.25)
    assert out.tolist() == [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0]]


@pytest.mark.req("FR-010-06")
def test_douglas_peucker_keeps_a_vertex_beyond_the_tolerance_and_drops_it_within() -> None:
    pts = np.array([(0, 0), (5, 0.3), (10, 0)], dtype=float)  # the middle vertex is 0.3 from the chord
    assert len(sections.douglas_peucker(pts, 0.25)) == 3
    assert len(sections.douglas_peucker(pts, 0.35)) == 2


@pytest.mark.req("FR-010-06")
@pytest.mark.parametrize(
    "bad",
    [
        np.empty((0, 2)),
        np.array([[0.0, 0.0]]),
        np.array([[0.0, 0.0], [np.nan, 1.0]]),
        np.array([[0.0, 0.0], [1.0, np.inf]]),
    ],
)
def test_douglas_peucker_rejects_hostile_polylines(bad) -> None:
    with pytest.raises(ValueError, match=r"."):
        sections.douglas_peucker(bad, 0.25)


@pytest.mark.req("FR-010-06")
@pytest.mark.parametrize("tol", [0.0, -0.25, float("nan"), float("inf")])
def test_douglas_peucker_rejects_a_bad_tolerance(tol) -> None:
    with pytest.raises(ValueError, match=r"."):
        sections.douglas_peucker(np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]), tol)


def _deviation_from_chords(pts: np.ndarray, kept: np.ndarray) -> float:
    """Largest perpendicular distance of a vertex to the line through the two kept vertices that bracket it."""
    xs = kept[:, 0]
    worst = 0.0
    for p in pts:
        i = int(np.searchsorted(xs, p[0], side="right")) - 1
        i = min(max(i, 0), len(kept) - 2)
        a, b = kept[i], kept[i + 1]
        ab = b - a
        worst = max(worst, abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / float(np.hypot(*ab)))
    return worst


@pytest.mark.req("FR-010-06")
@settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(
    st.lists(st.floats(-50.0, 50.0), min_size=2, max_size=60),
    st.floats(0.05, 2.0),
)
def test_douglas_peucker_guarantee_endpoints_subset_and_deviation_within_tolerance(zs, tol) -> None:
    pts = np.column_stack([np.arange(len(zs), dtype=float), np.asarray(zs)])
    out = sections.douglas_peucker(pts, tol)
    assert out[0].tolist() == pts[0].tolist()
    assert out[-1].tolist() == pts[-1].tolist()
    rows = {tuple(r) for r in pts.tolist()}
    assert all(tuple(r) in rows for r in out.tolist())
    assert np.all(np.diff(out[:, 0]) > 0)
    # the defining guarantee: no dropped vertex is farther than the tolerance from the chord that replaced it
    assert _deviation_from_chords(pts, out) <= tol + 1e-9


# ---------------------------------------------------------------------------------------------------------------------
# reading and sampling


@pytest.mark.req("FR-010-06")
def test_read_dem_returns_the_georeferenced_array_and_the_file_digest(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0)
    dem = sections.read_dem(path)
    assert dem.z.shape == (100, 100)
    assert (dem.x0, dem.y0, dem.cell, dem.crs) == (0.0, 100.0, 1.0, f"EPSG:{EPSG}")
    assert dem.nodata == -9999.0
    assert dem.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert dem.z[0, 0] == 60.0
    assert dem.z[0, 99] == 50.0


@pytest.mark.req("FR-010-06")
def test_sample_profile_follows_the_analytic_surface_at_one_metre_spacing(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0)
    dem = sections.read_dem(path)
    d, z = sections.sample_profile(dem, (10.5, 30.5), (80.5, 30.5), 1.0)
    assert d.tolist() == list(map(float, range(71)))
    expected = np.where(d <= 30, 60.0, np.where(d >= 50, 50.0, 60.0 - 10.0 * (d - 30) / 20.0))
    assert z == pytest.approx(expected, abs=1e-5)  # float32 storage
    # half-way between pixel centres bilinear interpolation gives the mean of the two values
    _, z2 = sections.sample_profile(dem, (10.5, 30.5), (80.5, 30.5), 0.5)
    assert z2[2 * 35] == pytest.approx(60.0 - 10.0 * 5 / 20.0, abs=1e-5)


@pytest.mark.req("FR-010-06")
def test_sampling_outside_the_dem_or_on_nodata_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0, hole=(69, 70))  # row 69 is y = 30.5; column 70 is x = 70.5
    dem = sections.read_dem(path)
    with pytest.raises(ValueError, match=r"."):
        sections.sample_profile(dem, (10.5, 30.5), (150.5, 30.5))
    with pytest.raises(ValueError, match=r"."):
        sections.sample_profile(dem, (10.5, 30.5), (80.5, 30.5))


# ---------------------------------------------------------------------------------------------------------------------
# the section extractor


@pytest.mark.req("FR-010-06")
@pytest.mark.parametrize("drop", [10.0, 15.0])
def test_three_sections_are_cut_perpendicular_to_the_wall_with_the_analytic_ground(tmp_path: Path, drop: float) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, drop)
    res = sections.extract_sections(
        path, source_id="bingham-3dep-2018", site_label="Bingham Canyon (provisional)",
        wall_line=WALL, half_length_m=35.0, defaults=_defaults(),
    )  # fmt: skip
    assert len(res.sections) == 3
    ids = [s["section_id"] for s in res.sections]
    assert len(set(ids)) == 3
    assert all(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", i) for i in ids)
    for k, doc in enumerate(res.sections):
        y = 30.5 + 20.0 * k
        assert ref.schema_errors(doc, "slope-section") == []
        src = doc["source"]
        assert src["kind"] == "dem"
        assert src["source_id"] == "bingham-3dep-2018"
        assert src["dem_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert src["crs"] == f"EPSG:{EPSG}"
        assert src["profile_start_m"] == pytest.approx([10.5, y])
        assert src["profile_end_m"] == pytest.approx([80.5, y])
        assert (src["sample_spacing_m"], src["simplify_tolerance_m"]) == (1, 0.25)
        assert src["site_label"] == "Bingham Canyon (provisional)"
        # by hand: bench to d = 30, planar face to d = 50, toe flat to d = 70 (Douglas-Peucker leaves the 4 corners)
        want = np.array([[0.0, 60.0], [30.0, 60.0], [50.0, 60.0 - drop], [70.0, 60.0 - drop]])
        assert np.asarray(doc["ground"]) == pytest.approx(want, abs=1e-5)
        assert (doc["crest_x_m"], doc["toe_x_m"]) == pytest.approx((30.0, 50.0))
        assert doc["materials"] == _defaults()["materials"]


@pytest.mark.req("FR-010-06")
def test_the_manifest_records_the_dem_digest_the_profile_ends_and_the_site_label(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0)
    res = sections.extract_sections(
        path, source_id="hambach-dgm1", site_label="Hambach (provisional)",
        wall_line=WALL, half_length_m=35.0, defaults=_defaults(),
    )  # fmt: skip
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    m = res.manifest
    assert m["stage"] == "s10_preprocess"
    assert m["dem_sha256"] == digest
    assert {"path": "dem.tif", "sha256": digest} in m["inputs"]
    assert m["site_label"] == "Hambach (provisional)"
    assert [(s["section_id"], s["profile_start_m"], s["profile_end_m"]) for s in m["sections"]] == [
        (doc["section_id"], doc["source"]["profile_start_m"], doc["source"]["profile_end_m"]) for doc in res.sections
    ]
    json.dumps(m)  # JSON-serialisable


@pytest.mark.req("FR-010-06")
def test_extraction_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0)
    kw = {"source_id": "x-1", "site_label": "Site (provisional)", "wall_line": WALL, "half_length_m": 35.0}
    a = sections.extract_sections(path, defaults=_defaults(), **kw)
    b = sections.extract_sections(path, defaults=_defaults(), **kw)
    assert json.dumps(a.sections, sort_keys=True) == json.dumps(b.sections, sort_keys=True)
    assert a.manifest == b.manifest


@pytest.mark.req("FR-010-06")
def test_fewer_than_three_sections_and_hostile_lines_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dem.tif"
    _write_dem(path, 10.0)
    kw = {"source_id": "x-1", "site_label": "Site (provisional)", "defaults": _defaults()}
    with pytest.raises(ValueError, match=r"."):
        sections.extract_sections(path, wall_line=WALL, half_length_m=35.0, n_sections=2, **kw)
    with pytest.raises(ValueError, match=r"."):  # section lines leave the DEM
        sections.extract_sections(path, wall_line=WALL, half_length_m=80.0, **kw)
    with pytest.raises(ValueError, match=r"."):  # zero-length wall
        sections.extract_sections(path, wall_line=((45.5, 50.5), (45.5, 50.5)), half_length_m=35.0, **kw)
    with pytest.raises(ValueError, match=r"."):
        sections.extract_sections(path, wall_line=WALL, half_length_m=float("nan"), **kw)
    with pytest.raises((FileNotFoundError, ValueError)):
        sections.extract_sections(tmp_path / "missing.tif", wall_line=WALL, half_length_m=35.0, **kw)
