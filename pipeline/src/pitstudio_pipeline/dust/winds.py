"""Hourly wind of NOAA GHCNh per-station PSV files (documentation v1.1.0, spec 008 section 7), read for the dust case C3.

One record per UTC clock hour: the earliest valid record of the hour wins (METAR, SYNOP and SPECI reports share the files).
A record without a speed, or whose speed quality code is not in `good_quality`, is dropped and counted. The direction is read
as the documentation says (whole degrees from true north, 360 = north, 000 = calm). The real files also carry the value 999 on
every calm and variable hour, told apart by `wind_direction_Measurement_Code` C (calm) and V (variable), N being a normal
observation; the letters follow the ISD wind-observation-type convention and their meaning in the GHCNh documentation text is
UNVERIFIED (it could not be read). Such an hour has no direction, never a guessed one. Nothing is imputed, clipped or interpolated.
"""
# ruff: noqa: E501

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

COLUMNS = (
    "STATION",
    "Station_name",
    "DATE",
    "LATITUDE",
    "LONGITUDE",
    "ELEVATION",
    "wind_speed",
    "wind_speed_Quality_Code",
    "wind_direction",
    "wind_direction_Quality_Code",
    "wind_direction_Measurement_Code",
)
VARIABLE_DIRECTION = 999.0


class StationMismatch(ValueError):
    """A file holds records of another station than the one asked for."""


@dataclass
class WindRecords:
    hour_utc: np.ndarray  # datetime64[h]
    speed_m_s: np.ndarray
    direction_deg: np.ndarray  # degrees from north in [0, 360), NaN without a usable direction
    kind: np.ndarray  # "wind", "calm" or "variable"
    counts: dict[str, int] = field(default_factory=dict)
    station: dict[str, Any] = field(default_factory=dict)


def _read(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, separator="|", columns=list(COLUMNS), infer_schema=False, null_values=[""])
    return frame.with_columns(pl.int_range(pl.len()).alias("_row"))


def read_ghcnh_wind(
    paths: Sequence[Path | str], *, station: str, good_quality: Sequence[str] = ("1", "5")
) -> WindRecords:
    counts: Counter[str] = Counter()
    frames = []
    meta: dict[str, Any] = {}
    for n, path in enumerate(paths):
        frame = _read(Path(path)).with_columns(pl.lit(n).alias("_file"))
        other = frame.filter(pl.col("STATION") != station)
        if other.height:
            raise StationMismatch(f"{Path(path).name}: station {other['STATION'][0]!r} is not {station!r}")
        if frame.height and not meta:
            first = frame.row(0, named=True)
            meta = {
                "id": first["STATION"],
                "name": first["Station_name"],
                "latitude": float(first["LATITUDE"]),
                "longitude": float(first["LONGITUDE"]),
                "elevation_m": float(first["ELEVATION"]) if first["ELEVATION"] else None,
            }
        frames.append(frame)
    all_rows = pl.concat(frames) if frames else pl.DataFrame()
    counts["rows"] = all_rows.height
    good = list(good_quality)
    all_rows = all_rows.with_columns(
        pl.col("wind_speed").cast(pl.Float64),
        pl.col("wind_direction").cast(pl.Float64, strict=False),
        pl.col("DATE").str.to_datetime("%Y-%m-%dT%H:%M:%S").alias("_t"),
    )
    no_speed = all_rows.filter(pl.col("wind_speed").is_null())
    counts["dropped_no_speed"] = no_speed.height
    rows = all_rows.filter(pl.col("wind_speed").is_not_null())
    bad_q = ~pl.col("wind_speed_Quality_Code").is_in(good) | pl.col("wind_speed_Quality_Code").is_null()
    counts["dropped_speed_quality"] = rows.filter(bad_q).height
    rows = rows.filter(~bad_q).sort(["_t", "_file", "_row"])
    rows = rows.with_columns(pl.col("_t").dt.truncate("1h").alias("_h"))
    hourly = rows.unique(subset=["_h"], keep="first", maintain_order=True).sort("_h")
    counts["dropped_duplicate_hour"] = rows.height - hourly.height
    counts["hours"] = hourly.height

    speed = hourly["wind_speed"].to_numpy().astype(float)
    raw_dir = hourly["wind_direction"].to_numpy().astype(float)
    dir_ok = hourly["wind_direction_Quality_Code"].is_in(good).fill_null(False).to_numpy()
    code = hourly["wind_direction_Measurement_Code"].fill_null("").to_numpy()
    kind = np.full(hourly.height, "wind", dtype="<U8")
    direction = np.full(hourly.height, np.nan)
    has_dir = ~np.isnan(raw_dir)
    # the measurement code C (calm) and V (variable) mark the hours without a direction; 999 is never read as one
    variable = (code == "V") | (has_dir & (raw_dir == VARIABLE_DIRECTION) & (code != "C"))
    calm = ((code == "C") | ((speed == 0.0) & (~has_dir | (raw_dir == 0.0)))) & ~variable
    normal = ~variable & ~calm
    counts["direction_quality_rejected"] = int((normal & has_dir & ~dir_ok).sum())
    kind[variable] = "variable"
    kind[calm] = "calm"
    in_range = (raw_dir >= 0.0) & (raw_dir <= 360.0)
    good_dir = normal & has_dir & dir_ok & in_range
    direction[good_dir] = np.mod(raw_dir[good_dir], 360.0)
    counts["calm"] = int(calm.sum())
    counts["variable"] = int(variable.sum())
    counts["direction_out_of_range"] = int((normal & has_dir & dir_ok & ~in_range).sum())
    return WindRecords(
        hour_utc=hourly["_h"].to_numpy().astype("datetime64[h]"),
        speed_m_s=speed,
        direction_deg=direction,
        kind=kind,
        counts=dict(counts),
        station=meta,
    )


def wind_rose(
    records: WindRecords, n_sectors: int = 16, speed_edges_m_s: Sequence[float] = (3.0, 6.0)
) -> dict[str, Any]:
    """Frequency of the direction the wind blows FROM, by sector and speed bin, as a fraction of all hours of the record."""
    edges = list(speed_edges_m_s)
    labels = [f"0 to {edges[0]:g} m/s"] + [f"{a:g} to {b:g} m/s" for a, b in pairwise(edges)]
    labels.append(f"above {edges[-1]:g} m/s")
    n = len(records.speed_m_s)
    freq = np.zeros((len(labels), n_sectors))
    ok = ~np.isnan(records.direction_deg) & (records.kind == "wind")
    width = 360.0 / n_sectors
    sector = (np.floor(np.mod(records.direction_deg[ok] + width / 2, 360.0) / width)).astype(int)
    sbin = np.searchsorted(np.array(edges), records.speed_m_s[ok], side="left")
    np.add.at(freq, (sbin, sector), 1.0)
    return {
        "sector_centres_deg": [width * k for k in range(n_sectors)],
        "speed_labels": labels,
        "frequency": (freq / n).tolist() if n else freq.tolist(),
        "calm_fraction": float((records.kind == "calm").sum() / n) if n else 0.0,
        "variable_fraction": float((records.kind == "variable").sum() / n) if n else 0.0,
        "n_hours": n,
    }
