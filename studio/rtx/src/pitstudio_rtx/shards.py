# SPDX-License-Identifier: Apache-2.0
"""Shard writer of the sensor lane: Parquet, Zarr v3 chunks and PNG, each file at most 10 MB, an index with SHA-256.

Implements FR-013-31 and the file side of DC-013-03 (`contracts/sensor-shard.schema.json`). Output is deterministic:
the same input gives byte-identical files and the same index. Files are listed in the index sorted by path.

Layout under `out_dir`: `sensors/<scenario>/<sensor>/returns-NNNNN.parquet` (lidar), `detections-NNNNN.parquet` (radar),
`images.parquet` (image index), `ldr-NNNNN.png`, `<hdr|distance|semantic>-NNNNN.zarr/` (Zarr v3, chunked along the
first axis, no compression so that a chunk's size is known), and `shard-index.json`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

SENSOR_ID = re.compile(r"[a-z][a-z0-9-]{0,31}")
LIDAR_COLUMNS = (
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
)
RADAR_COLUMNS = ("frame", "x_m", "y_m", "z_m", "rcs_dbsm", "radial_velocity_m_per_s", "object_id")
_UINT = {"frame": "uint32", "beam": "uint32", "object_id": "uint32", "echo": "uint8", "flags": "uint8"}
_FLOATS = ("x_m", "y_m", "z_m", "range_m", "intensity", "rcs_dbsm", "radial_velocity_m_per_s")
_ZARR_CONTENT = {"hdr": "hdr-color", "distance": "distance", "semantic": "semantic"}
_IMAGE_DTYPE = {"hdr": np.float16, "distance": np.float32, "semantic": np.uint32, "ldr": np.uint8}
_RECORD_REQUIRED = ("width_px", "height_px", "fx_px", "fy_px", "cx_px", "cy_px", "world_from_camera")
_RECORD_OPTIONAL = ("gsd_m", "h_agl_m")
_ZARR_FILL = 0.8  # a Zarr chunk is cut to at most this fraction of `max_bytes`


def image_record(
    camera: Mapping[str, Any],
    *,
    image: int,
    file: str,
    world_from_camera: Sequence[float],
    h_agl_m: float | None = None,
) -> dict[str, Any]:
    """The DC-013-03 image record of a recipe camera: pinhole intrinsics fx = fy = f / p, `gsd_m = p H / f` (S2)."""
    focal, pitch = float(camera["focal_length_m"]), float(camera["pixel_pitch_m"])
    cx, cy = (float(v) for v in camera["principal_point_px"])
    record: dict[str, Any] = {
        "image": int(image),
        "sensor": camera["id"],
        "file": file,
        "width_px": int(camera["width_px"]),
        "height_px": int(camera["height_px"]),
        "fx_px": focal / pitch,
        "fy_px": focal / pitch,
        "cx_px": cx,
        "cy_px": cy,
        "world_from_camera": [float(v) for v in world_from_camera],
    }
    if h_agl_m is not None:
        record["h_agl_m"] = float(h_agl_m)
        record["gsd_m"] = pitch * float(h_agl_m) / focal
    return record


def encode_png(rgb: np.ndarray, *, level: int = 6) -> bytes:
    """An 8-bit non-interlaced RGB PNG with the Up filter on every row (deterministic, standard library zlib)."""
    h, w, _ = rgb.shape
    rows = np.ascontiguousarray(rgb, dtype=np.uint8).reshape(h, w * 3)
    delta = rows.copy()
    delta[1:] = rows[1:] - rows[:-1]
    raw = np.concatenate([np.full((h, 1), 2, dtype=np.uint8), delta], axis=1).tobytes()

    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, level))
        + chunk(b"IEND", b"")
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _Shard:
    """The Parquet file being filled for one (kind, sensor): whole frames only."""

    def __init__(self, number: int, path: str) -> None:
        self.number, self.path = number, path
        self.tables: list[Any] = []
        self.estimate = 0
        self.rows = 0


class ShardWriter:
    """Write the shards of one stage run; `finish()` writes `shard-index.json` and returns the DC-013-03 index."""

    def __init__(
        self,
        out_dir: str | Path,
        *,
        run_id: str,
        stage: str,
        scenario: str,
        backend: str,
        max_bytes: int = 10_000_000,
        fixture: bool = False,
    ) -> None:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1024:
            raise ValueError(f"max_bytes must be an integer of at least 1024, got {max_bytes!r}")
        self.out_dir = Path(out_dir)
        self.run_id, self.stage, self.scenario, self.backend = run_id, stage, scenario, backend
        self.max_bytes, self.fixture = max_bytes, bool(fixture)
        self._frames: list[dict[str, Any]] = []
        self._files: dict[str, dict[str, Any]] = {}
        self._open: dict[tuple[str, str], _Shard] = {}
        self._counters: dict[tuple[str, str], int] = {}
        self._seen: set[tuple[str, str, int]] = set()
        self._images: dict[str, list[dict[str, Any]]] = {}
        self._finished = False

    # -- validation -----------------------------------------------------------------------------------------------
    @staticmethod
    def _sensor(sensor_id: Any) -> str:
        if not isinstance(sensor_id, str) or SENSOR_ID.fullmatch(sensor_id) is None:
            raise ValueError(f"not a sensor id (DC-013-01): {sensor_id!r}")
        return sensor_id

    @staticmethod
    def _index(value: Any, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or not 0 <= int(value) < 2**32:
            raise ValueError(f"{name} must be an integer in [0, 2^32), got {value!r}")
        return int(value)

    def _claim(self, kind: str, sensor: str, frame: int) -> None:
        if self._finished:
            raise RuntimeError("the writer is finished")
        if (kind, sensor, frame) in self._seen:
            raise ValueError(f"{kind} frame {frame} of sensor {sensor} was already written")

    def _table(self, columns: Mapping[str, Any], names: Sequence[str], frame: int) -> Any:
        import pyarrow as pa

        if set(columns) != set(names):
            raise ValueError(f"columns must be exactly {list(names)}, got {sorted(columns)}")
        arrays = {name: np.asarray(columns[name]) for name in names}
        lengths = {len(a) for a in arrays.values()}
        if any(a.ndim != 1 for a in arrays.values()) or len(lengths) != 1:
            raise ValueError("columns must be 1-D arrays of equal length")
        if np.any(arrays["frame"].astype(np.int64) != frame):
            raise ValueError(f"the frame column must hold {frame}")
        data: dict[str, Any] = {}
        for name in names:
            arr = arrays[name]
            if name in _UINT:
                data[name] = pa.array(arr.astype(_UINT[name]))
            elif name in _FLOATS:
                data[name] = pa.array(arr if arr.dtype in (np.float32, np.float64) else arr.astype(np.float64))
            elif name == "material_class":
                values = arr.astype(str)
                if not np.all(np.isin(values, ("retro", "diffuse"))):
                    raise ValueError("material_class values must be 'retro' or 'diffuse'")
                data[name] = pa.array(values.tolist(), type=pa.string())
        return pa.table(data).replace_schema_metadata({"pitstudio:fixture": "true"} if self.fixture else None)

    # -- parquet ----------------------------------------------------------------------------------------------------
    def _estimate(self, table: Any) -> int:
        import pyarrow as pa
        import pyarrow.parquet as pq

        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd", compression_level=3)
        return int(sink.getvalue().size)

    def _directory(self, sensor: str) -> str:
        return f"sensors/{self.scenario.lower()}/{sensor}"

    def _add_rows(self, kind: str, sensor: str, frame: int, table: Any) -> str:
        """Add one whole frame to the shard of (kind, sensor), rotating first when it would not fit; return the path."""
        size = self._estimate(table)
        if size > self.max_bytes:
            raise ValueError(f"one frame needs {size} bytes, more than the {self.max_bytes} byte limit")
        key = (kind, sensor)
        shard = self._open.get(key)
        if shard is not None and shard.estimate + size > self.max_bytes:
            self._flush(kind, sensor)
            shard = None
        if shard is None:
            number = self._counters.get(key, 0)
            self._counters[key] = number + 1
            stem = "returns" if kind == "lidar" else "detections"
            shard = self._open[key] = _Shard(number, f"{self._directory(sensor)}/{stem}-{number:05d}.parquet")
        shard.tables.append(table)
        shard.estimate += size
        shard.rows += table.num_rows
        self._seen.add((kind, sensor, frame))
        return shard.path

    def _flush(self, kind: str, sensor: str) -> None:
        shard = self._open.pop((kind, sensor), None)
        if shard is None:
            return
        self._write_parquet(shard.path, shard.tables, "lidar-returns" if kind == "lidar" else "radar-detections")

    def _write_parquet(self, relpath: str, tables: Sequence[Any], content: str) -> None:
        import pyarrow.parquet as pq

        target = self.out_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        with pq.ParquetWriter(target, tables[0].schema, compression="zstd", compression_level=3) as writer:
            for table in tables:
                writer.write_table(table)
        self._register(relpath, "parquet", content, rows=sum(t.num_rows for t in tables))

    def _register(self, relpath: str, fmt: str, content: str, rows: int | None = None) -> None:
        path = self.out_dir / relpath
        size = path.stat().st_size
        if size > self.max_bytes:
            path.unlink()
            raise ValueError(f"{relpath} is {size} bytes, more than the {self.max_bytes} byte limit")
        entry: dict[str, Any] = {
            "path": relpath,
            "bytes": size,
            "sha256": _sha256(path),
            "format": fmt,
            "content": content,
        }
        if rows is not None:
            entry["rows"] = rows
        if self.fixture:
            entry["fixture"] = True
        self._files[relpath] = entry

    # -- public API -------------------------------------------------------------------------------------------------
    def add_lidar_frame(
        self,
        sensor_id: str,
        frame: int,
        columns: Mapping[str, Any],
        *,
        beams_emitted: int,
        rain_rate_mm_h: float | None = None,
    ) -> None:
        """Add the valid returns of one lidar frame (all columns of `LIDAR_COLUMNS`, equal length, at least one row)."""
        sensor, frame = self._sensor(sensor_id), self._index(frame, "frame")
        self._claim("lidar", sensor, frame)
        table = self._table(columns, LIDAR_COLUMNS, frame)
        if table.num_rows < 1:
            raise ValueError("a lidar frame needs at least one valid return (point-count guard)")
        if isinstance(beams_emitted, bool) or not isinstance(beams_emitted, (int, np.integer)):
            raise ValueError(f"beams_emitted must be an integer, got {beams_emitted!r}")
        if not table.num_rows <= int(beams_emitted) <= 10_000_000:
            raise ValueError(f"beams_emitted {beams_emitted} must lie in [valid points {table.num_rows}, 10000000]")
        if rain_rate_mm_h is not None and not (math.isfinite(rain_rate_mm_h) and 0 <= rain_rate_mm_h <= 200):
            raise ValueError(f"rain_rate_mm_h must be in [0, 200], got {rain_rate_mm_h!r}")
        path = self._add_rows("lidar", sensor, frame, table)
        record: dict[str, Any] = {
            "sensor": sensor,
            "frame": frame,
            "beams_emitted": int(beams_emitted),
            "valid_points": table.num_rows,
            "file": path,
        }
        if rain_rate_mm_h is not None:
            record["rain_rate_mm_h"] = float(rain_rate_mm_h)
        self._frames.append(record)

    def add_radar_frame(self, sensor_id: str, frame: int, columns: Mapping[str, Any]) -> None:
        """Add the detections of one radar frame (all columns of `RADAR_COLUMNS`; zero rows are allowed)."""
        sensor, frame = self._sensor(sensor_id), self._index(frame, "frame")
        self._claim("radar", sensor, frame)
        self._add_rows("radar", sensor, frame, self._table(columns, RADAR_COLUMNS, frame))

    def add_image(
        self, sensor_id: str, image: int, arrays: Mapping[str, np.ndarray], record: Mapping[str, Any]
    ) -> None:
        """Add one camera image: `hdr`, `distance`, `semantic` as Zarr v3, `ldr` as PNG, and its image-index record."""
        sensor, image = self._sensor(sensor_id), self._index(image, "image")
        self._claim("image", sensor, image)
        rec = self._check_image(arrays, record)
        base = f"{self._directory(sensor)}"
        first = None
        for name in ("hdr", "distance", "semantic"):
            if name in arrays:
                first = first or f"{base}/{name}-{image:05d}.zarr"
                self._write_zarr(f"{base}/{name}-{image:05d}.zarr", np.asarray(arrays[name]), _ZARR_CONTENT[name])
        if "ldr" in arrays:
            png = encode_png(np.asarray(arrays["ldr"]))
            relpath = f"{base}/ldr-{image:05d}.png"
            if len(png) > self.max_bytes:
                raise ValueError(f"the PNG needs {len(png)} bytes, more than the {self.max_bytes} byte limit")
            (self.out_dir / relpath).parent.mkdir(parents=True, exist_ok=True)
            (self.out_dir / relpath).write_bytes(png)
            self._register(relpath, "png", "ldr-color")
            first = relpath
        self._images.setdefault(sensor, []).append({"image": image, "sensor": sensor, "file": first, **rec})
        self._seen.add(("image", sensor, image))

    def _check_image(self, arrays: Mapping[str, np.ndarray], record: Mapping[str, Any]) -> dict[str, Any]:
        if not arrays or not set(arrays) <= set(_IMAGE_DTYPE):
            raise ValueError(f"arrays must be a non-empty subset of {sorted(_IMAGE_DTYPE)}")
        missing = [k for k in _RECORD_REQUIRED if k not in record]
        extra = [k for k in record if k not in (*_RECORD_REQUIRED, *_RECORD_OPTIONAL)]
        if missing or extra:
            raise ValueError(f"image record: missing {missing}, unexpected {extra}")
        h, w = int(record["height_px"]), int(record["width_px"])
        for name, arr in arrays.items():
            want = (h, w, 3) if name in ("hdr", "ldr") else (h, w)
            if np.asarray(arr).dtype != _IMAGE_DTYPE[name] or np.asarray(arr).shape != want:
                raise ValueError(f"{name} must be {np.dtype(_IMAGE_DTYPE[name])} of shape {want}")
        pose = record["world_from_camera"]
        if len(pose) != 16 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in pose):
            raise ValueError("world_from_camera must hold 16 finite numbers")
        return {k: record[k] for k in (*_RECORD_REQUIRED, *_RECORD_OPTIONAL) if k in record}

    def _write_zarr(self, relpath: str, array: np.ndarray, content: str) -> None:
        import zarr

        row_bytes = array.itemsize * int(np.prod(array.shape[1:]))
        if row_bytes > self.max_bytes * _ZARR_FILL:
            raise ValueError(f"one row of {relpath} is {row_bytes} bytes, too large for the byte limit")
        rows = max(1, min(array.shape[0], int(self.max_bytes * _ZARR_FILL) // row_bytes))
        target = self.out_dir / relpath
        store = zarr.create_array(
            str(target),
            shape=array.shape,
            chunks=(rows, *array.shape[1:]),
            dtype=array.dtype,
            zarr_format=3,
            compressors=None,
            overwrite=False,
        )
        store[...] = array
        for path in sorted(target.rglob("*")):
            if path.is_file():
                self._register(path.relative_to(self.out_dir).as_posix(), "zarr", content)

    def finish(self) -> dict[str, Any]:
        """Flush every open shard, write the image indexes and `shard-index.json`, and return the index."""
        if self._finished:
            raise RuntimeError("the writer is finished")
        for kind, sensor in sorted(self._open):
            self._flush(kind, sensor)
        for sensor, records in sorted(self._images.items()):
            self._write_image_index(sensor, records)
        self._finished = True
        index: dict[str, Any] = {
            "schema_version": "1.1",
            "run_id": self.run_id,
            "stage": self.stage,
            "scenario": self.scenario,
            "backend": self.backend,
            "frames": self._frames,
            "files": [self._files[k] for k in sorted(self._files)],
        }
        if self.fixture:
            index["fixture"] = True
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "shard-index.json").write_text(
            json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return index

    def _write_image_index(self, sensor: str, records: list[dict[str, Any]]) -> None:
        import pyarrow as pa

        records = sorted(records, key=lambda r: r["image"])
        columns: dict[str, Any] = {
            "image": pa.array([r["image"] for r in records], pa.uint32()),
            "sensor": pa.array([r["sensor"] for r in records], pa.string()),
            "file": pa.array([r["file"] for r in records], pa.string()),
            "width_px": pa.array([r["width_px"] for r in records], pa.int32()),
            "height_px": pa.array([r["height_px"] for r in records], pa.int32()),
        }
        for key in ("fx_px", "fy_px", "cx_px", "cy_px"):
            columns[key] = pa.array([float(r[key]) for r in records], pa.float64())
        columns["world_from_camera"] = pa.array(
            [[float(v) for v in r["world_from_camera"]] for r in records], pa.list_(pa.float64())
        )
        for key in _RECORD_OPTIONAL:
            if any(key in r for r in records):
                columns[key] = pa.array([r.get(key) for r in records], pa.float64())
        table = pa.table(columns).replace_schema_metadata({"pitstudio:fixture": "true"} if self.fixture else None)
        self._write_parquet(f"{self._directory(sensor)}/images.parquet", [table], "image-index")
