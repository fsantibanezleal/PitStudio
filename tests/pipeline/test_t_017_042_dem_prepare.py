"""T-017-042: DEM grid preparation: CRS, datum, reprojection, datum mismatch (pipeline, studio environment).

Requirements: FR-017-31, FR-017-32.

Spec: specs/017-planning-survey/spec.md
- FR-017-31: the grid preparation reads the horizontal CRS, the vertical datum and the vertical accuracy (RMSEz) of
  each
  DEM from its metadata, reprojects the 2018 DEM onto the 2023 grid by bilinear interpolation when the grids
  differ, and
  records the transform, both SHA-256 digests and both 3DEP project names;
- FR-017-32: if the two DEMs' vertical datums or geoid models differ and the recipe declares no vertical transform
  (with
  its source), the real-volume result is "Not run -- vertical datums differ" (an em dash in the label); a declared
  constant or grid offset is applied and recorded.
plan.md test strategy rows FR-017-31 / FR-017-32 (studio env): synthetic GeoTIFFs with known CRS, datum and RMSEz
built by
the test; a datum mismatch with and without a declared offset.

Oracles:
- synthetic GeoTIFFs written by the test with `rasterio` (reference implementation of the format), with the
  metadata as
  GDAL dataset tags `VERTICAL_DATUM`, `GEOID`, `RMSEZ_M` and `PROJECT_NAME` (the tag names are this test's contract
  with
  the implementation: UNVERIFIED against the real 3DEP metadata, which the spec says is read per project);
- bilinear interpolation reproduces a linear function exactly in the interior of the source grid, so a 2018 DEM
  sampled
  from the plane z = 5 + 0.02 x + 0.03 y (x, y in metres from the grid corner) reprojected onto a finer, shifted 2023
  grid must equal the plane evaluated at the 2023 cell centres (float32 storage: tolerance 1e-3 m);
- SHA-256 digests by `hashlib` over the file bytes; the transform of the 2023 grid written out by hand;
- the declared offset arithmetic by hand (+0.25 m added to every 2018 value).

Expected public API (module `pitstudio_studio.survey.dem_prepare`, `studio/` environment, rasterio):
    @dataclass(frozen=True) DemInfo: z (float64 array, NaN for no data), transform (6 floats a, b, c, d, e, f of the
        affine), crs (str "EPSG:nnnn"), vertical_datum (str), geoid (str), rmse_z_m (float), project (str), sha256
        (hex)
    read_dem(path: Path) -> DemInfo
    @dataclass PrepareResult: status "ok" | "not_run"; label (None or "Not run â€” <reason>"); before (DemInfo
        on the 2023 grid, vertical offset applied) or None; after (the 2023 DemInfo) or None; record (dict) or None.
    prepare_pair(path_2018: Path, path_2023: Path, *, recipe: Mapping) -> PrepareResult
        `recipe` may hold "vertical_transform": {"kind": "constant", "offset_m": float, "source": str} or {"kind":
        "grid", "path": str (a GeoTIFF on the 2023 grid), "source": str}. record = {"crs", "transform" (of the
        target grid), "resampling":
        "bilinear" | "none", "sha256_2018", "sha256_2023", "project_2018", "project_2023", "vertical_datum_2018",
        "vertical_datum_2023", "geoid_2018", "geoid_2023", "rmse_z_2018_m", "rmse_z_2023_m", "vertical_transform":
        None | the declared transform that was applied}.
        Grids that are identical are not resampled ("none"); a vertical datum or geoid that differs gives status
        "not_run" with the label "Not run â€” vertical datums differ" unless the recipe declares a vertical transform
        with a non-empty `source`; a declared transform without a source counts as undeclared.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from pitstudio_studio.survey.dem_prepare import prepare_pair, read_dem

EM_DASH = "â€”"
SOURCE = "NOAA VDatum 4.x, GEOID12B to GEOID18 offset at Bingham Canyon"


def _write(path: Path, *, cell: float, x0: float, y_top: float, nx: int, ny: int, datum="NAVD88", geoid="GEOID18",
           rmse=0.15, project="UT_Bingham_2018", fn=None) -> Path:  # fmt: skip
    import rasterio
    from rasterio.transform import from_origin

    xs = x0 + (np.arange(nx) + 0.5) * cell
    ys = y_top - (np.arange(ny) + 0.5) * cell
    plane = (lambda x, y: 5.0 + 0.02 * (x - 400_000.0) + 0.03 * (y - 4_500_000.0)) if fn is None else fn
    z = plane(xs[None, :], ys[:, None]).astype(np.float32)
    profile = {
        "driver": "GTiff", "height": ny, "width": nx, "count": 1, "dtype": "float32", "crs": "EPSG:32612",
        "transform": from_origin(x0, y_top, cell, cell), "nodata": -9999.0,
    }  # fmt: skip
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(z, 1)
        dst.update_tags(VERTICAL_DATUM=datum, GEOID=geoid, RMSEZ_M=str(rmse), PROJECT_NAME=project)
    return path


def _pair(tmp_path: Path, **kw2018):
    p18 = _write(tmp_path / "2018.tif", cell=4.0, x0=400_000.0, y_top=4_500_100.0, nx=30, ny=30, **kw2018)
    p23 = _write(
        tmp_path / "2023.tif", cell=2.0, x0=400_011.0, y_top=4_500_089.0, nx=40, ny=40, geoid="GEOID18",
        rmse=0.1, project="UT_Bingham_2023",
    )  # fmt: skip
    return p18, p23


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-31
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-31")
def test_the_crs_datum_geoid_rmse_and_project_are_read_from_the_metadata(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "a.tif",
        cell=4.0,
        x0=400_000.0,
        y_top=4_500_100.0,
        nx=10,
        ny=10,
        datum="NAD83",
        geoid="GEOID12B",
        rmse=0.21,
        project="UT_Test",
    )
    dem = read_dem(path)
    assert dem.crs == "EPSG:32612"
    assert (dem.vertical_datum, dem.geoid, dem.rmse_z_m, dem.project) == ("NAD83", "GEOID12B", 0.21, "UT_Test")
    assert dem.transform == (4.0, 0.0, 400_000.0, 0.0, -4.0, 4_500_100.0)
    assert dem.z.shape == (10, 10)
    assert dem.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.req("FR-017-31")
def test_grids_that_differ_are_resampled_bilinearly_onto_the_2023_grid_exactly_for_a_plane(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path)
    result = prepare_pair(p18, p23, recipe={})
    assert result.status == "ok"
    assert result.label is None
    assert result.record["resampling"] == "bilinear"
    assert result.before.z.shape == result.after.z.shape == (40, 40)
    assert result.before.transform == result.after.transform == (2.0, 0.0, 400_011.0, 0.0, -2.0, 4_500_089.0)
    xs = 400_011.0 + (np.arange(40) + 0.5) * 2.0
    ys = 4_500_089.0 - (np.arange(40) + 0.5) * 2.0
    plane = 5.0 + 0.02 * (xs[None, :] - 400_000.0) + 0.03 * (ys[:, None] - 4_500_000.0)
    np.testing.assert_allclose(result.before.z, plane, atol=1e-3)  # the 2023 grid lies inside the 2018 coverage


@pytest.mark.req("FR-017-31")
def test_the_record_holds_the_transform_both_digests_both_projects_and_the_rmse(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path)
    record = prepare_pair(p18, p23, recipe={}).record
    assert record["crs"] == "EPSG:32612"
    assert record["transform"] == (2.0, 0.0, 400_011.0, 0.0, -2.0, 4_500_089.0)
    assert record["sha256_2018"] == hashlib.sha256(p18.read_bytes()).hexdigest()
    assert record["sha256_2023"] == hashlib.sha256(p23.read_bytes()).hexdigest()
    assert (record["project_2018"], record["project_2023"]) == ("UT_Bingham_2018", "UT_Bingham_2023")
    assert (record["rmse_z_2018_m"], record["rmse_z_2023_m"]) == (0.15, 0.1)
    assert (record["vertical_datum_2018"], record["vertical_datum_2023"]) == ("NAVD88", "NAVD88")
    assert record["vertical_transform"] is None


@pytest.mark.req("FR-017-31")
def test_identical_grids_are_not_resampled(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.tif", cell=2.0, x0=400_000.0, y_top=4_500_100.0, nx=20, ny=20, project="UT_A")
    b = _write(tmp_path / "b.tif", cell=2.0, x0=400_000.0, y_top=4_500_100.0, nx=20, ny=20, project="UT_B", rmse=0.1)
    result = prepare_pair(a, b, recipe={})
    assert result.record["resampling"] == "none"
    np.testing.assert_array_equal(result.before.z, read_dem(a).z)


# ----------------------------------------------------------------------------------------------------------------------
# FR-017-32
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-017-32")
@pytest.mark.parametrize(("datum", "geoid"), [("NGVD29", "GEOID18"), ("NAVD88", "GEOID12B"), ("NGVD29", "GEOID12B")])
def test_a_vertical_datum_or_geoid_mismatch_without_a_declared_transform_is_not_run(
    tmp_path: Path, datum, geoid
) -> None:
    p18, p23 = _pair(tmp_path, datum=datum, geoid=geoid)
    result = prepare_pair(p18, p23, recipe={})
    assert result.status == "not_run"
    assert result.label == f"Not run {EM_DASH} vertical datums differ"
    assert result.before is None
    assert result.after is None


@pytest.mark.req("FR-017-32")
def test_a_declared_constant_offset_is_applied_and_recorded(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path, geoid="GEOID12B")
    transform = {"kind": "constant", "offset_m": 0.25, "source": SOURCE}
    plain = prepare_pair(p18, p23, recipe={"vertical_transform": transform})
    assert plain.status == "ok"
    assert plain.record["vertical_transform"] == transform
    # the same grids with matching metadata and no transform give the un-shifted values: the shift is exactly +0.25 m
    base18 = _write(tmp_path / "b18.tif", cell=4.0, x0=400_000.0, y_top=4_500_100.0, nx=30, ny=30, geoid="GEOID18")
    reference = prepare_pair(base18, p23, recipe={})
    np.testing.assert_allclose(plain.before.z - reference.before.z, 0.25, atol=1e-6)
    np.testing.assert_array_equal(plain.after.z, reference.after.z)  # the 2023 surface is never shifted


@pytest.mark.req("FR-017-32")
def test_a_declared_grid_offset_is_applied_cell_by_cell_and_recorded(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path, geoid="GEOID12B")
    offset = _write(
        tmp_path / "offset.tif",
        cell=2.0,
        x0=400_011.0,
        y_top=4_500_089.0,
        nx=40,
        ny=40,
        fn=lambda x, y: 0.1 + 0.001 * (x - 400_000.0) + 0.0 * y,
    )
    transform = {"kind": "grid", "path": str(offset), "source": SOURCE}
    result = prepare_pair(p18, p23, recipe={"vertical_transform": transform})
    assert result.status == "ok"
    assert result.record["vertical_transform"] == transform
    base18 = _write(tmp_path / "b18.tif", cell=4.0, x0=400_000.0, y_top=4_500_100.0, nx=30, ny=30, geoid="GEOID18")
    reference = prepare_pair(base18, p23, recipe={})
    xs = 400_011.0 + (np.arange(40) + 0.5) * 2.0
    expected = 0.1 + 0.001 * (xs[None, :] - 400_000.0) * np.ones((40, 1))
    np.testing.assert_allclose(result.before.z - reference.before.z, expected, atol=1e-3)


@pytest.mark.req("FR-017-32")
@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "constant", "offset_m": 0.25},
        {"kind": "constant", "offset_m": 0.25, "source": ""},
        {"kind": "constant", "offset_m": 0.25, "source": "   "},
    ],
)
def test_a_transform_without_a_source_counts_as_undeclared(tmp_path: Path, bad: dict) -> None:
    p18, p23 = _pair(tmp_path, geoid="GEOID12B")
    result = prepare_pair(p18, p23, recipe={"vertical_transform": bad})
    assert result.status == "not_run"
    assert "vertical datums differ" in result.label


@pytest.mark.req("FR-017-32")
@pytest.mark.parametrize("offset", [float("nan"), float("inf"), "0.2", None])
def test_a_non_finite_or_non_numeric_offset_is_not_applied(tmp_path: Path, offset) -> None:
    p18, p23 = _pair(tmp_path, geoid="GEOID12B")
    recipe = {"vertical_transform": {"kind": "constant", "offset_m": offset, "source": SOURCE}}
    try:
        result = prepare_pair(p18, p23, recipe=recipe)
    except ValueError:
        return  # refusing the recipe is acceptable
    assert result.status == "not_run"


@pytest.mark.req("FR-017-32")
def test_a_declared_transform_is_not_needed_and_not_recorded_when_the_datums_agree(tmp_path: Path) -> None:
    p18, p23 = _pair(tmp_path)  # same datum and geoid
    result = prepare_pair(p18, p23, recipe={})
    assert result.status == "ok"
    assert result.record["vertical_transform"] is None
