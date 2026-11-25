# ruff: noqa: E501, PT018
"""T-004-017: hostile terrain inputs: corrupt files, CRS mismatch, NaN/sentinel elevations, bad AOI, path escapes.

Requirements: FR-004-10, FR-004-11, FR-004-12, FR-004-13, FR-004-14.

Oracle: fixtures with one known defect each, written here (plan.md "FR-004-10 .. FR-004-14"); the reference decoders
(rasterio, laspy) are used only to confirm in the fixture builder that each defect is a real decoding failure; hand-counted
nodata fractions; wall-clock timing; a spy on the pixel and point readers for "before reading".

Expected API (package `pitstudio_studio.scene`, studio environment):
- `common.SceneStageError(Exception)` with `error_class` (one of the DC-004 classes) and a message that starts with
  `"<error_class>: "`; `terrain.SceneStageError` is the same class.
- `terrain.io.read_dem(path, *, source_id="", expected_sha256=None)` / `terrain.io.read_laz(...)`: raise
  `SceneStageError("input-corrupt")` naming the source id and the file name, within 5 s of opening, for an invalid
  header, a truncated file, a LAZ chunk-table or decompression error, a point count different from the header, a
  GeoTIFF that cannot be decoded, or a SHA-256 different from `expected_sha256`.
- `terrain.io.read_dem_metadata(path)`: header-only read (CRS record, extent) that never reads pixels.
- `terrain.io.check_crs_consistency(records)`: `records` maps an input name to its `crs` record (test_t_004_010);
  raises `crs-mismatch` listing both CRSs and the inputs when two inputs differ in horizontal CRS (NAD83 vs NAD83(2011)
  included) or in vertical CRS, unless `transformations` (SceneSpec `terrain.transformations`) declares the step.
- `terrain.io.resolve_input(path, *, roots, sha256)`: returns the resolved `Path`; raises `input-path` when the path
  resolves outside every root (`..`, another drive, UNC, a link leaving the root) and `input-corrupt` when the file's
  SHA-256 differs; the path check comes first and nothing is read before both pass.
- `terrain.grid.sanitise_elevations(values_m, *, nodata_m=None)`: float64 metres in, `.values` out (NaN where rejected)
  with `.rejected_non_finite`, `.rejected_sentinel` (equal to the declared nodata), `.rejected_out_of_range`
  (outside [-500, 9000] m, bounds inclusive).
- `terrain.grid.check_aoi(aoi_xy_m, *, cell_size_m, max_cells, extents_xy_m)`: `aoi-invalid` for an empty list, fewer
  than 3 vertices, a self-intersecting polygon, zero area, non-finite coordinates, or an AOI outside every extent
  `(x_min, y_min, x_max, y_max)`; `aoi-too-large` when ceil(width / cell) * ceil(height / cell) > max_cells.
- `terrain.build_terrain_grid(spec, inputs)`: calls the readers as `terrain.io.read_dem` / `terrain.io.read_laz`
  (module attributes) only after the AOI is accepted; `too-much-nodata` when the nodata fraction after filling exceeds
  `spec.terrain.max_nodata_frac`, the message reporting the fraction; `crs-mismatch` for an input without a CRS.
- `terrain.run(job) -> StageRun` (`.result`: a DC-002-02 stage result dict; `.digests`: output path -> SHA-256): a
  failure sets `status = "failed"`, `error_class = "unknown"`, `message` starting with `"<error_class>: "`, and writes
  nothing under `job["output_dir"]`.
"""

from __future__ import annotations

import os
import re
import struct
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, terrain  # noqa: E402

SRC = "usgs-3dep-bingham"


# ----------------------------------------------------------------------------------------------- fixture builders
def _good_dem(tmp: Path, name: str = "ok.tif", n: int = 129, wkt: str | None = None, **kw) -> Path:
    z = np.random.default_rng(1).uniform(1800.0, 1900.0, (n, n))
    return kit.write_dem(
        tmp / name, z, x_min=kit.E0, y_max=kit.N0 + n, cell=1.0, wkt=wkt or kit.crs_wkt("utm12-m"), **kw
    )


def _good_laz(tmp: Path, name: str = "ok.laz") -> Path:
    rng = np.random.default_rng(2)
    n = 2000
    return kit.write_laz(
        tmp / name,
        kit.E0 + rng.uniform(0, 50, n),
        kit.N0 + rng.uniform(0, 50, n),
        kit.Z0 + rng.uniform(0, 10, n),
        np.full(n, 2, np.uint8),
    )


def _corrupt_dems(tmp: Path) -> dict[str, Path]:
    good = _good_dem(tmp).read_bytes()
    out = {
        "truncated": good[: len(good) // 2],  # strips missing
        "garbage": b"this is not a tiff file " * 40,  # invalid header
        "empty": b"",
    }
    paths = {}
    for k, data in out.items():
        paths[k] = tmp / f"bad_{k}.tif"
        paths[k].write_bytes(data)
    return paths


def _corrupt_lazs(tmp: Path) -> dict[str, Path]:
    good = _good_laz(tmp).read_bytes()
    offset_to_points = struct.unpack_from("<I", good, 96)[0]
    count = bytearray(good)
    struct.pack_into("<Q", count, 247, struct.unpack_from("<Q", good, 247)[0] + 5)  # extended point count + 5
    chunk = bytearray(good)
    struct.pack_into("<q", chunk, offset_to_points, len(good) + 5000)  # chunk-table offset beyond the file
    sig = bytearray(good)
    sig[0:4] = b"XXXX"
    variants = {
        "truncated": good[: int(len(good) * 0.6)],
        "count": bytes(count),
        "chunk": bytes(chunk),
        "signature": bytes(sig),
        "empty": b"",
    }
    paths = {}
    for k, data in variants.items():
        paths[k] = tmp / f"bad_{k}.laz"
        paths[k].write_bytes(data)
    return paths


def _roots(tmp: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    store, data = tmp / "store", tmp / "data"
    store.mkdir()
    data.mkdir()
    monkeypatch.setenv("PITSTUDIO_STORE", str(store))
    monkeypatch.setenv("PITSTUDIO_DATA", str(data))
    return store, data


# ------------------------------------------------------------------------------------------------------- FR-004-10
@pytest.mark.req("FR-004-10")
@pytest.mark.parametrize("kind", ["truncated", "garbage", "empty"])
def test_corrupt_dem_fails_fast_with_input_corrupt(tmp_path: Path, kind: str) -> None:
    path = _corrupt_dems(tmp_path)[kind]
    t0 = time.perf_counter()
    with pytest.raises(common.SceneStageError) as exc:
        terrain.io.read_dem(path, source_id=SRC)
    assert time.perf_counter() - t0 < 5.0
    assert exc.value.error_class == "input-corrupt"
    assert str(exc.value).startswith("input-corrupt: ")
    assert SRC in str(exc.value) and path.name in str(exc.value)  # names the source id and the tile


@pytest.mark.req("FR-004-10")
@pytest.mark.parametrize("kind", ["truncated", "count", "chunk", "signature", "empty"])
def test_corrupt_laz_fails_fast_with_input_corrupt(tmp_path: Path, kind: str) -> None:
    path = _corrupt_lazs(tmp_path)[kind]
    t0 = time.perf_counter()
    with pytest.raises(common.SceneStageError) as exc:
        terrain.io.read_laz(path, source_id=SRC)
    assert time.perf_counter() - t0 < 5.0
    assert exc.value.error_class == "input-corrupt"
    assert SRC in str(exc.value) and path.name in str(exc.value)


@pytest.mark.req("FR-004-10")
def test_sha256_different_from_the_registry_is_input_corrupt(tmp_path: Path) -> None:
    dem, laz = _good_dem(tmp_path), _good_laz(tmp_path)
    for reader, path in ((terrain.io.read_dem, dem), (terrain.io.read_laz, laz)):
        with pytest.raises(common.SceneStageError) as exc:
            reader(path, source_id=SRC, expected_sha256="0" * 64)
        assert exc.value.error_class == "input-corrupt" and SRC in str(exc.value)
        reader(path, source_id=SRC, expected_sha256=kit.sha256_file(path))  # the right digest is accepted


@pytest.mark.req("FR-004-10")
def test_corrupt_input_through_the_stage_writes_no_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, data = _roots(tmp_path, monkeypatch)
    bad = _corrupt_dems(data)["truncated"]
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 100.0, 100.0)
    job = kit.make_job(store, "st10_terrain", spec, [(SRC, bad)])
    run = terrain.run(job)
    assert run.result["status"] == "failed" and run.result["error_class"] == "unknown"
    assert run.result["message"].startswith("input-corrupt: ")
    assert list(Path(job["output_dir"]).rglob("*")) == []  # nothing written, nothing to promote


# ------------------------------------------------------------------------------------------------------- FR-004-11
@pytest.mark.req("FR-004-11")
def test_different_datum_realisations_are_a_crs_mismatch_listing_both(tmp_path: Path) -> None:
    a = terrain.io.read_dem(_good_dem(tmp_path, "nad83.tif", wkt=kit.crs_wkt("utm12-m")))
    b = terrain.io.read_dem(_good_dem(tmp_path, "nad83_2011.tif", wkt=kit.crs_wkt("utm12-2011-m")))
    terrain.io.check_crs_consistency({"tile-a": a.crs, "tile-a2": a.crs})  # the same CRS is accepted
    with pytest.raises(common.SceneStageError) as exc:
        terrain.io.check_crs_consistency({"tile-a": a.crs, "tile-b": b.crs})
    msg = str(exc.value)
    assert exc.value.error_class == "crs-mismatch" and msg.startswith("crs-mismatch: ")
    assert "tile-a" in msg and "tile-b" in msg and "26912" in msg and "6341" in msg


@pytest.mark.req("FR-004-11")
def test_vertical_datum_mismatch_without_a_declared_transformation_is_rejected() -> None:
    horizontal = {"epsg": 26912}
    unit = {"name": "metre", "factor_to_m": 1.0}
    navd88 = {"horizontal": horizontal, "vertical": {"epsg": 5703}, "horizontal_unit": unit, "vertical_unit": unit}
    ngvd29 = {**navd88, "vertical": {"epsg": 5702}}
    with pytest.raises(common.SceneStageError) as exc:
        terrain.io.check_crs_consistency({"a": navd88, "b": ngvd29})
    assert exc.value.error_class == "crs-mismatch" and "5702" in str(exc.value) and "5703" in str(exc.value)


@pytest.mark.req("FR-004-11")
def test_input_without_a_crs_is_a_crs_mismatch(tmp_path: Path) -> None:
    path = kit.write_dem(
        tmp_path / "nocrs.tif", np.full((9, 9), 1800.0), x_min=kit.E0, y_max=kit.N0 + 9, cell=1.0, wkt=None
    )
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 9.0, 9.0)
    with pytest.raises(common.SceneStageError) as exc:
        terrain.build_terrain_grid(spec, {SRC: [path]})
    assert exc.value.error_class == "crs-mismatch" and "nocrs.tif" in str(exc.value)


# ------------------------------------------------------------------------------------------------------- FR-004-12
@pytest.mark.req("FR-004-12")
def test_nan_inf_sentinels_and_out_of_range_samples_become_nodata_and_are_counted() -> None:
    v = np.array(
        [
            1800.0,
            np.nan,
            np.inf,
            -np.inf,  # 1 NaN + 2 infinities = 3 non-finite
            -3.4028235e38,
            -3.4028235e38,  # the file's declared nodata sentinel, twice
            -9999.0,
            9000.01,
            -500.01,
            1.0e6,  # undeclared sentinel and out-of-range: 4
            -500.0,
            9000.0,
            0.0,  # bounds inclusive: valid
        ]
    )
    res = terrain.grid.sanitise_elevations(v, nodata_m=-3.4028235e38)
    assert (res.rejected_non_finite, res.rejected_sentinel, res.rejected_out_of_range) == (3, 2, 4)
    assert np.isnan(res.values).sum() == 9
    np.testing.assert_array_equal(res.values[[0, 10, 11, 12]], [1800.0, -500.0, 9000.0, 0.0])


@pytest.mark.req("FR-004-12")
def test_feet_are_converted_before_the_range_check() -> None:
    """30,000 US survey feet = 9144.018 m is out of range; 20,000 ft = 6096.012 m is valid."""
    metres = np.array([30000.0, 20000.0]) * (1200 / 3937)
    res = terrain.grid.sanitise_elevations(metres)
    assert np.isnan(res.values[0]) and res.values[1] == pytest.approx(6096.012192, abs=1e-6)
    assert res.rejected_out_of_range == 1


def _dem_with_hole(tmp: Path, hole: tuple[slice, slice], n: int = 20, nodata: float | None = -9999.0) -> Path:
    z = np.full((n, n), kit.Z0 + 10.0)
    z[hole] = -9999.0 if nodata is not None else np.nan
    return kit.write_dem(
        tmp / "holes.tif", z, x_min=kit.E0, y_max=kit.N0 + n, cell=1.0, wkt=kit.crs_wkt("utm12-m"), nodata=nodata
    )


@pytest.mark.req("FR-004-12")
def test_nodata_fraction_above_the_limit_after_filling_fails_and_reports_it(tmp_path: Path) -> None:
    """A 6 x 6 block (36 > 16 cells, never filled) in a 20 x 20 grid is 36/400 = 0.09 of the AOI (> 0.05)."""
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 20.0, 20.0)
    with pytest.raises(common.SceneStageError) as exc:
        terrain.build_terrain_grid(spec, {SRC: [_dem_with_hole(tmp_path, (slice(5, 11), slice(5, 11)))]})
    assert exc.value.error_class == "too-much-nodata"
    numbers = [float(m) for m in re.findall(r"\d+\.\d+", str(exc.value))]
    assert any(abs(x - 0.09) < 1e-3 for x in numbers), str(exc.value)


@pytest.mark.req("FR-004-12")
def test_exactly_five_percent_nodata_passes_and_just_above_fails(tmp_path: Path) -> None:
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 20.0, 20.0)
    ok = terrain.build_terrain_grid(spec, {SRC: [_dem_with_hole(tmp_path, (slice(9, 10), slice(0, 20)))]})  # 20 cells
    assert ok.counts["nodata_cells"] == 20 and ok.nodata_frac == pytest.approx(0.05)
    with pytest.raises(common.SceneStageError) as exc:  # 3 x 7 = 21 cells: 0.0525
        terrain.build_terrain_grid(spec, {SRC: [_dem_with_hole(tmp_path, (slice(8, 11), slice(3, 10)))]})
    assert exc.value.error_class == "too-much-nodata"


@pytest.mark.req("FR-004-12")
def test_rejected_samples_are_never_heights_and_are_counted_in_the_grid(tmp_path: Path) -> None:
    z = np.full((20, 20), kit.Z0 + 10.0)
    z[2, 2], z[4, 4], z[6, 6], z[8, 8], z[10, 10] = np.nan, np.inf, -3.4028235e38, -9999.0, 9500.0
    path = kit.write_dem(
        tmp_path / "bad.tif", z, x_min=kit.E0, y_max=kit.N0 + 20, cell=1.0, wkt=kit.crs_wkt("utm12-m"), nodata=None
    )
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 20.0, 20.0)
    grid = terrain.build_terrain_grid(spec, {SRC: [path]})
    assert grid.counts["rejected_non_finite"] == 2 and grid.counts["rejected_out_of_range"] == 3
    valid = grid.elevation[grid.valid_mask]
    assert np.isfinite(valid).all() and valid.max() < 9000.0 - kit.Z0 + 1e-3 and valid.min() > -500.0 - kit.Z0
    assert grid.valid_mask.sum() + grid.counts["nodata_cells"] == 400


# ------------------------------------------------------------------------------------------------------- FR-004-13
EXTENT = [(0.0, 0.0, 129.0, 129.0)]


@pytest.mark.req("FR-004-13")
@pytest.mark.parametrize(
    "aoi",
    [
        [],
        [[0.0, 0.0], [10.0, 10.0]],  # two vertices
        [[0.0, 0.0], [10.0, 10.0], [10.0, 0.0], [0.0, 10.0]],  # bow-tie
        [[0.0, 0.0], [5.0, 5.0], [10.0, 10.0]],  # zero area
        [[0.0, 0.0], [10.0, 0.0], [10.0, float("nan")], [0.0, 10.0]],
        [[0.0, 0.0], [10.0, 0.0], [float("inf"), 10.0], [0.0, 10.0]],
        [[1000.0, 1000.0], [1010.0, 1000.0], [1010.0, 1010.0], [1000.0, 1010.0]],  # outside every input
    ],
    ids=["empty", "two-vertices", "bow-tie", "zero-area", "nan", "inf", "outside-extent"],
)
def test_invalid_aoi_is_rejected(aoi: list[list[float]]) -> None:
    with pytest.raises(common.SceneStageError) as exc:
        terrain.grid.check_aoi(aoi, cell_size_m=1.0, max_cells=100_000_000, extents_xy_m=EXTENT)
    assert exc.value.error_class == "aoi-invalid" and str(exc.value).startswith("aoi-invalid: ")


@pytest.mark.req("FR-004-13")
def test_aoi_over_the_cell_cap_is_too_large_and_the_cap_itself_is_allowed() -> None:
    square = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
    terrain.grid.check_aoi(square, cell_size_m=1.0, max_cells=10_000, extents_xy_m=[(0, 0, 100, 100)])
    with pytest.raises(common.SceneStageError) as exc:
        terrain.grid.check_aoi(square, cell_size_m=1.0, max_cells=9_999, extents_xy_m=[(0, 0, 100, 100)])
    assert exc.value.error_class == "aoi-too-large"
    with pytest.raises(common.SceneStageError) as exc:  # a finer cell size makes the same AOI too large: 400 x 400
        terrain.grid.check_aoi(square, cell_size_m=0.25, max_cells=100_000, extents_xy_m=[(0, 0, 100, 100)])
    assert exc.value.error_class == "aoi-too-large"


@pytest.mark.req("FR-004-13")
@pytest.mark.parametrize("case", ["bow-tie", "outside", "too-large", "zero-area"])
def test_bad_aoi_is_rejected_before_any_pixel_or_point_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    def boom(*a: object, **k: object) -> None:
        raise AssertionError("a pixel or point reader was called before the AOI was accepted")

    dem = _good_dem(tmp_path)  # site extent x, y in [0, 129]
    monkeypatch.setattr(terrain.io, "read_dem", boom)
    monkeypatch.setattr(terrain.io, "read_laz", boom)
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 10.0, 10.0)
    expected = "aoi-invalid"
    if case == "bow-tie":
        spec["terrain"]["aoi_xy_m"] = [[0.0, 0.0], [10.0, 10.0], [10.0, 0.0], [0.0, 10.0]]
    elif case == "zero-area":
        spec["terrain"]["aoi_xy_m"] = [[0.0, 0.0], [5.0, 5.0], [10.0, 10.0]]
    elif case == "outside":
        spec["terrain"]["aoi_xy_m"] = [[500.0, 500.0], [510.0, 500.0], [510.0, 510.0], [500.0, 510.0]]
    else:
        spec["terrain"]["max_cells"] = 1000  # a 100 x 100 AOI is 10,000 cells
        spec["terrain"]["aoi_xy_m"] = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
        expected = "aoi-too-large"
    with pytest.raises(common.SceneStageError) as exc:
        terrain.build_terrain_grid(spec, {SRC: [dem]})
    assert exc.value.error_class == expected


# ------------------------------------------------------------------------------------------------------- FR-004-14
def _other_drive(path: Path) -> str | None:
    if os.name != "nt":
        return None
    here = path.drive[:1].upper()
    return next(f"{d}:/pitstudio_other/x.tif" for d in "ZYXWV" if d != here)


@pytest.mark.req("FR-004-14")
def test_input_inside_the_roots_is_accepted(tmp_path: Path) -> None:
    store, data = tmp_path / "store", tmp_path / "data"
    store.mkdir(), data.mkdir()
    f = _good_dem(data)
    got = terrain.io.resolve_input(f.as_posix(), roots=[store, data], sha256=kit.sha256_file(f))
    assert Path(got).resolve() == f.resolve()


@pytest.mark.req("FR-004-14")
def test_paths_that_leave_the_roots_are_input_path(tmp_path: Path) -> None:
    store, data, outside = tmp_path / "store", tmp_path / "data", tmp_path / "outside"
    for d in (store, data, outside):
        d.mkdir()
    secret = _good_dem(outside, "secret.tif")
    digest = kit.sha256_file(secret)  # the digest is right: only the location is wrong
    link = data / "link"
    kit.make_link(link, outside)
    candidates = [
        f"{data.as_posix()}/../outside/secret.tif",  # '..' segments
        f"{data.as_posix()}/sub/../../outside/secret.tif",
        (link / "secret.tif").as_posix(),  # a link leaving the root
        "//server/share/secret.tif",  # UNC
        "\\\\server\\share\\secret.tif",
        secret.as_posix(),  # absolute but outside both roots
    ]
    if (drive := _other_drive(tmp_path)) is not None:
        candidates.append(drive)  # another drive
    for cand in candidates:
        with pytest.raises(common.SceneStageError) as exc:
            terrain.io.resolve_input(cand, roots=[store, data], sha256=digest)
        assert exc.value.error_class == "input-path", cand
        assert str(exc.value).startswith("input-path: ")


@pytest.mark.req("FR-004-14")
def test_digest_different_from_the_job_specification_is_input_corrupt(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    f = _good_dem(data)
    with pytest.raises(common.SceneStageError) as exc:
        terrain.io.resolve_input(f.as_posix(), roots=[data], sha256="f" * 64)
    assert exc.value.error_class == "input-corrupt"


@pytest.mark.req("FR-004-14")
def test_stage_refuses_an_escaping_input_before_reading_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store, data = _roots(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = _good_dem(outside, "secret.tif")
    spec = kit.with_aoi(kit.scene_spec(), 0.0, 0.0, 10.0, 10.0)
    job = kit.make_job(store, "st10_terrain", spec, [(SRC, secret)])
    job["inputs"][0]["path"] = f"{data.as_posix()}/../outside/secret.tif"

    def boom(*a: object, **k: object) -> None:
        raise AssertionError("the escaping input was read")

    monkeypatch.setattr(terrain.io, "read_dem", boom)
    run = terrain.run(job)
    assert run.result["status"] == "failed" and run.result["message"].startswith("input-path: ")
    assert list(Path(job["output_dir"]).rglob("*")) == []
