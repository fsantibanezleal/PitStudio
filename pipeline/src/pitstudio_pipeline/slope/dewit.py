"""de Wit ingestion for the single real event of case C1 (FR-010-13, FR-010-14, FR-010-15).

Only the Zenodo record 15003054 archive ``Data.zip`` (8,943,265 bytes, MD5 3adeb6c853d2e87249b7d3549a2a00ca, CC BY
4.0) is
accepted. Members are read in memory and never extracted; nothing but the derived series and its manifest is written.

Supported layouts (the layout is read at ingestion; UNVERIFIED which the real archive needs, see the note below):
1. a CSV with columns ``time_<unit>`` (s, min, h, d) and ``displacement_<unit>`` (mm, cm, m) plus one JSON metadata
file with
   ``failure_time``, ``failure_time_unit``, ``failure_time_source`` and ``attribution``;
2. an ``.npz`` with ``time_<unit>`` (T,) and ``displacement_<unit>`` (T, H, W) maps, reduced to the per-epoch median
over the
   pixels in the top 5 % of the final cumulative displacement, with the same metadata.
The real ``Data.zip`` was inspected on 2026-10-12: its ``radar-deformation-data`` folder holds prism series (columns
Prism,
Date, Time, Easting, Northing, Height, Adjusted Distance Diff ...) with no displacement unit in the headers and no
failure time
anywhere in the archive, and the Zenodo record and page state no failure date. FR-010-14 therefore rejects it ("no
supported
member" / "unit" / "failure time"); the failure time (with its documentary source) is a required input: pass
``failure_time={"value", "unit", "source", "attribution"}`` for an archive whose metadata lacks it.

A rejected archive raises ``DewitRejected``; ``panel_text`` is the C1 real-event panel text "Not run - <reason>".
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.slope import snr as _snr

EXPECTED_BYTES = 8_943_265
EXPECTED_MD5 = "3adeb6c853d2e87249b7d3549a2a00ca"
EVENT_ID = "dewit-2025-event"
SOURCE_ID = "dewit-slope-failure"
TIME_UNITS = {"s": 1 / 3600.0, "min": 1 / 60.0, "h": 1.0, "d": 24.0}
DISP_UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0}
MAX_MEMBER_BYTES = 256 * 1024 * 1024
_COLUMN = re.compile(r"^(time|displacement)(?:_([A-Za-z]+))?$")


class DewitRejected(ValueError):
    """The archive is rejected with a reason; no series and no TTF number leave it."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.panel_text = f"Not run — {reason}"


@dataclass
class DewitSeries:
    document: dict[str, Any]
    manifest: dict[str, Any]


def _check_names(names: list[str]) -> None:
    for name in names:
        norm = name.replace("\\", "/")
        if norm.startswith("/"):
            raise DewitRejected(f"member {name!r} is an absolute path")
        if re.match(r"^[A-Za-z]:", norm):
            raise DewitRejected(f"member {name!r} has a drive letter")
        if ".." in norm.split("/"):
            raise DewitRejected(f"member {name!r} has a '..' component")


def _units(header: list[str]) -> tuple[int, str, int, str]:
    t_i = d_i = -1
    t_u = d_u = ""
    for i, col in enumerate(header):
        m = _COLUMN.match(col.strip())
        if not m:
            continue
        if m.group(1) == "time":
            t_i, t_u = i, m.group(2) or ""
        else:
            d_i, d_u = i, m.group(2) or ""
    if t_i < 0 or d_i < 0:
        raise DewitRejected("archive has no supported member: no time and displacement columns")
    if t_u not in TIME_UNITS:
        raise DewitRejected(f"the time column has no valid unit (one of {list(TIME_UNITS)})")
    if d_u not in DISP_UNITS:
        raise DewitRejected(f"the displacement column has no valid unit (one of {list(DISP_UNITS)})")
    return t_i, t_u, d_i, d_u


def _read_csv(data: bytes) -> tuple[np.ndarray, np.ndarray, str, str]:
    lines = data.decode("utf-8", "replace").splitlines()
    header = lines[0].split(",") if lines else []
    t_i, t_u, d_i, d_u = _units(header)
    t, d = [], []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split(",")
        try:
            t.append(float(cells[t_i]))
            d.append(float(cells[d_i]))
        except ValueError, IndexError:
            raise DewitRejected("displacement or time value is not a number") from None
    return np.asarray(t), np.asarray(d), t_u, d_u


def _read_npz(data: bytes) -> tuple[np.ndarray, np.ndarray, str, str]:
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        keys = list(z.keys())
        t_i, t_u, d_i, d_u = _units(keys)
        t, stack = np.asarray(z[keys[t_i]], dtype=float), np.asarray(z[keys[d_i]], dtype=float)
    if stack.ndim != 3 or stack.shape[0] != t.size:
        raise DewitRejected("the displacement maps must have shape (epochs, rows, columns)")
    flat = stack.reshape(stack.shape[0], -1)
    k = max(1, math.ceil(0.05 * flat.shape[1]))
    top = np.argsort(flat[-1])[-k:]
    return t, np.median(flat[:, top], axis=1), t_u, d_u


def _failure_time(meta: dict[str, Any], override: dict[str, Any] | None) -> tuple[float, dict[str, Any], str]:
    src = override if override is not None else meta
    value = src.get("value", src.get("failure_time"))
    unit = src.get("unit", src.get("failure_time_unit", "h"))
    source = src.get("source", src.get("failure_time_source"))
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or unit not in TIME_UNITS
    ):
        raise DewitRejected("no failure time stated (a number and a unit are required)")
    if not isinstance(source, dict):
        raise DewitRejected("no failure time source stated (its documentary source is required)")
    attribution = src.get("attribution", meta.get("attribution"))
    if not isinstance(attribution, str) or not attribution:
        raise DewitRejected("no attribution text in the metadata")
    return float(value) * TIME_UNITS[unit], source, attribution


def ingest(
    archive: str | Path,
    *,
    expected_bytes: int = EXPECTED_BYTES,
    expected_md5: str = EXPECTED_MD5,
    out_dir: str | Path | None = None,
    failure_time: dict[str, Any] | None = None,
) -> DewitSeries:
    """Ingest the archive (see the module docstring) or raise ``DewitRejected``."""
    path = Path(archive)
    raw = path.read_bytes()
    if len(raw) != expected_bytes or hashlib.md5(raw).hexdigest() != expected_md5:
        raise DewitRejected("archive checksum mismatch: size or MD5 differs from the Zenodo record")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise DewitRejected("archive is not a valid zip file") from None
    with zf:
        names = [i.filename for i in zf.infolist() if not i.filename.endswith("/")]
        _check_names(names)
        for info in zf.infolist():
            if info.file_size > MAX_MEMBER_BYTES:
                raise DewitRejected(f"archive member {info.filename!r} is too large")
        data_member = None
        for name in names:
            if name.lower().endswith(".npz"):
                data_member, reader, extraction = name, _read_npz, "map-median-top-5pct"
                break
        else:
            for name in names:
                if name.lower().endswith(".csv"):
                    head = zf.read(name)[:4096].decode("utf-8", "replace").splitlines()[:1]
                    if head and _COLUMN.match(head[0].split(",")[0].strip()) and "displacement" in head[0]:
                        data_member, reader, extraction = name, _read_csv, "series-as-delivered"
                        break
        if data_member is None:
            raise DewitRejected("archive has no supported member (a series CSV or a map stack)")
        meta_name = next((n for n in names if n.lower().endswith(".json")), None)
        meta = json.loads(zf.read(meta_name).decode("utf-8")) if meta_name else {}
        t_raw, d_raw, t_u, d_u = reader(zf.read(data_member))
    if not np.all(np.isfinite(t_raw)) or not np.all(np.diff(t_raw) > 0.0):
        raise DewitRejected("timestamps are not strictly increasing")
    if not np.all(np.isfinite(d_raw)):
        raise DewitRejected("the displacement contains a non-finite value")
    t_f, t_f_source, attribution = _failure_time(meta, failure_time)
    t = t_raw * TIME_UNITS[t_u]
    omega = d_raw * DISP_UNITS[d_u]
    t_0 = float(t[0])
    if not t_f > t_0:
        raise DewitRejected("the failure time is not after the first timestamp")
    keep = (t >= t_0) & (t <= t_f)
    if int(keep.sum()) < 4:
        raise DewitRejected("fewer than 4 samples between the first timestamp and the failure time")
    snr_obs = _snr.snr_obs(t, omega, t_0, t_f)
    diffs = np.diff(t)
    interval = float(np.median(diffs))
    regular = bool(np.allclose(diffs, interval, rtol=1e-9, atol=0.0))
    sha = hashlib.sha256(raw).hexdigest()
    units = {"displacement": d_u, "time": t_u}
    sampling = {"n_samples": int(t.size), "interval_h": interval, "regular": regular}
    document = {
        "kind": "real-event",
        "synthetic": False,
        "event_id": EVENT_ID,
        "source_id": SOURCE_ID,
        "archive_bytes": expected_bytes,
        "archive_md5": expected_md5,
        "archive_sha256": sha,
        "archive_member": data_member,
        "extraction": extraction,
        "source_units": units,
        "t_0_h": t_0,
        "t_f_h": t_f,
        "t_f_source": t_f_source,
        "snr_obs": snr_obs,
        "sampling": sampling,
        "attribution": attribution,
        "licence": {"spdx": "CC-BY-4.0", "licence_class": "attribution"},
        "use": "descriptive-evaluation-only",
        "t_h": [float(x) for x in t],
        "los_displacement_mm": [float(x) for x in omega],
    }
    manifest = {
        "archive_bytes": expected_bytes,
        "archive_md5": expected_md5,
        "archive_sha256": sha,
        "archive_member": data_member,
        "source_units": units,
        "sampling_interval_h": interval,
        "t_0_h": t_0,
        "t_f_h": t_f,
        "t_f_source": t_f_source,
        "attribution": attribution,
        "snr_obs": snr_obs,
    }
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "dewit-series.json").write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return DewitSeries(document, manifest)
