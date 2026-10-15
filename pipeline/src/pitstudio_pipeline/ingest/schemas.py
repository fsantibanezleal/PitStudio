"""Pandera (Polars) schemas of the tabular inputs of `s10_preprocess` (FR-008-20).

Settings: every dtype declared, `coerce=False`, `strict=True`, `nullable=False` unless a column declares otherwise,
and a physical bound only with the unit (SI) and the source that justifies it in the column metadata. The schemas hold
no unit conversion: conversions happen after validation, in `ingest.units` (FR-008-25).

`ghcnh_hourly` follows the NCEI GHCNh per-station PSV (documentation v1.1.0, 2026-03-10): 329 columns, i.e. 11
identification columns and 53 variables with the five qualifier columns `_Measurement_Code`, `_Quality_Code`,
`_Report_Type`, `_Source_Code` and `_Source_Station_ID` each (section III(A) p.6, section X p.18). The column names
were read on 2026-10-11 from the header line of a published station file
(`.../hourly/access/by-station/GHCNh_USW00024127_por.psv`, 329 fields); the identification columns are spelled
`STATION`, `LATITUDE`, `LONGITUDE`, `ELEVATION` there. The value types are an assumption (numeric measurements as
Float64, coded and free-text variables as String) because the PSV carries text only; the two ranges are those of the
documentation (Table 1, p.7). `era5_hourly`, `dewit_slope_failure`, `egms_hambach` and `xu_expansion_v3` describe the
tidy tables that the extraction step writes from those sources, whose raw formats are pinned only at first download
(spec 008 section 7, UNVERIFIED list); they carry the bounds that physics or geometry fix and no others.
"""

from __future__ import annotations

import pandera.polars as pa
import polars as pl

QUALIFIERS = ("_Measurement_Code", "_Quality_Code", "_Report_Type", "_Source_Code", "_Source_Station_ID")
NCEI_DOC = "NCEI GHCNh documentation v1.1.0 (2026-03-10)"
GEOMETRY = "geometric definition of the coordinate"
CALENDAR = "calendar definition"

GHCNH_VARIABLES = (
    "temperature",
    "dew_point_temperature",
    "station_level_pressure",
    "sea_level_pressure",
    "wind_direction",
    "wind_speed",
    "wind_gust",
    "precipitation",
    "relative_humidity",
    "wet_bulb_temperature",
    "pres_wx_MW1",
    "pres_wx_MW2",
    "pres_wx_MW3",
    "pres_wx_AU1",
    "pres_wx_AU2",
    "pres_wx_AU3",
    "pres_wx_AW1",
    "pres_wx_AW2",
    "pres_wx_AW3",
    "snow_depth",
    "visibility",
    "altimeter",
    "pressure_3hr_change",
    "sky_condition",
    "sky_condition_baseht",
    "ceiling_height",
    "sky_cover_layer_1",
    "sky_cover_layer_2",
    "sky_cover_layer_3",
    "sky_cover_layer_4",
    "sky_cover_layer_baseht_1",
    "sky_cover_layer_baseht_2",
    "sky_cover_layer_baseht_3",
    "sky_cover_layer_baseht_4",
    "sky_cover_summation_1",
    "sky_cover_summation_2",
    "sky_cover_summation_3",
    "sky_cover_summation_4",
    "sky_cover_summation_baseht_1",
    "sky_cover_summation_baseht_2",
    "sky_cover_summation_baseht_3",
    "sky_cover_summation_baseht_4",
    "precipitation_5_minute",
    "precipitation_15_minute",
    "precipitation_3_hour",
    "precipitation_6_hour",
    "precipitation_9_hour",
    "precipitation_12_hour",
    "precipitation_15_hour",
    "precipitation_18_hour",
    "precipitation_21_hour",
    "precipitation_24_hour",
    "REM",
)
_TEXT_VARIABLES = ("pres_wx_", "sky_condition", "sky_cover_layer_", "sky_cover_summation_", "REM")


def _is_text(variable: str) -> bool:
    return variable.startswith(_TEXT_VARIABLES) and "baseht" not in variable


def _ghcnh_columns() -> dict[str, pa.Column]:
    columns: dict[str, pa.Column] = {
        "STATION": pa.Column(pl.String, nullable=False),
        "Station_name": pa.Column(pl.String, nullable=True),
        "DATE": pa.Column(
            pl.String,
            pa.Check.str_matches(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),
            nullable=False,
            metadata={"unit": "ISO 8601 UTC", "source": NCEI_DOC + ", section III(A)"},
        ),
        "Year": pa.Column(
            pl.Int64, pa.Check.in_range(1, 9999), nullable=False, metadata={"unit": "year", "source": CALENDAR}
        ),
        "Month": pa.Column(
            pl.Int64, pa.Check.in_range(1, 12), nullable=False, metadata={"unit": "month", "source": CALENDAR}
        ),
        "Day": pa.Column(
            pl.Int64, pa.Check.in_range(1, 31), nullable=False, metadata={"unit": "day", "source": CALENDAR}
        ),
        "Hour": pa.Column(
            pl.Int64, pa.Check.in_range(0, 23), nullable=False, metadata={"unit": "h", "source": CALENDAR}
        ),
        "Minute": pa.Column(
            pl.Int64, pa.Check.in_range(0, 59), nullable=False, metadata={"unit": "min", "source": CALENDAR}
        ),
        "LATITUDE": pa.Column(
            pl.Float64, pa.Check.in_range(-90.0, 90.0), nullable=False, metadata={"unit": "deg", "source": GEOMETRY}
        ),
        "LONGITUDE": pa.Column(
            pl.Float64, pa.Check.in_range(-180.0, 180.0), nullable=False, metadata={"unit": "deg", "source": GEOMETRY}
        ),
        "ELEVATION": pa.Column(pl.Float64, nullable=True),
    }
    for variable in GHCNH_VARIABLES:
        if _is_text(variable):
            columns[variable] = pa.Column(pl.String, nullable=True)
        elif variable == "wind_direction":  # whole degrees from true north, 360 = north, 000 = calm (Table 1, p.7)
            columns[variable] = pa.Column(
                pl.Float64,
                pa.Check.in_range(0.0, 360.0),
                nullable=True,
                metadata={"unit": "deg", "source": NCEI_DOC + ", Table 1, p.7"},
            )
        elif variable == "wind_speed":  # metres per second, never negative (Table 1, p.7)
            columns[variable] = pa.Column(
                pl.Float64,
                pa.Check.ge(0.0),
                nullable=True,
                metadata={"unit": "m/s", "source": NCEI_DOC + ", Table 1, p.7"},
            )
        else:
            columns[variable] = pa.Column(pl.Float64, nullable=True)
        for qualifier in QUALIFIERS:
            columns[variable + qualifier] = pa.Column(pl.String, nullable=True)
    return columns


def _schema(columns: dict[str, pa.Column], unique: list[str] | None = None) -> pa.DataFrameSchema:
    return pa.DataFrameSchema(columns, strict=True, coerce=False, unique=unique)


def _col(dtype: type[pl.DataType], unit: str, source: str, *checks: pa.Check, nullable: bool = False) -> pa.Column:
    return pa.Column(dtype, list(checks), nullable=nullable, coerce=False, metadata={"unit": unit, "source": source})


SCHEMAS: dict[str, pa.DataFrameSchema] = {
    "ghcnh_hourly": _schema(_ghcnh_columns()),
    "era5_hourly": _schema(
        {
            "time": pa.Column(pl.String, nullable=False),
            "latitude": _col(pl.Float64, "deg", GEOMETRY, pa.Check.in_range(-90.0, 90.0)),
            "longitude": _col(pl.Float64, "deg", GEOMETRY, pa.Check.in_range(-180.0, 360.0)),
            "u10": pa.Column(pl.Float64, nullable=False),
            "v10": pa.Column(pl.Float64, nullable=False),
            "t2m": _col(pl.Float64, "K", "thermodynamic temperature cannot be below absolute zero", pa.Check.ge(0.0)),
            "sp": _col(pl.Float64, "Pa", "a pressure is never negative", pa.Check.ge(0.0)),
            "tp": _col(pl.Float64, "m", "an accumulated precipitation is never negative", pa.Check.ge(0.0)),
        },
        unique=["time", "latitude", "longitude"],
    ),
    "dewit_slope_failure": _schema(
        {
            "t": pa.Column(pl.Float64, nullable=False),
            "x": pa.Column(pl.Float64, nullable=False),
        },
        unique=["t"],
    ),
    "egms_hambach": _schema(
        {
            "pid": pa.Column(pl.String, nullable=False),
            "date": pa.Column(pl.String, nullable=False),
            "latitude": _col(pl.Float64, "deg", GEOMETRY, pa.Check.in_range(-90.0, 90.0)),
            "longitude": _col(pl.Float64, "deg", GEOMETRY, pa.Check.in_range(-180.0, 180.0)),
            "displacement": pa.Column(pl.Float64, nullable=False),
        },
        unique=["pid", "date"],
    ),
    "xu_expansion_v3": _schema(
        {
            "mine_id": pa.Column(pl.String, nullable=False),
            "year": _col(pl.Int64, "year", CALENDAR, pa.Check.in_range(1, 9999)),
            "area": _col(pl.Float64, "m2", "an area is never negative", pa.Check.ge(0.0)),
        },
        unique=["mine_id", "year"],
    ),
}
