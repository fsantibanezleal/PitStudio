"""The de Wit prism-export reader and the real series of case C1 (FR-010-12, FR-010-13, FR-010-14, FR-010-15).

The real ``Data.zip`` (Zenodo record 15003054) delivers its surface deformation as Quikslope5 prism exports: one row per
total-station reading of a prism, with the columns Prism, Date, Time, Easting, Northing, Height (metres) and the Diff
columns of the export (millimetres). It carries no map stack and no series CSV, so ``dewit.ingest`` rejects it. This
module applies the rule of FR-010-13 for map stacks to prisms:

1. a prism is eligible when it has at least two readings up to ``t_f``; its cumulative displacement is the 3D distance
   of a reading from its first reading, in millimetres;
2. the selected prisms are the top ``fraction`` (5 %, at least one) of the eligible prisms by the cumulative
   displacement of their last reading up to ``t_f``; readings after ``t_f`` never decide the selection;
3. each selected prism's displacement is projected on the direction of its own final displacement (a signed along-motion
   displacement, the analogue of the line-of-sight displacement of the synthetic events, free of the positive bias that
   the magnitude of a noisy 3D vector has near zero) and linearly interpolated on a regular grid of ``step_h`` hours;
4. the series is the per-epoch median over the selected prisms that have a reading at the epoch, kept from the first
   epoch to the last one at which at least ``min_share`` of the selected prisms have one.

The failure time is an input with its two documentary sources; this module never guesses one. ``ingest_prisms`` returns
the document of ``dewit.ingest`` (same keys) with ``t_h`` in hours from the first epoch of the series. The archive is
read in memory, never extracted, and its series is for descriptive evaluation only (FR-010-15).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import zipfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio.slope import snr as _snr
from pitstudio_pipeline.slope import dewit

Reading = tuple[datetime, float, float, float]
MONTHS = {
    m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
}
EXTRACTION = "prism-median-top-5pct"
REQUIRED = ("Prism", "Date", "Time", "Easting", "Northing", "Height", "Easting Diff")


def _timestamp(date: str, clock: str) -> datetime:
    day, month, year = date.strip().split("-")
    h, m, s = clock.strip().split(":")
    return datetime(2000 + int(year), MONTHS[month], int(day), int(h), int(m), int(s))


def _header_index(lines: Sequence[str]) -> int | None:
    for i, line in enumerate(lines[:20]):
        if line.startswith("Prism,") and all(col in line for col in REQUIRED):
            return i
    return None


def is_prism_export(data: bytes) -> bool:
    return _header_index(data[:8192].decode("utf-8", "replace").splitlines()) is not None


def read_prisms(data: bytes) -> dict[str, list[Reading]]:
    """The readings of every prism of a Quikslope export, in time order, in file order of the prisms."""
    lines = data.decode("utf-8", "replace").splitlines()
    start = _header_index(lines)
    if start is None:
        raise dewit.DewitRejected("archive has no supported member: not a prism export (header columns missing)")
    out: dict[str, list[Reading]] = {}
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        if not row.get("Prism"):
            continue
        try:
            reading = (
                _timestamp(row["Date"], row["Time"]),
                float(row["Easting"]),
                float(row["Northing"]),
                float(row["Height"]),
            )
        except ValueError, KeyError, TypeError:
            raise dewit.DewitRejected("a prism reading has a date, a time or a coordinate that is not valid") from None
        if not all(math.isfinite(v) for v in reading[1:]):
            raise dewit.DewitRejected("a prism reading has a non-finite coordinate")
        out.setdefault(row["Prism"], []).append(reading)
    if not out:
        raise dewit.DewitRejected("the prism export has no readings")
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


def build_series(
    prisms: Mapping[str, Sequence[Reading]],
    t_f: datetime,
    *,
    step_h: float = 6.0,
    fraction: float = 0.05,
    min_share: float = 0.5,
) -> dict[str, Any]:
    """The FR-010-13 series of the prisms in the top ``fraction`` of the displacement to ``t_f`` (module docstring)."""
    if not (step_h > 0.0 and 0.0 < fraction <= 1.0 and 0.0 < min_share <= 1.0):
        raise ValueError("step_h must be positive, fraction and min_share in (0, 1]")
    eligible = []
    for pid, rows in prisms.items():
        used = [r for r in rows if r[0] <= t_f]
        if len(used) < 2:
            continue
        pos = np.array([[r[1], r[2], r[3]] for r in used], dtype=float)
        disp = (pos - pos[0]) * 1000.0
        eligible.append((float(np.linalg.norm(disp[-1])), pid, used, disp))
    if not eligible:
        raise dewit.DewitRejected("no prism has two readings up to the failure time")
    eligible.sort(key=lambda e: (-e[0], e[1]))
    k = max(1, math.ceil(round(fraction * len(eligible), 9)))
    chosen = eligible[:k]
    if chosen[0][0] == 0.0:
        raise dewit.DewitRejected("the selected prisms did not move")
    first = min(e[2][0][0] for e in chosen)
    n_grid = int((t_f - first).total_seconds() // (3600.0 * step_h)) + 1
    grid_h = step_h * np.arange(n_grid)
    matrix = np.full((k, n_grid), np.nan)
    for j, (norm, pid, used, disp) in enumerate(chosen):
        times = np.array([(r[0] - first).total_seconds() / 3600.0 for r in used])
        if not np.all(np.diff(times) > 0.0):
            raise dewit.DewitRejected(f"prism {pid} has duplicate timestamps")
        along = disp @ (disp[-1] / norm)
        inside = (grid_h >= times[0]) & (grid_h <= times[-1])
        matrix[j, inside] = np.interp(grid_h[inside], times, along)
    counts = np.sum(np.isfinite(matrix), axis=0)
    need = max(1, math.ceil(round(min_share * k, 9)))
    enough = counts >= need
    if not enough.any():
        raise dewit.DewitRejected("no epoch has enough selected prisms")
    lo = int(np.argmax(enough))
    hi = lo
    while hi + 1 < n_grid and enough[hi + 1]:
        hi += 1
    keep = slice(lo, hi + 1)
    with np.errstate(all="ignore"):
        omega = np.nanmedian(matrix[:, keep], axis=0)
    return {
        "t0": first + timedelta(hours=float(grid_h[lo])),
        "t_h": [float(h - grid_h[lo]) for h in grid_h[keep]],
        "omega_mm": [float(v) for v in omega],
        "prisms": [e[1] for e in chosen],
        "counts": [int(c) for c in counts[keep]],
    }


def _failure(ft: Mapping[str, Any]) -> dict[str, Any]:
    """The checked failure time: instant, uncertainty, zone, two sources and the attribution."""
    try:
        instant = datetime.fromisoformat(str(ft["instant"]))
    except KeyError, ValueError:
        raise dewit.DewitRejected("no failure time stated (an ISO instant is required)") from None
    unc = ft.get("uncertainty_h")
    if isinstance(unc, bool) or not isinstance(unc, int | float) or not math.isfinite(unc) or unc < 0:
        raise dewit.DewitRejected("the failure time needs a finite uncertainty in hours, zero or more")
    zone = ft.get("zone")
    if not isinstance(zone, str) or not zone.strip():
        raise dewit.DewitRejected("the failure time needs the time zone of the archive clock stated")
    sources = ft.get("sources")
    good = [
        s
        for s in (sources if isinstance(sources, list) else [])
        if isinstance(s, Mapping)
        and isinstance(s.get("citation"), str)
        and s["citation"].strip()
        and isinstance(s.get("locator"), str)
        and s["locator"].strip()
    ]
    if len(good) < 2 or len(good) != len(sources):
        raise dewit.DewitRejected("no failure time source stated (two documentary citations are required)")
    attribution = ft.get("attribution")
    if not isinstance(attribution, str) or not attribution:
        raise dewit.DewitRejected("no attribution text in the metadata")
    return {
        "instant": instant,
        "uncertainty_h": float(unc),
        "zone": zone,
        "sources": [dict(s) for s in good],
        "attribution": attribution,
    }


def ingest_prisms(
    archive: str | Path,
    *,
    failure_time: Mapping[str, Any],
    expected_bytes: int = dewit.EXPECTED_BYTES,
    expected_md5: str = dewit.EXPECTED_MD5,
    member: str | None = None,
    out_dir: str | Path | None = None,
    step_h: float = 6.0,
) -> dewit.DewitSeries:
    """Ingest the prism export of the archive (module docstring) or raise ``dewit.DewitRejected``."""
    raw = Path(archive).read_bytes()
    if len(raw) != expected_bytes or hashlib.md5(raw).hexdigest() != expected_md5:
        raise dewit.DewitRejected("archive checksum mismatch: size or MD5 differs from the Zenodo record")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise dewit.DewitRejected("archive is not a valid zip file") from None
    with zf:
        names = [i.filename for i in zf.infolist() if not i.filename.endswith("/")]
        dewit._check_names(names)
        for info in zf.infolist():
            if info.file_size > dewit.MAX_MEMBER_BYTES:
                raise dewit.DewitRejected(f"archive member {info.filename!r} is too large")
        if member is not None:
            if member not in names:
                raise dewit.DewitRejected(f"the named member {member!r} is not in the archive")
            chosen = member
        else:
            found = [n for n in names if n.lower().endswith(".csv") and is_prism_export(zf.read(n)[:8192])]
            if not found:
                raise dewit.DewitRejected("archive has no supported member: no prism export")
            if len(found) > 1:
                raise dewit.DewitRejected(f"several prism exports ({found}): name the member to use")
            chosen = found[0]
        prisms = read_prisms(zf.read(chosen))
    ft = _failure(failure_time)
    series = build_series(prisms, ft["instant"], step_h=step_h)
    t0: datetime = series["t0"]
    if not ft["instant"] > t0:
        raise dewit.DewitRejected("the failure time is not after the first timestamp")
    t = np.asarray(series["t_h"], dtype=float)
    omega = np.asarray(series["omega_mm"], dtype=float)
    t_f_h = (ft["instant"] - t0).total_seconds() / 3600.0
    try:
        snr_obs = _snr.snr_obs(t, omega, 0.0, t_f_h)
    except ValueError as exc:
        raise dewit.DewitRejected(f"SNR_obs cannot be estimated: {exc}") from None
    sha = hashlib.sha256(raw).hexdigest()
    t_f_source = {
        "instant": ft["instant"].isoformat(),
        "uncertainty_h": ft["uncertainty_h"],
        "zone": ft["zone"],
        "sources": ft["sources"],
    }
    units = {"displacement": "mm", "time": "h"}
    document = {
        "kind": "real-event",
        "synthetic": False,
        "event_id": dewit.EVENT_ID,
        "source_id": dewit.SOURCE_ID,
        "archive_bytes": expected_bytes,
        "archive_md5": expected_md5,
        "archive_sha256": sha,
        "archive_member": chosen,
        "extraction": EXTRACTION,
        "source_units": units,
        "t_0_h": 0.0,
        "t_f_h": t_f_h,
        "t_0_instant": t0.isoformat(),
        "t_f_instant": ft["instant"].isoformat(),
        "t_f_uncertainty_h": ft["uncertainty_h"],
        "zone": ft["zone"],
        "t_f_source": t_f_source,
        "snr_obs": snr_obs,
        "sampling": {"n_samples": int(t.size), "interval_h": float(step_h), "regular": True},
        "prisms": series["prisms"],
        "prism_counts": series["counts"],
        "attribution": ft["attribution"],
        "licence": {"spdx": "CC-BY-4.0", "licence_class": "attribution"},
        "use": "descriptive-evaluation-only",
        "t_h": [float(x) for x in t],
        "los_displacement_mm": [float(x) for x in omega],
    }
    manifest = {
        "archive_bytes": expected_bytes,
        "archive_md5": expected_md5,
        "archive_sha256": sha,
        "archive_member": chosen,
        "extraction": EXTRACTION,
        "source_units": units,
        "sampling_interval_h": float(step_h),
        "t_0_h": 0.0,
        "t_f_h": t_f_h,
        "t_0_instant": t0.isoformat(),
        "t_f_instant": ft["instant"].isoformat(),
        "t_f_uncertainty_h": ft["uncertainty_h"],
        "zone": ft["zone"],
        "t_f_source": t_f_source,
        "prisms": series["prisms"],
        "attribution": ft["attribution"],
        "snr_obs": snr_obs,
    }
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "dewit-series.json").write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return dewit.DewitSeries(document, manifest)
