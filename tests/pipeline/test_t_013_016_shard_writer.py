# ruff: noqa: E501, PT018, PT011
"""T-013-016: shard writer: Parquet, Zarr v3 chunks, PNG, all at most 10 MB, an index with SHA-256.

Requirements: FR-013-31.

Oracle: file sizes and SHA-256 recomputed with `os.stat` and `hashlib`; round trips through the reference readers
(`pyarrow.parquet`, `zarr`, a standard-library PNG decoder in `sensor_kit`); the DC-013-03 draft schema for the index;
"at most 10 MB" is 10,000,000 bytes (spec 013 clarifications log).

Expected API (package `pitstudio_rtx.shards`, first-party code importable from `studio/rtx/src`):
- `shards.ShardWriter(out_dir, *, run_id, stage, scenario, backend, max_bytes=10_000_000)`.
  `add_lidar_frame(sensor_id, frame, columns, *, beams_emitted, rain_rate_mm_h=None)`: `columns` maps the lidar-return
  column names (frame, beam, echo, x_m, y_m, z_m, range_m, intensity, flags, material_class (strings), object_id) to equal-length
  arrays holding the frame's valid returns; `add_radar_frame(sensor_id, frame, columns)`: columns frame, x_m, y_m, z_m,
  rcs_dbsm, radial_velocity_m_per_s, object_id; `add_image(sensor_id, image, arrays, record)`: `arrays` may hold `hdr`
  (height, width, 3) float16, `distance` (height, width) float32, `semantic` (height, width) uint32 (Zarr v3) and `ldr`
  (height, width, 3) uint8 (PNG); `record` the DC-013-03 image record without its `file` and `sensor`/`image` keys.
  `finish() -> dict` writes `<out_dir>/shard-index.json` and returns the DC-013-03 index.
- Parquet files hold whole frames only and rotate before they would exceed `max_bytes`; no file of any format is larger than
  `max_bytes`; every Zarr array is chunked so that no chunk or metadata file exceeds it; every file is listed in the index with
  `path` (relative to `out_dir`), `bytes`, `sha256`, `format`, `content` and, for Parquet, `rows`. A frame's `file` is the shard
  that holds its rows. The same input gives byte-identical files.
- Invalid input (columns of different length, a sensor id that is not a DC-013-01 sensor id, the same (sensor, frame) twice)
  raises `ValueError` and leaves no file of that call behind.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "rtx" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
import sensor_kit as kit  # noqa: E402
from pitstudio_rtx import shards  # noqa: E402

LIMIT = 10_000_000
RUN = "20261011T120000Z-shardtest"


def _writer(out: Path, scenario: str = "S1", stage: str = "st53_sensors") -> shards.ShardWriter:
    return shards.ShardWriter(out, run_id=RUN, stage=stage, scenario=scenario, backend="fake")


def _columns(n: int, frame: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    return {
        "frame": np.full(n, frame, np.uint32),
        "beam": np.arange(n, dtype=np.uint32),
        "echo": np.zeros(n, np.uint8),
        "x_m": rng.uniform(-100, 100, n),
        "y_m": rng.uniform(-100, 100, n),
        "z_m": rng.uniform(-5, 20, n),
        "range_m": rng.uniform(1, 200, n),
        "intensity": rng.uniform(0, 1, n),
        "flags": np.full(n, 0x40, np.uint8),
        "material_class": np.where(rng.uniform(size=n) < 0.2, "retro", "diffuse"),
        "object_id": rng.integers(0, 6, n).astype(np.uint32),
    }


def _check_files(out: Path, index: dict) -> None:
    assert kit.schema_errors("sensor-shard.schema.json", index) == []
    listed = {e["path"] for e in index["files"]}
    on_disk = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.name != "shard-index.json"}
    assert listed == on_disk  # every output file is listed, and every listed file exists
    for entry in index["files"]:
        data = (out / entry["path"]).read_bytes()
        assert entry["bytes"] == len(data) <= LIMIT, entry["path"]
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()


@pytest.mark.req("FR-013-31")
def test_oversized_lidar_output_is_split_into_shards_of_at_most_10_mb(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    w = _writer(tmp_path)
    n_frames, per_frame = 16, 50_000  # about 800,000 rows: more than 10 MB of Parquet
    sources = {}
    for k in range(n_frames):
        cols = _columns(per_frame, k, k)
        sources[k] = cols
        w.add_lidar_frame("rotary-64", k, cols, beams_emitted=per_frame + 10)
    index = w.finish()
    _check_files(tmp_path, index)
    parquet = [e for e in index["files"] if e["format"] == "parquet"]
    assert len(parquet) >= 3 and all(e["content"] == "lidar-returns" for e in parquet)
    assert sum(e["rows"] for e in parquet) == n_frames * per_frame
    for frame in index["frames"]:  # each frame lives whole in the file the index names
        table = pq.read_table(tmp_path / frame["file"], filters=[("frame", "=", frame["frame"])])
        assert table.num_rows == frame["valid_points"] == per_frame and frame["beams_emitted"] == per_frame + 10
        np.testing.assert_allclose(table.column("x_m").to_numpy(), sources[frame["frame"]]["x_m"])
    assert [f["frame"] for f in index["frames"]] == list(range(n_frames))
    assert (tmp_path / "shard-index.json").is_file()


@pytest.mark.req("FR-013-31")
def test_parquet_columns_are_the_lidar_return_column_set(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    w = _writer(tmp_path)
    w.add_lidar_frame("rotary-64", 0, _columns(1000, 0, 1), beams_emitted=1200)
    index = w.finish()
    table = pq.read_table(tmp_path / index["files"][0]["path"])
    assert table.column_names == [
        "frame",
        "beam",
        "echo",
        "x_m",
        "y_m",
        "z_m",
        "range_m",
        "intensity",
        "flags",
        "material_class",
        "object_id",
    ]
    assert set(table.column("material_class").to_pylist()) <= {"retro", "diffuse"}
    assert index["files"][0]["rows"] == 1000 and index["files"][0]["content"] == "lidar-returns"


@pytest.mark.req("FR-013-31")
def test_radar_detections_are_written_as_parquet_with_the_radar_column_set(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    rng = np.random.default_rng(3)
    n = 500
    w = _writer(tmp_path, "S4a")
    w.add_radar_frame(
        "proximity-77",
        0,
        {
            "frame": np.zeros(n, np.uint32),
            "x_m": rng.uniform(15, 80, n),
            "y_m": rng.uniform(-3, 3, n),
            "z_m": rng.uniform(0, 2, n),
            "rcs_dbsm": rng.uniform(-10, 20, n),
            "radial_velocity_m_per_s": rng.uniform(-15, 15, n),
            "object_id": rng.integers(0, 4, n).astype(np.uint32),
        },
    )
    index = w.finish()
    _check_files(tmp_path, index)
    (entry,) = index["files"]
    assert entry["format"] == "parquet" and entry["content"] == "radar-detections" and entry["rows"] == n
    assert pq.read_table(tmp_path / entry["path"]).column_names[:3] == ["frame", "x_m", "y_m"]
    assert index["frames"] == []  # radar rows are not lidar frames (S4a index: no lidar frame records)


@pytest.mark.req("FR-013-31")
def test_dense_arrays_are_zarr_v3_chunks_each_at_most_10_mb(tmp_path: Path) -> None:
    import zarr

    rng = np.random.default_rng(2)
    h, wd = 1080, 1920
    hdr = rng.uniform(0, 4, (h, wd, 3)).astype(np.float16)  # 12.4 MB raw: needs several chunks
    dist = rng.uniform(5, 100, (h, wd)).astype(np.float32)
    sem = rng.integers(0, 40, (h, wd)).astype(np.uint32)
    ldr = rng.integers(0, 256, (h, wd, 3)).astype(np.uint8)
    w = _writer(tmp_path, "S3")
    record = {
        "width_px": wd,
        "height_px": h,
        "fx_px": 2000.0,
        "fy_px": 2000.0,
        "cx_px": 960.0,
        "cy_px": 540.0,
        "world_from_camera": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    }
    w.add_image("crusher-cam", 0, {"hdr": hdr, "distance": dist, "semantic": sem, "ldr": ldr}, record)
    index = w.finish()
    _check_files(tmp_path, index)
    formats = {(e["format"], e["content"]) for e in index["files"]}
    assert {
        ("zarr", "hdr-color"),
        ("zarr", "distance"),
        ("zarr", "semantic"),
        ("png", "ldr-color"),
        ("parquet", "image-index"),
    } <= formats
    for content, expected in (("hdr-color", hdr), ("distance", dist), ("semantic", sem)):
        meta = next(
            e
            for e in index["files"]
            if e["format"] == "zarr" and e["content"] == content and e["path"].endswith("zarr.json")
        )
        arr = zarr.open_array(str(tmp_path / Path(meta["path"]).parent), mode="r")
        np.testing.assert_array_equal(arr[...], expected)
        assert json.loads((tmp_path / meta["path"]).read_text(encoding="utf-8"))["zarr_format"] == 3  # Zarr v3 metadata
    assert (
        len([e for e in index["files"] if e["content"] == "hdr-color"]) >= 3
    )  # metadata plus at least two chunk files


@pytest.mark.req("FR-013-31")
def test_ldr_images_are_png_files_listed_in_the_index_and_round_trip(tmp_path: Path) -> None:
    rng = np.random.default_rng(4)
    ldr = rng.integers(0, 256, (1080, 1920, 3)).astype(np.uint8)
    w = _writer(tmp_path, "S3")
    w.add_image(
        "crusher-cam",
        7,
        {"ldr": ldr},
        {
            "width_px": 1920,
            "height_px": 1080,
            "fx_px": 1000.0,
            "fy_px": 1000.0,
            "cx_px": 960.0,
            "cy_px": 540.0,
            "world_from_camera": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        },
    )
    index = w.finish()
    _check_files(tmp_path, index)
    (png,) = [e for e in index["files"] if e["format"] == "png"]
    assert png["content"] == "ldr-color" and png["bytes"] <= LIMIT
    np.testing.assert_array_equal(kit.png_decode(tmp_path / png["path"]), ldr)


@pytest.mark.req("FR-013-31")
def test_the_same_input_gives_byte_identical_files(tmp_path: Path) -> None:
    digests = []
    for name in ("a", "b"):
        out = tmp_path / name
        w = _writer(out)
        for k in range(3):
            w.add_lidar_frame("rotary-64", k, _columns(2000, k, k), beams_emitted=2500)
        index = w.finish()
        digests.append([(e["path"], e["sha256"], e["bytes"]) for e in index["files"]])
    assert digests[0] == digests[1]


@pytest.mark.req("FR-013-31")
def test_invalid_input_raises_value_error_and_writes_nothing(tmp_path: Path) -> None:
    w = _writer(tmp_path)
    good = _columns(100, 0, 0)
    bad_len = {**good, "y_m": good["y_m"][:-1]}
    with pytest.raises(ValueError):
        w.add_lidar_frame("rotary-64", 0, bad_len, beams_emitted=100)
    for sensor in ("../escape", "Rotary", "", "a" * 33, "naïve"):
        with pytest.raises(ValueError):
            w.add_lidar_frame(sensor, 0, good, beams_emitted=100)
    w.add_lidar_frame("rotary-64", 0, good, beams_emitted=100)
    with pytest.raises(ValueError):
        w.add_lidar_frame("rotary-64", 0, good, beams_emitted=100)  # the same (sensor, frame) twice
    index = w.finish()
    assert [f["frame"] for f in index["frames"]] == [0] and index["frames"][0]["valid_points"] == 100
    assert not any("escape" in p.as_posix() for p in tmp_path.rglob("*"))
