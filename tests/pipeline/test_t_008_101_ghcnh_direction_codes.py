"""T-008-101: the wind-direction measurement code of GHCNh rows marks calm and variable winds (pipeline environment).

Requirements: FR-008-20, FR-008-21.

Spec: specs/008-data-pipeline/spec.md section 7 and the module doc of `pitstudio_pipeline.dust.winds`. The real station files
of 2015 to 2024 (USW00024127, read on 2026-11-24) hold direction 999 on every calm and variable hour, with
`wind_direction_Measurement_Code` C (calm, speed 0.0) or V (variable), N for a normal observation, and quality code 9 or blank on
the 999 rows. The code letters follow the ISD wind-observation-type convention; their meaning in the GHCNh documentation text
could not be read (UNVERIFIED), so the code is honoured and the value 999 is never read as a direction.

Oracles: hand-written rows and their hand tally (the reader is `read_ghcnh_wind` of T-008-100).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.dust.winds import read_ghcnh_wind
from pitstudio_pipeline.ingest.schemas import GHCNH_VARIABLES, QUALIFIERS

IDENT = ["STATION", "Station_name", "DATE", "Year", "Month", "Day", "Hour", "Minute", "LATITUDE", "LONGITUDE", "ELEVATION"]
HEADER = IDENT + [v + q for v in GHCNH_VARIABLES for q in ("", *QUALIFIERS)]
SLC = "USW00024127"


def _row(hour: int, speed: str, direction: str, dq: str, code: str) -> str:
    cell = dict.fromkeys(HEADER, "")
    cell.update(STATION=SLC, Station_name="SALT LAKE CITY INTL AP", DATE=f"2020-01-01T{hour:02d}:53:00", Year="2020")
    cell.update(Month="01", Day="01", Hour=f"{hour:02d}", Minute="53", LATITUDE="40.7706", LONGITUDE="-111.965")
    cell.update(ELEVATION="1288.4", wind_speed=speed, wind_speed_Quality_Code="5", wind_direction=direction)
    cell.update(wind_direction_Quality_Code=dq, wind_direction_Measurement_Code=code)
    return "|".join(cell[c] for c in HEADER)


@pytest.fixture
def rec(tmp_path: Path):
    rows = [
        _row(0, "0.0", "999", "9", "C"),  # calm
        _row(1, "3.1", "999", "", "V"),  # variable, blank quality
        _row(2, "4.0", "140", "5", "N"),  # normal
        _row(3, "2.0", "999", "9", ""),  # 999 without a code: variable, never a direction
        _row(4, "5.0", "200", "9", "N"),  # normal observation whose direction quality is not accepted
    ]
    path = tmp_path / "c.psv"
    path.write_text("\n".join(["|".join(HEADER), *rows]) + "\n", encoding="utf-8", newline="\n")
    return read_ghcnh_wind([path], station=SLC)


@pytest.mark.req("FR-008-20")
def test_the_measurement_code_names_calm_and_variable_hours(rec) -> None:
    assert rec.kind.tolist() == ["calm", "variable", "wind", "variable", "wind"]
    assert rec.counts["calm"] == 1
    assert rec.counts["variable"] == 2


@pytest.mark.req("FR-008-21")
def test_a_direction_is_given_only_to_a_normal_observation_with_an_accepted_quality_code(rec) -> None:
    d = rec.direction_deg
    assert d[2] == 140.0
    assert np.isnan(d[[0, 1, 3, 4]]).all()
    assert rec.counts["direction_quality_rejected"] == 1  # the calm and variable rows are not quality rejections
    assert rec.counts["direction_out_of_range"] == 0
