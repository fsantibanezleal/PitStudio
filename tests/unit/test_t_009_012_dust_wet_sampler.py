# ruff: noqa: E501
"""T-009-012 - FR-009-05, FR-009-06: dust extinction from the plume field at the camera and wet-road flags.

Oracles (independent of the code under test):
- FR-009-05, hand calculation of the large-particle mass extinction k_m = 3 Q / (2 rho D) (spec 006 FR-006-15 of
  minephys; Bohren & Huffman 1983) and beta = k_m * C: D = 10 um, rho = 2650 kg/m^3, Q = 2 give
  k_m = 6 / (2 * 2650 * 1e-5) = 113.2075 m^2/kg, and C = 1e-5 kg/m^3 gives beta = 1.132075e-3 1/m = 1.132075 1/km;
  the same value is also taken from the reference implementation `minephys.environment` called directly in this file
  (`mass_extinction_coefficient`, `extinction_coefficient`; the spec names that library as the source of sigma);
  the plume field is a closed-form fixture c(x, y, z) so that the camera position, not a grid convention, decides the
  concentration.
- FR-009-06, hand calculation of plan 009: watered 10:00, drying time 60 min -> wet at 10:59, dry at 11:01; the
  boundary 11:00 is wet ("<="); a pass after the image instant does not count; a segment with no earlier pass is dry
  and carries no `minutes_since_watering`.

Expected public API (module `pitstudio_studio.sdg.dust_wet`, package under `studio/src/`):

    DustField                      typing.Protocol with `concentration_kg_m3(x_m: float, y_m: float, z_m: float) -> float`
                                   (the scenario's plume field, spec 006 / DC-006-xx; any object with that method).
    dust_extinction_per_km(field: DustField, camera_xyz_m: Sequence[float], *, particle_diameter_m: float,
                           particle_density_kg_m3: float, extinction_efficiency: float | None = None) -> float
        sigma [1/km] = 1000 * minephys.environment.extinction_coefficient(C, mass_extinction_coefficient(D, rho, Q))
        with C = field.concentration_kg_m3(*camera_xyz_m); Q = extinction_efficiency, or minephys' default row when None.
        ValueError (message names the argument) for non-finite or non-positive diameter/density, a camera position
        that is not 3 finite numbers, or a field value that is NaN, inf or negative (message contains "concentration").
    wet_segments(schedule: Mapping[str, Sequence[datetime.datetime]], when_utc: datetime.datetime, *,
                 drying_time_min: float = 60.0) -> list[dict]
        One dict per segment id (in the mapping's order), shaped as DC-009-01 `wet_segment`: {"segment_id": str,
        "wet": bool, "minutes_since_watering": float}; minutes_since_watering = minutes from the LAST watering pass at
        or before `when_utc` (passes after it are ignored); the key is omitted when no such pass exists.
        wet == (minutes_since_watering <= drying_time_min). All datetimes timezone-aware.
        ValueError for a naive datetime (message contains "schedule" or "when_utc"), drying_time_min <= 0 or non-finite
        (message contains "drying_time_min"), or a segment id that does not match ^[a-z0-9][a-z0-9_-]{0,95}$ (message
        contains "segment").
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.sdg import dust_wet  # noqa: E402

UTC = dt.UTC
EXAMPLES = 200
D, RHO, Q = 10e-6, 2650.0, 2.0
KM = 6.0 / (2.0 * RHO * D)  # 113.2075... m^2/kg, hand calculation above


class _Gauss:
    """c(x, y, z) = 2e-5 exp(-(x^2 + y^2) / 2500) exp(-z / 50) kg/m^3: closed form, decays away from the source."""

    def concentration_kg_m3(self, x_m: float, y_m: float, z_m: float) -> float:
        return 2e-5 * math.exp(-(x_m * x_m + y_m * y_m) / 2500.0) * math.exp(-z_m / 50.0)


class _Const:
    def __init__(self, value: float) -> None:
        self.value = value

    def concentration_kg_m3(self, x_m: float, y_m: float, z_m: float) -> float:
        return self.value


def _wet_segment_validator():
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "perception-dataset.schema.json",
        ROOT / "specs" / "009-perception" / "contracts" / "perception-dataset.schema.json",
    ):
        if p.is_file():
            s = json.loads(p.read_text(encoding="utf-8"))
            return Draft202012Validator({"$ref": "#/$defs/wet_segment", "$defs": s["$defs"]})
    raise AssertionError("perception-dataset.schema.json not found")


# ---------------------------------------------------------------- FR-009-05


@pytest.mark.req("FR-009-05")
def test_sigma_of_a_constant_field_equals_the_hand_calculated_beer_lambert_extinction() -> None:
    sigma = dust_wet.dust_extinction_per_km(
        _Const(1e-5), (10.0, 20.0, 5.0), particle_diameter_m=D, particle_density_kg_m3=RHO, extinction_efficiency=Q
    )
    assert sigma == pytest.approx(1000.0 * KM * 1e-5, rel=1e-9)  # 1.132075 1/km
    assert sigma == pytest.approx(1.132075, abs=1e-6)


@pytest.mark.req("FR-009-05")
def test_sigma_is_read_at_the_camera_position_of_the_field() -> None:
    field = _Gauss()
    for cam in [(0.0, 0.0, 0.0), (30.0, -40.0, 12.0), (-100.0, 5.0, 60.0)]:
        want = 1000.0 * KM * field.concentration_kg_m3(*cam)
        got = dust_wet.dust_extinction_per_km(
            field, cam, particle_diameter_m=D, particle_density_kg_m3=RHO, extinction_efficiency=Q
        )
        assert got == pytest.approx(want, rel=1e-9)


@pytest.mark.req("FR-009-05")
def test_sigma_equals_the_minephys_environment_reference() -> None:
    from minephys import environment

    field = _Gauss()
    cam = (30.0, -40.0, 12.0)
    c = field.concentration_kg_m3(*cam)
    ref = 1000.0 * float(environment.extinction_coefficient(c, environment.mass_extinction_coefficient(D, RHO, Q)))
    got = dust_wet.dust_extinction_per_km(
        field, cam, particle_diameter_m=D, particle_density_kg_m3=RHO, extinction_efficiency=Q
    )
    assert got == pytest.approx(ref, rel=1e-12)


@pytest.mark.req("FR-009-05")
def test_a_clean_air_camera_has_zero_extinction_and_sigma_is_linear_in_concentration() -> None:
    kw = {"particle_diameter_m": D, "particle_density_kg_m3": RHO, "extinction_efficiency": Q}
    assert dust_wet.dust_extinction_per_km(_Const(0.0), (0.0, 0.0, 0.0), **kw) == 0.0
    s1 = dust_wet.dust_extinction_per_km(_Const(1e-6), (0.0, 0.0, 0.0), **kw)
    s3 = dust_wet.dust_extinction_per_km(_Const(3e-6), (0.0, 0.0, 0.0), **kw)
    assert s3 == pytest.approx(3.0 * s1, rel=1e-12)


@pytest.mark.req("FR-009-05")
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1e-6])
def test_a_bad_field_value_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="concentration"):
        dust_wet.dust_extinction_per_km(
            _Const(value), (0.0, 0.0, 0.0), particle_diameter_m=D, particle_density_kg_m3=RHO, extinction_efficiency=Q
        )


@pytest.mark.req("FR-009-05")
@pytest.mark.parametrize(
    ("cam", "diameter", "density", "arg"),
    [
        ((0.0, 0.0), D, RHO, "camera_xyz_m"),
        ((0.0, float("nan"), 0.0), D, RHO, "camera_xyz_m"),
        ((0.0, 0.0, 0.0), 0.0, RHO, "particle_diameter_m"),
        ((0.0, 0.0, 0.0), float("nan"), RHO, "particle_diameter_m"),
        ((0.0, 0.0, 0.0), D, -2650.0, "particle_density_kg_m3"),
        ((0.0, 0.0, 0.0), D, float("inf"), "particle_density_kg_m3"),
    ],
)
def test_hostile_arguments_are_rejected_naming_the_argument(
    cam: tuple[float, ...], diameter: float, density: float, arg: str
) -> None:
    with pytest.raises(ValueError, match=arg):
        dust_wet.dust_extinction_per_km(
            _Const(1e-5), cam, particle_diameter_m=diameter, particle_density_kg_m3=density, extinction_efficiency=Q
        )


# ---------------------------------------------------------------- FR-009-06

T0 = dt.datetime(2025, 3, 14, 10, 0, tzinfo=UTC)  # the watering pass of the hand example


def _flag(when: dt.datetime, drying: float = 60.0) -> dict:
    (seg,) = dust_wet.wet_segments({"haul-road-03": [T0]}, when, drying_time_min=drying)
    return seg


@pytest.mark.req("FR-009-06")
def test_a_segment_watered_at_ten_is_wet_at_10_59_and_dry_at_11_01() -> None:
    wet = _flag(T0 + dt.timedelta(minutes=59))
    dry = _flag(T0 + dt.timedelta(minutes=61))
    assert wet["segment_id"] == "haul-road-03"
    assert wet["wet"] is True
    assert wet["minutes_since_watering"] == pytest.approx(59.0)
    assert dry["wet"] is False
    assert dry["minutes_since_watering"] == pytest.approx(61.0)


@pytest.mark.req("FR-009-06")
def test_the_drying_time_boundary_is_wet_and_the_drying_time_is_a_parameter() -> None:
    assert _flag(T0 + dt.timedelta(minutes=60))["wet"] is True  # "<= drying time"
    assert _flag(T0 + dt.timedelta(minutes=60, seconds=1))["wet"] is False
    assert _flag(T0 + dt.timedelta(minutes=100), drying=120.0)["wet"] is True
    assert _flag(T0 + dt.timedelta(minutes=100), drying=90.0)["wet"] is False


@pytest.mark.req("FR-009-06")
def test_the_last_pass_at_or_before_the_instant_decides_and_later_passes_are_ignored() -> None:
    passes = [T0, T0 + dt.timedelta(minutes=120), T0 + dt.timedelta(minutes=500)]
    when = T0 + dt.timedelta(minutes=150)  # last earlier pass at +120 min -> 30 min ago -> wet
    (seg,) = dust_wet.wet_segments({"ramp-01": passes}, when)
    assert seg["wet"] is True
    assert seg["minutes_since_watering"] == pytest.approx(30.0)
    (seg2,) = dust_wet.wet_segments({"ramp-01": passes}, T0 + dt.timedelta(minutes=300))  # 180 min after the last pass
    assert seg2["wet"] is False
    assert seg2["minutes_since_watering"] == pytest.approx(180.0)


@pytest.mark.req("FR-009-06")
def test_a_segment_with_no_earlier_pass_is_dry_and_has_no_minutes_field() -> None:
    segs = dust_wet.wet_segments(
        {"never": [], "later": [T0 + dt.timedelta(minutes=5)], "ok": [T0 - dt.timedelta(minutes=10)]}, T0
    )
    assert [s["segment_id"] for s in segs] == ["never", "later", "ok"]
    assert segs[0] == {"segment_id": "never", "wet": False}
    assert segs[1] == {"segment_id": "later", "wet": False}
    assert segs[2]["wet"] is True
    assert segs[2]["minutes_since_watering"] == pytest.approx(10.0)


@pytest.mark.req("FR-009-06")
def test_every_record_validates_against_the_wet_segment_definition_of_the_dataset_index() -> None:
    v = _wet_segment_validator()
    schedule = {"a": [T0], "b": [], "c": [T0 - dt.timedelta(days=2)]}
    for seg in dust_wet.wet_segments(schedule, T0 + dt.timedelta(minutes=30)):
        assert list(v.iter_errors(seg)) == []


@pytest.mark.req("FR-009-06")
@given(
    minutes=st.floats(0, 5000, allow_nan=False),
    drying=st.floats(1, 1440, allow_nan=False),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_wet_if_and_only_if_the_elapsed_time_is_at_most_the_drying_time(minutes: float, drying: float) -> None:
    when = T0 + dt.timedelta(seconds=minutes * 60.0)
    (seg,) = dust_wet.wet_segments({"seg": [T0]}, when, drying_time_min=drying)
    elapsed = (when - T0).total_seconds() / 60.0  # the exact timedelta, as the implementation sees it
    assume(abs(elapsed - drying) > 1e-6)  # stay clear of microsecond rounding at the boundary (boundary: own test)
    assert seg["wet"] is (elapsed <= drying)
    assert seg["minutes_since_watering"] == pytest.approx(elapsed, abs=1e-6)


@pytest.mark.req("FR-009-06")
@pytest.mark.parametrize(
    ("schedule", "when", "drying", "arg"),
    [
        ({"a": [dt.datetime(2025, 1, 1, 10, 0)]}, T0, 60.0, "schedule"),  # naive pass
        ({"a": [T0]}, dt.datetime(2025, 1, 1, 10, 0), 60.0, "when_utc"),  # naive instant
        ({"a": [T0]}, T0, 0.0, "drying_time_min"),
        ({"a": [T0]}, T0, -5.0, "drying_time_min"),
        ({"a": [T0]}, T0, float("nan"), "drying_time_min"),
        ({"A B": [T0]}, T0, 60.0, "segment"),  # id outside the artefact-id pattern
        ({"": [T0]}, T0, 60.0, "segment"),
    ],
)
def test_hostile_wet_inputs_are_rejected_naming_the_argument(
    schedule: dict, when: dt.datetime, drying: float, arg: str
) -> None:
    with pytest.raises(ValueError, match=arg):
        dust_wet.wet_segments(schedule, when, drying_time_min=drying)
