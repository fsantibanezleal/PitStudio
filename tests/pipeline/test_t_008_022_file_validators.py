# ruff: noqa: E501, PT018
"""T-008-022: raster, point-cloud, vector and image/mask validators and their rejection reports.

Requirements: FR-008-23, FR-008-24.

Spec: specs/008-data-pipeline/spec.md FR-008-23 (rasters: CRS present, cell size in metres > 0 and finite, declared dtype,
declared nodata, extent inside the area of interest; point clouds: CRS present, point count > 0, classification codes
present, bounds inside the area of interest; vector layers: valid geometries, CRS present, required attributes present;
images and masks: 512 x 512 RGB JPEG images, indexed `P`-mode masks with 0 = background and k = instance k, exactly one mask
per image) and FR-008-24 (a rejection names the file, the property, the found value and the expected value).

Oracle: fixtures written by hand in the test kit with known properties and no reader library involved in producing them:
a GeoTIFF whose tags are written with Pillow (GeoTIFF 1.0 tags 33550, 33922, 34735, 42113), a LAS 1.2 file written with
`struct` (ASPRS LAS 1.2 header, 227 bytes), a GeoPackage written with `sqlite3` (OGC GeoPackage 1.3 tables and geometry
blob), JPEG and indexed PNG images written with Pillow. The bow-tie polygon (0,0)-(10,10)-(10,0)-(0,10) is the textbook
self-intersecting (OGC-invalid) ring; an unclosed ring has first point != last point.

Expected API of the implementation (module `pitstudio_pipeline.ingest.files`; every validator returns None for a valid file
and raises `pitstudio_pipeline.errors.IngestionRejected` otherwise, with `.violations`: dicts with the keys of the
ingestion-report `violation` (`file`, `row`, `pixel`, `field`, `field_kind`, `value`, `expected`, `rule`, `unit`); for
file-level properties `field_kind` is `"property"`, `field` the property name below, `value` the found value, `expected`
the expected value as text, `file` the `file` argument):
- `validate_raster(path, *, aoi, dtype, nodata, file)`: `aoi = (xmin, ymin, xmax, ymax)` in the raster CRS; `dtype` such as
  "float32"; `nodata` a float. Properties: `crs`, `cell_size_m`, `dtype`, `nodata`, `extent`.
- `validate_point_cloud(path, *, aoi, file)`: properties `crs`, `point_count`, `classification` (rejected when every point has
  class 0, i.e. no classification codes are present), `bounds`.
- `validate_vector(path, *, required_attributes, aoi=None, file)`: properties `crs`, `geometry` (violation `row` = 0-based
  feature index), and one violation naming each missing attribute (its name appears in `field`, `expected` or `value`).
- `validate_image(path, *, size=(512, 512), file)`: properties `format` (JPEG), `size`, `mode` (RGB).
- `validate_mask(path, *, size=(512, 512), file)`: properties `format` (PNG), `size`, `mode` (indexed `P`).
- `validate_image_mask_set(images, masks, *, file_prefix)`: `images` and `masks` are lists of paths paired by file stem;
  an image without a mask, a mask without an image or two masks for one image is a violation (`field` `mask`).
"""

from __future__ import annotations

from pathlib import Path

import _p008_kit as kit
import numpy as np
import pytest
from pitstudio_pipeline.errors import IngestionRejected
from pitstudio_pipeline.ingest import files as F

AOI = (399_000.0, 4_499_000.0, 401_000.0, 4_501_000.0)  # contains the fixtures below
OUTSIDE = (0.0, 0.0, 10.0, 10.0)
REL = "raw/t/f"


def props(exc: IngestionRejected) -> dict[str, dict]:
    return {v["field"]: v for v in exc.violations}


def reject(fn, *a, **kw) -> IngestionRejected:
    with pytest.raises(IngestionRejected) as info:
        fn(*a, **kw)
    return info.value


# ------------------------------------------------------------------------------------------------ rasters
def dem(tmp: Path, **kw) -> Path:
    arr = kw.pop("array", np.arange(16, dtype=np.float32).reshape(4, 4))
    return kit.write_geotiff(tmp / "d.tif", arr, **kw)


def good_raster(tmp: Path, **kw):
    return dict(path=dem(tmp, **kw), aoi=AOI, dtype="float32", nodata=-9999.0, file=REL + ".tif")


@pytest.mark.req("FR-008-23")
def test_valid_raster_is_accepted(tmp_path: Path) -> None:
    assert F.validate_raster(**good_raster(tmp_path, nodata=-9999.0)) is None


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize(
    ("kw", "prop"),
    [
        ({"epsg": None}, "crs"),
        ({"cell": None}, "cell_size_m"),
        ({"cell": (0.0, 0.0)}, "cell_size_m"),
        ({"cell": (-1.0, -1.0)}, "cell_size_m"),
        ({"cell": (float("nan"), float("nan"))}, "cell_size_m"),
        ({"cell": (float("inf"), float("inf"))}, "cell_size_m"),
        ({"nodata": None}, "nodata"),
        ({"nodata": -1.0}, "nodata"),
        ({"array": np.arange(16, dtype=np.uint16).reshape(4, 4)}, "dtype"),
        ({"origin": (10_000_000.0, 4_500_000.0)}, "extent"),
    ],
    ids=[
        "no-crs",
        "no-scale",
        "zero-cell",
        "negative-cell",
        "nan-cell",
        "inf-cell",
        "no-nodata",
        "wrong-nodata",
        "wrong-dtype",
        "outside-aoi",
    ],
)
def test_raster_violation_names_file_property_found_and_expected(kw: dict, prop: str, tmp_path: Path) -> None:
    kw = {"nodata": -9999.0, **kw}
    exc = reject(F.validate_raster, **good_raster(tmp_path, **kw))
    v = props(exc)[prop]
    assert v["file"] == REL + ".tif" and v["field_kind"] == "property"
    assert v["expected"] is not None and str(v["expected"]) != ""
    assert "value" in v  # the found value


@pytest.mark.req("FR-008-24")
def test_raster_dtype_and_nodata_report_found_and_expected_values(tmp_path: Path) -> None:
    exc = reject(F.validate_raster, **good_raster(tmp_path, array=np.zeros((4, 4), dtype=np.uint16), nodata=-1.0))
    v = props(exc)
    assert "uint16" in str(v["dtype"]["value"]) and "float32" in str(v["dtype"]["expected"])
    assert float(v["nodata"]["value"]) == -1.0 and "-9999" in str(v["nodata"]["expected"])


@pytest.mark.req("FR-008-24")
def test_all_raster_violations_are_listed(tmp_path: Path) -> None:
    exc = reject(
        F.validate_raster, **good_raster(tmp_path, epsg=None, array=np.zeros((4, 4), dtype=np.uint16), nodata=None)
    )
    assert {"crs", "dtype", "nodata"} <= set(props(exc))
    full = {
        "schema_version": "1.0",
        "source": "t",
        "stage": "s10_preprocess",
        "run_id": "20261011T120000Z-t",
        "created": kit.NOW_TEXT,
        "status": "rejected",
        "files": [
            {
                "path": REL + ".tif",
                "sha256": kit.HEX64,
                "validator": "raster",
                "schema_name": "dem_geotiff",
                "status": "rejected",
                "records": None,
            }
        ],
        "violations": exc.violations,
        "outputs": [],
    }
    assert kit.schema_errors("ingestion-report.schema.json", full) == []


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize("content", [b"", b"II*\x00", b"not a tiff at all" * 50])
def test_corrupt_raster_is_rejected_with_a_report(content: bytes, tmp_path: Path) -> None:
    p = tmp_path / "bad.tif"
    p.write_bytes(content)
    exc = reject(F.validate_raster, path=p, aoi=AOI, dtype="float32", nodata=-9999.0, file=REL + ".tif")
    assert exc.violations and all(v["file"] == REL + ".tif" for v in exc.violations)


# ------------------------------------------------------------------------------------------------ point clouds
def las(tmp: Path, **kw) -> Path:
    xyz = kw.pop(
        "xyz",
        np.array(
            [[400_000.0, 4_500_000.0, 1500.0], [400_010.0, 4_500_020.0, 1510.0], [400_020.0, 4_500_030.0, 1520.0]]
        ),
    )
    classes = kw.pop("classes", [2, 2, 5])
    return kit.write_las(tmp / "p.las", xyz, classes, **kw)


@pytest.mark.req("FR-008-23")
def test_valid_point_cloud_is_accepted(tmp_path: Path) -> None:
    assert F.validate_point_cloud(las(tmp_path), aoi=AOI, file=REL + ".las") is None


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize(
    ("kw", "prop"),
    [
        ({"epsg": None}, "crs"),
        ({"xyz": np.zeros((0, 3)), "classes": []}, "point_count"),
        ({"classes": [0, 0, 0]}, "classification"),
        ({"xyz": np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])}, "bounds"),
    ],
    ids=["no-crs", "no-points", "no-classification", "outside-aoi"],
)
def test_point_cloud_violation_names_the_property(kw: dict, prop: str, tmp_path: Path) -> None:
    exc = reject(F.validate_point_cloud, las(tmp_path, **kw), aoi=AOI, file=REL + ".las")
    v = props(exc)[prop]
    assert v["file"] == REL + ".las" and v["field_kind"] == "property" and v["expected"] is not None
    if prop == "point_count":
        assert v["value"] == 0


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize("cut", [0, 10, 226, 300])
def test_truncated_point_cloud_is_rejected(cut: int, tmp_path: Path) -> None:
    p = las(tmp_path)
    p.write_bytes(p.read_bytes()[:cut])
    exc = reject(F.validate_point_cloud, p, aoi=AOI, file=REL + ".las")
    assert exc.violations


# ------------------------------------------------------------------------------------------------ vector layers
@pytest.mark.req("FR-008-23")
def test_valid_vector_layer_is_accepted(tmp_path: Path) -> None:
    p = kit.write_gpkg(tmp_path / "v.gpkg", [kit.SQUARE])
    assert F.validate_vector(p, required_attributes=["name"], file=REL + ".gpkg") is None


@pytest.mark.req("FR-008-24")
def test_invalid_geometries_are_reported_with_the_feature_row(tmp_path: Path) -> None:
    p = kit.write_gpkg(tmp_path / "v.gpkg", [kit.SQUARE, kit.BOWTIE, kit.UNCLOSED])
    exc = reject(F.validate_vector, p, required_attributes=["name"], file=REL + ".gpkg")
    rows = sorted(v["row"] for v in exc.violations if v["field"] == "geometry")
    assert rows == [1, 2]
    assert all(v["file"] == REL + ".gpkg" for v in exc.violations)


@pytest.mark.req("FR-008-24")
def test_missing_crs_is_reported(tmp_path: Path) -> None:
    p = kit.write_gpkg(tmp_path / "v.gpkg", [kit.SQUARE], srs_id=None)
    exc = reject(F.validate_vector, p, required_attributes=["name"], file=REL + ".gpkg")
    assert "crs" in props(exc)


@pytest.mark.req("FR-008-24")
def test_missing_required_attribute_is_named(tmp_path: Path) -> None:
    p = kit.write_gpkg(tmp_path / "v.gpkg", [kit.SQUARE], attributes=("label",))
    exc = reject(F.validate_vector, p, required_attributes=["name", "label"], file=REL + ".gpkg")
    text = " ".join(f"{v['field']} {v['expected']} {v['value']}" for v in exc.violations)
    assert "name" in text


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize("content", [b"", b"SQLite format 3\x00" + b"\0" * 20, kit.payload(4096, 1)])
def test_corrupt_vector_file_is_rejected(content: bytes, tmp_path: Path) -> None:
    p = tmp_path / "bad.gpkg"
    p.write_bytes(content)
    exc = reject(F.validate_vector, p, required_attributes=["name"], file=REL + ".gpkg")
    assert exc.violations


# ------------------------------------------------------------------------------------------------ images and masks
def labels(n_inst: int = 3) -> np.ndarray:
    a = np.zeros((512, 512), dtype=np.uint8)
    for k in range(1, n_inst + 1):
        a[20 * k : 20 * k + 10, 30 : 40 + k] = k
    return a


@pytest.mark.req("FR-008-23")
def test_valid_image_and_mask_are_accepted(tmp_path: Path) -> None:
    assert F.validate_image(kit.write_rgb_jpeg(tmp_path / "a.jpg"), file=REL + ".jpg") is None
    assert F.validate_mask(kit.write_indexed_mask(tmp_path / "a.png", labels()), file=REL + ".png") is None


@pytest.mark.req("FR-008-24")
def test_mask_with_instance_gaps_is_valid(tmp_path: Path) -> None:
    a = labels(1)
    a[100:110, 100:110] = 7  # indices 2..6 unused: gaps are allowed (spec section 7: unnamed instances)
    assert F.validate_mask(kit.write_indexed_mask(tmp_path / "a.png", a), file=REL + ".png") is None


@pytest.mark.req("FR-008-24")
@pytest.mark.parametrize(
    ("size", "mode", "prop"),
    [((511, 512), "RGB", "size"), ((512, 513), "RGB", "size"), ((512, 512), "L", "mode"), ((1, 1), "RGB", "size")],
    ids=["narrow", "tall", "grayscale", "tiny"],
)
def test_image_violations(size: tuple[int, int], mode: str, prop: str, tmp_path: Path) -> None:
    p = kit.write_rgb_jpeg(tmp_path / "a.jpg", size=size, mode=mode)
    exc = reject(F.validate_image, p, file=REL + ".jpg")
    v = props(exc)[prop]
    assert v["file"] == REL + ".jpg" and v["field_kind"] == "property" and v["expected"] is not None


@pytest.mark.req("FR-008-24")
def test_image_that_is_a_png_not_a_jpeg_is_rejected(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "a.jpg"
    Image.new("RGB", (512, 512)).save(p, format="PNG")  # a PNG hidden under a .jpg name
    assert "format" in props(reject(F.validate_image, p, file=REL + ".jpg"))


@pytest.mark.req("FR-008-24")
def test_truncated_jpeg_is_rejected(tmp_path: Path) -> None:
    p = kit.write_rgb_jpeg(tmp_path / "a.jpg")
    p.write_bytes(p.read_bytes()[:100])
    assert reject(F.validate_image, p, file=REL + ".jpg").violations


@pytest.mark.req("FR-008-24")
def test_mask_must_be_indexed_p_mode_of_the_right_size(tmp_path: Path) -> None:
    gray = kit.write_indexed_mask(tmp_path / "g.png", labels(), mode="L")
    assert "mode" in props(reject(F.validate_mask, gray, file=REL + ".png"))
    small = kit.write_indexed_mask(tmp_path / "s.png", labels()[:256, :256])
    assert "size" in props(reject(F.validate_mask, small, file=REL + ".png"))


@pytest.mark.req("FR-008-24")
def test_exactly_one_mask_per_image(tmp_path: Path) -> None:
    imgs = [kit.write_rgb_jpeg(tmp_path / f"{n}.jpg") for n in ("a", "b", "c")]
    mask_dir = tmp_path / "m"
    mask_dir.mkdir()
    masks = [kit.write_indexed_mask(mask_dir / f"{n}.png", labels()) for n in ("a", "b")]  # c has none
    exc = reject(F.validate_image_mask_set, imgs, masks, file_prefix="raw/t")
    assert any(v["field"] == "mask" and v["file"].endswith("c.jpg") for v in exc.violations)
    orphan = kit.write_indexed_mask(mask_dir / "z.png", labels())
    masks_ok = [*masks, kit.write_indexed_mask(mask_dir / "c.png", labels())]
    exc2 = reject(F.validate_image_mask_set, imgs, [*masks_ok, orphan], file_prefix="raw/t")
    assert any(v["field"] == "mask" and v["file"].endswith("z.png") for v in exc2.violations)
    assert F.validate_image_mask_set(imgs, masks_ok, file_prefix="raw/t") is None
