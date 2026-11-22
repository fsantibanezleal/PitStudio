# ruff: noqa: E501, PT018
"""T-004-097: the orthophoto albedo of the terrain grid, with its manifest source and digests.

Requirements: FR-004-48.

Oracle: linear colour ramps over the site frame (`ortho_kit.ramp`): a bilinear resample of a linear function is exact, so
the value of each grid cell is `60 + 2 x`, `120 + 3 y` (x, y: the cell centre in the site frame) to within the 8-bit
rounding of the source pixels; Pillow as the reference JPEG decoder; hashlib for digests; the exact US survey foot
(1200/3937 m) for a file in feet.

Expected API (package `pitstudio_studio.scene.terrain`, studio environment): with `terrain.imagery` in the scene
specification the stage `st10_terrain` (`terrain.run(job)`) takes the files of the source `usda-naip-bingham` among its
inputs, reads the acquisition year of each file from its name (`..._<yyyymmdd>.tif`), keeps the files of the year nearest
`terrain.sources[0].epoch` (a tie goes to the earlier year), resamples bands 1 to 3 bilinearly to the grid (cell centres)
through the CRS of the file, and writes `terrain/albedo/ortho.jpg` (8-bit RGB JPEG, one pixel per grid cell) or, when a side
exceeds `imagery.MAX_SIDE_PX`, one image `terrain/albedo/<tile id>.jpg` per LOD-0 tile. `terrain/records.json` gets a source
of role `imagery` and `terrain.albedo`. A cell no file covers fails the stage (`input-corrupt`, "uncovered"); an optional
source without data is `not_run` with a reason. The pure functions: `imagery.choose_year(years, dem_year)` and
`imagery.resample_orthophoto(files, rows=, cols=, x_min_m=, y_max_m=, cell_size_m=, origin=)`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import ortho_kit as ok  # noqa: E402
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import terrain  # noqa: E402
from pitstudio_studio.scene.common import SceneStageError  # noqa: E402
from pitstudio_studio.scene.terrain import imagery  # noqa: E402

ORIGIN = kit.scene_spec()["site"]["origin"]


def _expected(rows: int = 12, cols: int = 12) -> np.ndarray:
    xs = np.arange(cols) + 0.5
    ys = rows - (np.arange(rows) + 0.5)
    r = 60.0 + 2.0 * xs[None, :] + 0.0 * ys[:, None]
    g = 120.0 + 3.0 * ys[:, None] + 0.0 * xs[None, :]
    return np.stack([r, g, np.full_like(r, 40.0)], axis=-1)


def _cover(tmp: Path, name: str, **kw) -> Path:
    """A 0.5 m orthophoto covering x -5..17 and y -5..17 (site frame), more than the 12 m AOI."""
    args = {"x_min": ok.E0 - 5.0, "y_max": ok.N0 + 17.0, "cell": 0.5, "rows": 44, "cols": 44}
    args.update(kw)
    return ok.write_ortho(tmp / name, **args)


def _run(job: dict):
    run = terrain.run(job)
    return run, Path(job["output_dir"])


def _records(out: Path) -> dict:
    return json.loads((out / "terrain" / "records.json").read_text(encoding="utf-8"))


def _jpeg(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
        return np.asarray(im, dtype=np.float64)


@pytest.mark.req("FR-004-48")
def test_resample_is_bilinear_at_the_grid_cell_centres_and_ignores_the_fourth_band(tmp_path: Path) -> None:
    src = _cover(tmp_path, ok.naip_name(2018))
    got = imagery.resample_orthophoto(
        [src], rows=12, cols=12, x_min_m=0.0, y_max_m=12.0, cell_size_m=1.0, origin=ORIGIN
    )
    assert got.rgb.shape == (12, 12, 3) and got.rgb.dtype == np.uint8
    assert np.abs(got.rgb.astype(np.float64) - _expected()).max() <= 1.0
    assert got.ground_resolution_m == pytest.approx(0.5)


@pytest.mark.req("FR-004-48")
def test_the_crs_is_read_from_the_file_a_us_survey_foot_image_lands_in_the_same_place(tmp_path: Path) -> None:
    import pyproj

    wkt = pyproj.CRS.from_proj4("+proj=utm +zone=12 +datum=NAD83 +units=us-ft +no_defs").to_wkt()
    ft = 1.0 / kit.FT_US  # feet per metre
    src = ok.write_ortho(
        tmp_path / ok.naip_name(2018),
        x_min=(ok.E0 - 5.0) * ft,
        y_max=(ok.N0 + 17.0) * ft,
        cell=0.5 * ft,
        rows=44,
        cols=44,
        wkt=wkt,
        to_site=lambda v: v * kit.FT_US,
    )
    got = imagery.resample_orthophoto(
        [src], rows=12, cols=12, x_min_m=0.0, y_max_m=12.0, cell_size_m=1.0, origin=ORIGIN
    )
    assert np.abs(got.rgb.astype(np.float64) - _expected()).max() <= 1.0
    assert got.ground_resolution_m == pytest.approx(0.5, abs=1e-6)


@pytest.mark.req("FR-004-48")
def test_two_tiles_are_mosaicked_without_a_seam(tmp_path: Path) -> None:
    left = _cover(tmp_path, "a_" + ok.naip_name(2018), cols=22)  # x -5 .. 6
    right = _cover(tmp_path, "b_" + ok.naip_name(2018), x_min=ok.E0 + 6.0, cols=22)  # x 6 .. 17
    got = imagery.resample_orthophoto(
        [left, right], rows=12, cols=12, x_min_m=0.0, y_max_m=12.0, cell_size_m=1.0, origin=ORIGIN
    )
    assert np.abs(got.rgb.astype(np.float64) - _expected()).max() <= 1.0


@pytest.mark.req("FR-004-48")
def test_a_cell_no_image_covers_fails_and_is_never_filled(tmp_path: Path) -> None:
    half = _cover(tmp_path, ok.naip_name(2018), cols=22)  # covers x -5 .. 6 only
    with pytest.raises(SceneStageError) as caught:
        imagery.resample_orthophoto(
            [half], rows=12, cols=12, x_min_m=0.0, y_max_m=12.0, cell_size_m=1.0, origin=ORIGIN
        )
    assert caught.value.error_class == "input-corrupt" and "uncovered" in caught.value.detail
    assert "72" in caught.value.detail  # 6 of 12 columns, 12 rows: 72 cells


@pytest.mark.req("FR-004-48")
def test_the_stage_fails_on_a_hole_and_promotes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    half = _cover(tmp_path, ok.naip_name(2018), cols=22)
    run, out = _run(ok.dem_job(tmp_path, monkeypatch, [half]))
    assert run.result["status"] == "failed"
    assert run.result["message"].startswith("input-corrupt:") and "uncovered" in run.result["message"]
    assert not (out / "terrain").exists() and not (out / "result.json").exists()


@pytest.mark.req("FR-004-48")
@pytest.mark.parametrize(
    ("epoch", "wanted"),
    [(2018, 2018), (2019, 2018), (2020, 2021), (2017, 2016), (2030, 2021), (2000, 2016)],
)
def test_the_year_nearest_the_dem_year_is_used_and_a_tie_goes_to_the_earlier(epoch: int, wanted: int) -> None:
    years = [(Path(ok.naip_name(y)), y) for y in (2016, 2018, 2021)]
    assert imagery.choose_year(years, epoch) == wanted


@pytest.mark.req("FR-004-48")
def test_the_stage_mosaics_only_the_files_of_the_chosen_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def flat(level: float):
        return lambda e, n: (np.full_like(e, level), np.full_like(e, level), np.full_like(e, level))

    files = [
        _cover(tmp_path, ok.naip_name(y), colour=flat(level))
        for y, level in ((2016, 20.0), (2018, 100.0), (2021, 200.0))
    ]
    run, out = _run(ok.dem_job(tmp_path, monkeypatch, files, epoch=2019))
    assert run.result["status"] == "succeeded", run.result["message"]
    pixels = _jpeg(out / "terrain" / "albedo" / "ortho.jpg")
    assert np.abs(pixels - 100.0).max() <= 3.0  # 2018 is one year from 2019, 2021 two
    albedo = _records(out)["terrain"]["albedo"]
    assert (albedo["year"], albedo["dem_year"]) == (2018, 2019)


@pytest.mark.req("FR-004-48")
def test_the_albedo_is_an_8_bit_rgb_jpeg_with_one_pixel_per_cell_and_the_ramp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run, out = _run(ok.dem_job(tmp_path, monkeypatch, [_cover(tmp_path, ok.naip_name(2018))]))
    assert run.result["status"] == "succeeded", run.result["message"]
    path = out / "terrain" / "albedo" / "ortho.jpg"
    assert path.is_file() and path.stat().st_size < 100 * 1024 * 1024
    pixels = _jpeg(path)
    assert pixels.shape == (12, 12, 3)
    assert np.abs(pixels - _expected()).max() <= 4.0  # JPEG at quality 95, 4:4:4
    assert "terrain/albedo/ortho.jpg" in run.digests


@pytest.mark.req("FR-004-48")
def test_the_manifest_records_the_imagery_source_its_year_resolution_and_every_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _cover(tmp_path, ok.naip_name(2018))
    job = ok.dem_job(tmp_path, monkeypatch, [src])
    run, out = _run(job)
    assert run.result["status"] == "succeeded", run.result["message"]
    records = _records(out)
    source = next(s for s in records["sources"] if s["id"] == ok.IMG)
    assert source["role"] == "imagery" and source["status"] == "used" and source["epoch"] == 2018
    assert source["spdx"] == "LicenseRef-USGov-PD" and source["licence_class"] == "public-domain"
    assert source["redistribution"] == "redistributable" and source["attribution"].startswith("Imagery:")
    albedo = records["terrain"]["albedo"]
    assert albedo["source"] == ok.IMG and albedo["year"] == 2018 and albedo["dem_year"] == 2018
    assert albedo["ground_resolution_m"] == pytest.approx(0.5)
    image = out / "terrain" / "albedo" / "ortho.jpg"
    assert albedo["images"] == [
        {"path": "terrain/albedo/ortho.jpg", "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    ]
    assert albedo["inputs"] == [
        {"path": f"{ok.IMG}/{src.name}", "sha256": hashlib.sha256(src.read_bytes()).hexdigest()}
    ]
    assert [s["id"] for s in records["sources"]][0] == ok.SRC  # the DEM source stays first (primary grid)
    assert not kit.has_absolute_path_text(json.dumps(records))
    validator = kit.validator("scene-manifest.schema.json")
    for name, doc in (("albedo", albedo), ("source", source)):
        checker = validator.evolve(schema={"$ref": validator.schema["$id"] + f"#/$defs/{name}"})
        assert [e.message for e in checker.iter_errors(doc)] == [], name


@pytest.mark.req("FR-004-48")
def test_an_optional_source_without_data_is_not_run_with_a_reason_and_a_required_one_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    optional = [{"id": ok.IMG, "kind": "orthophoto", "optional": True}]
    run, out = _run(ok.dem_job(tmp_path, monkeypatch, [], imagery=optional))
    assert run.result["status"] == "succeeded", run.result["message"]
    source = next(s for s in _records(out)["sources"] if s["id"] == ok.IMG)
    assert source["status"] == "not_run" and source["role"] == "imagery"
    assert 0 < len(source["reason"]) <= 256 and "\n" not in source["reason"]
    assert "albedo" not in _records(out)["terrain"] and not (out / "terrain" / "albedo").exists()
    required = tmp_path / "req"
    required.mkdir()
    run2, _ = _run(ok.dem_job(required, monkeypatch, [], imagery=[{"id": ok.IMG, "kind": "orthophoto", "optional": False}]))
    assert run2.result["status"] == "failed" and run2.result["message"].startswith("input-corrupt:")


@pytest.mark.req("FR-004-48")
def test_a_scene_without_imagery_is_built_as_before(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job = ok.dem_job(tmp_path, monkeypatch, [], imagery=[])
    del job["params"]["terrain"]["imagery"]
    run, out = _run(job)
    assert run.result["status"] == "succeeded", run.result["message"]
    assert not (out / "terrain" / "albedo").exists()
    assert [s["id"] for s in _records(out)["sources"]] == [ok.SRC]


@pytest.mark.req("FR-004-48")
def test_two_builds_are_bitwise_identical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _cover(tmp_path, ok.naip_name(2018))
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    a = terrain.run(ok.dem_job(one, monkeypatch, [src]))
    b = terrain.run(ok.dem_job(two, monkeypatch, [src]))
    assert a.result["status"] == b.result["status"] == "succeeded"
    assert a.digests == b.digests and "terrain/albedo/ortho.jpg" in a.digests


@pytest.mark.req("FR-004-48")
def test_a_larger_extent_is_written_as_one_image_per_lod0_tile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imagery, "MAX_SIDE_PX", 100)

    def ramp_x(e, n):
        return 20.0 + 0.5 * e, np.full_like(e, 90.0), np.full_like(e, 40.0)

    src = ok.write_ortho(
        tmp_path / ok.naip_name(2018),
        x_min=ok.E0 - 5.0,
        y_max=ok.N0 + 25.0,
        cell=0.5,
        rows=60,
        cols=620,
        colour=ramp_x,
    )
    run, out = _run(ok.dem_job(tmp_path, monkeypatch, [src], width=300, height=20))
    assert run.result["status"] == "succeeded", run.result["message"]
    folder = out / "terrain" / "albedo"
    assert sorted(p.name for p in folder.iterdir()) == ["0-1-0-0.jpg", "0-1-1-0.jpg"] and not (folder / "ortho.jpg").exists()
    first, second = _jpeg(folder / "0-1-0-0.jpg"), _jpeg(folder / "0-1-1-0.jpg")
    assert first.shape == (20, 257, 3) and second.shape == (20, 44, 3)  # tile 1 starts at column 256 of 300
    assert abs(first[5, 100, 0] - (20.0 + 0.5 * 100.5)) <= 3.0
    assert abs(second[5, 10, 0] - (20.0 + 0.5 * 266.5)) <= 3.0
    images = _records(out)["terrain"]["albedo"]["images"]
    assert [i["path"] for i in images] == ["terrain/albedo/0-1-0-0.jpg", "terrain/albedo/0-1-1-0.jpg"]
    for item in images:
        assert item["sha256"] == hashlib.sha256((out / item["path"]).read_bytes()).hexdigest()


@pytest.mark.req("FR-004-48")
def test_a_file_without_a_readable_acquisition_year_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _cover(tmp_path, "scan.tif")
    run, _ = _run(ok.dem_job(tmp_path, monkeypatch, [src]))
    assert run.result["status"] == "failed" and run.result["message"].startswith("input-corrupt:")
    assert "year" in run.result["message"]


def test_the_jpeg_helper_round_trips() -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8)).save(buf, format="JPEG")
    assert buf.getvalue()[:2] == b"\xff\xd8"
