"""T-008-100: the hourly wind of NOAA GHCNh station files, read for the dust case C3 (pipeline test, pipeline environment).

Requirements: FR-008-20, FR-008-21, FR-008-25.

Spec: specs/008-data-pipeline/spec.md section 7 (NOAA GHCNh format, documentation v1.1.0): per-station PSV files with 329
columns, `DATE` in ISO 8601 UTC, `wind_direction` in whole degrees from true north with 360 = north and 000 = calm,
`wind_speed` in metres per second; every variable has the qualifier columns `_Measurement_Code`, `_Quality_Code`,
`_Report_Type`, `_Source_Code`, `_Source_Station_ID`. The real files of the station also carry direction 999 for a variable
wind (read on the 2015 to 2024 files of USW00024127; the documentation text itself was not readable, so the meaning is
UNVERIFIED and the reader names the rows instead of guessing a direction).

Expected public API (module `pitstudio_pipeline.dust.winds`):
    read_ghcnh_wind(paths, *, station, good_quality=("1", "5")) -> WindRecords
        one record per UTC clock hour (the earliest valid record of the hour wins); fields `hour_utc` (datetime64[h]),
        `speed_m_s`, `direction_deg` (degrees from north in [0, 360), NaN when the hour has no usable direction), `kind`
        ("wind", "calm", "variable"), `counts` (dict) and `station` (dict of id, name, latitude, longitude, elevation).
        A record whose speed or its quality code is missing or not in `good_quality` is dropped and counted. A file of
        another station raises `StationMismatch`.
    wind_rose(records, n_sectors=16, speed_edges_m_s=(3.0, 6.0)) -> dict
        `sector_centres_deg`, `speed_labels`, `frequency` (speed bin x sector, fraction of all hours), `calm_fraction`,
        `variable_fraction`, `n_hours`.

Oracles (none of them is the code under test): hand-written PSV rows with a hand tally of the expected hours and rose.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.dust.winds import StationMismatch, read_ghcnh_wind, wind_rose
from pitstudio_pipeline.ingest.schemas import GHCNH_VARIABLES, QUALIFIERS

IDENT = ["STATION", "Station_name", "DATE", "Year", "Month", "Day", "Hour", "Minute", "LATITUDE", "LONGITUDE", "ELEVATION"]
HEADER = IDENT + [v + q for v in GHCNH_VARIABLES for q in ("", *QUALIFIERS)]
SLC = "USW00024127"


def _row(date: str, speed: str, direction: str, *, sq: str = "5", dq: str = "5", station: str = SLC) -> str:
    cell = dict.fromkeys(HEADER, "")
    y, m, rest = date.split("-", 2)
    d, hm = rest.split("T")
    hh, mm, _ = hm.split(":")
    cell.update(
        STATION=station, Station_name="SALT LAKE CITY INTL AP", DATE=date, Year=y, Month=m, Day=d, Hour=hh, Minute=mm
    )
    cell.update(LATITUDE="40.7706", LONGITUDE="-111.965", ELEVATION="1288.4")
    cell.update(wind_speed=speed, wind_speed_Quality_Code=sq, wind_direction=direction, wind_direction_Quality_Code=dq)
    return "|".join(cell[c] for c in HEADER)


def _file(tmp_path: Path, name: str, rows: list[str]) -> Path:
    path = tmp_path / name
    path.write_text("\n".join(["|".join(HEADER), *rows]) + "\n", encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def two_years(tmp_path: Path) -> list[Path]:
    a = _file(
        tmp_path,
        "a.psv",
        [
            _row("2020-01-01T00:53:00", "2.0", "90"),  # hour 0: east wind, slow
            _row("2020-01-01T00:59:00", "9.9", "270"),  # same hour, later: dropped as a duplicate hour
            _row("2020-01-01T01:53:00", "4.0", "360"),  # north, middle bin
            _row("2020-01-01T02:53:00", "0.0", "0"),  # calm
            _row("2020-01-01T03:53:00", "7.0", "999"),  # variable direction with wind
            _row("2020-01-01T04:53:00", "", "180"),  # no speed: dropped
            _row("2020-01-01T05:53:00", "5.0", "180", sq="3"),  # speed failed quality: dropped
        ],
    )
    b = _file(
        tmp_path,
        "b.psv",
        [
            _row("2021-06-01T12:53:00", "6.5", "225"),  # south-west, fast
            _row("2021-06-01T13:53:00", "3.0", "45", dq="3"),  # direction failed quality: speed kept, no direction
        ],
    )
    return [a, b]


def test_one_record_per_hour_with_the_dropped_rows_counted(two_years) -> None:
    rec = read_ghcnh_wind(two_years, station=SLC)
    assert [str(h) for h in rec.hour_utc] == [
        "2020-01-01T00",
        "2020-01-01T01",
        "2020-01-01T02",
        "2020-01-01T03",
        "2021-06-01T12",
        "2021-06-01T13",
    ]
    assert rec.speed_m_s.tolist() == [2.0, 4.0, 0.0, 7.0, 6.5, 3.0]
    assert rec.counts["rows"] == 9
    assert rec.counts["dropped_no_speed"] == 1
    assert rec.counts["dropped_speed_quality"] == 1
    assert rec.counts["dropped_duplicate_hour"] == 1
    assert rec.counts["hours"] == 6
    assert rec.station["id"] == SLC
    assert rec.station["latitude"] == pytest.approx(40.7706)


def test_direction_north_is_zero_calm_and_variable_are_named_never_guessed(two_years) -> None:
    rec = read_ghcnh_wind(two_years, station=SLC)
    assert rec.kind.tolist() == ["wind", "wind", "calm", "variable", "wind", "wind"]
    d = rec.direction_deg
    assert d[0] == 90.0
    assert d[1] == 0.0  # 360 is north and is stored as 0
    assert np.isnan(d[2])  # calm
    assert np.isnan(d[3])  # variable
    assert d[4] == 225.0
    assert np.isnan(d[5])  # direction quality code not accepted
    assert rec.counts["calm"] == 1
    assert rec.counts["variable"] == 1
    assert rec.counts["direction_quality_rejected"] == 1


def test_the_accepted_quality_codes_are_a_parameter(two_years) -> None:
    rec = read_ghcnh_wind(two_years, station=SLC, good_quality=("5", "3"))
    assert rec.counts["dropped_speed_quality"] == 0
    assert rec.counts["hours"] == 7


def test_a_file_of_another_station_is_refused(tmp_path: Path) -> None:
    path = _file(tmp_path, "x.psv", [_row("2020-01-01T00:53:00", "2.0", "90", station="USW00099999")])
    with pytest.raises(StationMismatch):
        read_ghcnh_wind([path], station=SLC)


def test_the_rose_is_the_hand_tally(two_years) -> None:
    rec = read_ghcnh_wind(two_years, station=SLC)
    rose = wind_rose(rec, n_sectors=16, speed_edges_m_s=(3.0, 6.0))
    assert rose["n_hours"] == 6
    assert rose["sector_centres_deg"][:3] == [0.0, 22.5, 45.0]
    f = np.array(rose["frequency"])
    assert f.shape == (3, 16)
    # speed bins: (0, 3], (3, 6], above 6; sector k centred on 22.5 k degrees
    assert f[0, 4] == pytest.approx(1 / 6)  # 2.0 m/s from 90 degrees (sector 4)
    assert f[1, 0] == pytest.approx(1 / 6)  # 4.0 m/s from north (sector 0)
    assert f[2, 10] == pytest.approx(1 / 6)  # 6.5 m/s from 225 degrees (sector 10)
    assert f.sum() == pytest.approx(2 / 6 + 1 / 6)  # three hours with a usable direction and speed
    assert rose["calm_fraction"] == pytest.approx(1 / 6)
    assert rose["variable_fraction"] == pytest.approx(1 / 6)
    # the sixth hour has a speed but no accepted direction: the rest of the fractions sum to one
    assert f.sum() + rose["calm_fraction"] + rose["variable_fraction"] + 1 / 6 == pytest.approx(1.0)
    assert rose["speed_labels"][0] == "0 to 3 m/s"


def test_the_sector_edges_lie_half_a_sector_either_side_of_the_centre(tmp_path: Path) -> None:
    rows = [_row(f"2020-01-01T{h:02d}:53:00", "4.0", d) for h, d in enumerate(["349", "348", "11", "12"])]
    rec = read_ghcnh_wind([_file(tmp_path, "e.psv", rows)], station=SLC)
    f = np.array(wind_rose(rec)["frequency"])[1]
    # 348.75 and 11.25 are the edges of the north sector: 349 and 11 in it, 348 and 12 out
    assert f[0] == pytest.approx(2 / 4)
    assert f[15] == pytest.approx(1 / 4)
    assert f[1] == pytest.approx(1 / 4)
