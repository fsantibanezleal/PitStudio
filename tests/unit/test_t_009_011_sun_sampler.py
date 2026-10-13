"""T-009-011 - FR-009-04, P-009-12 (solar half): structured sun sampler and the stage-frame direction vector.

Oracles (independent of the code under test):
- published worked example of the Solar Position Algorithm: Reda & Andreas 2004, Solar Energy 76(5):577-589,
  https://doi.org/10.1016/j.solener.2003.12.003 (appendix example; values as transcribed in spec 009 section 7 from the
  reference implementation's test vectors, pvlib-python tests/test_spa.py, read 2026-10-06; the NREL page itself was
  unreachable that day, so the transcription is UNVERIFIED against the primary table): 2003-10-17 12:30:30 at UTC-7
  (= 19:30:30 UTC), latitude 39.742476 N, longitude 105.1786 W, elevation 1,830.14 m, pressure 820 mbar, temperature
  11 C, delta-T 67.0 s, refraction at sunrise/sunset 0.5667 deg -> topocentric zenith 50.11162 deg and topocentric
  azimuth 194.340241 deg (eastward from north), tolerance 0.01 deg (FR-009-04);
- analytical: at local solar noon the solar elevation is 90 - |phi - delta| (spec 009 section 7; phi = latitude,
  delta = declination, 23.436 deg south at the December 2025 solstice, almanac value), found here by scanning the day at
  one-minute resolution, tolerance 0.02 deg;
- analytical: the stage frame of spec 004 FR-004-02 is X east, Y north, Z up, so the unit vector TOWARD the sun is
  (cos el sin az, cos el cos az, sin el) with the azimuth measured clockwise from north; hand-evaluated corner cases
  (north horizon (0, 1, 0), east horizon (1, 0, 0), zenith (0, 0, 1), south at 45 deg (0, -sqrt(2)/2, sqrt(2)/2));
  tolerance 1e-9 in float64 (FR-009-04);
- analytical bound for the rejection rule: at latitude 89 N the sun can exceed 5 deg of elevation only while the
  declination is about 4 deg or more (elevation <= 1 + delta at that latitude), i.e. between the end of March and the
  middle of September; every accepted instant must lie in that window;
- Kolmogorov-Smirnov (scipy.stats.kstest) of the day-of-year fraction of accepted instants against the uniform law at
  the equator, where the daylight fraction changes by about 1 % over the year: p >= 1e-3, fixed seed (plan 009
  tolerances).

Expected public API (module `pitstudio_studio.sdg.sun`, package under `studio/src/`):

    SolarPosition                    frozen dataclass: zenith_deg, elevation_deg, azimuth_deg (float); azimuth in
                                     [0, 360) eastward from north; elevation = 90 - zenith; the topocentric values with
                                     atmospheric refraction, as the SPA reports them.
    solar_position(when_utc: datetime.datetime, latitude_deg: float, longitude_deg: float, *, elevation_m: float = 0.0,
                   pressure_mbar: float = 1013.25, temperature_c: float = 15.0, delta_t_s: float = 69.0,
                   refraction_deg: float = 0.5667) -> SolarPosition
        `when_utc` must be timezone-aware (UTC); a naive datetime, NaN/inf coordinates, |latitude| > 90 or
        |longitude| > 180 raise ValueError whose message contains the argument name.
    sun_direction_stage(elevation_deg: float, azimuth_deg: float) -> tuple[float, float, float]
        unit vector from the scene toward the sun in the stage frame (X east, Y north, Z up).
    SunSample                        frozen dataclass: utc (datetime, UTC), elevation_deg, azimuth_deg,
                                     direction_stage (tuple of 3 floats).
    sample_sun(rng: numpy.random.Generator, *, latitude_deg: float, longitude_deg: float, year: int,
               elevation_m: float = 0.0, min_elevation_deg: float = 5.0) -> SunSample
        Draws UTC instants uniformly over [year-01-01T00:00:00Z, (year+1)-01-01T00:00:00Z), rejects those with a solar
        elevation < min_elevation_deg and returns the first accepted one; elevation_deg/azimuth_deg are
        solar_position(...) of that instant; direction_stage = sun_direction_stage(elevation_deg, azimuth_deg).
        Deterministic for a given Generator state.
"""

from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.sdg import sun  # noqa: E402

UTC = dt.UTC
EXAMPLES = 200  # thresholds.yaml property_tests.ci_examples_per_test


def _spa_example() -> sun.SolarPosition:
    return sun.solar_position(
        dt.datetime(2003, 10, 17, 19, 30, 30, tzinfo=UTC),  # 12:30:30 at UTC-7
        39.742476,
        -105.1786,
        elevation_m=1830.14,
        pressure_mbar=820.0,
        temperature_c=11.0,
        delta_t_s=67.0,
        refraction_deg=0.5667,
    )


# ---------------------------------------------------------------- solar position against the SPA example


@pytest.mark.req("FR-009-04")
def test_the_spa_worked_example_zenith_is_reproduced_within_0_01_degrees() -> None:
    pos = _spa_example()
    assert abs(pos.zenith_deg - 50.11162) <= 0.01
    assert abs(pos.elevation_deg - (90.0 - 50.11162)) <= 0.01


@pytest.mark.req("FR-009-04")
def test_the_spa_worked_example_azimuth_is_reproduced_within_0_01_degrees() -> None:
    assert abs(_spa_example().azimuth_deg - 194.340241) <= 0.01


@pytest.mark.req("FR-009-04")
def test_elevation_and_zenith_always_sum_to_ninety_degrees() -> None:
    pos = _spa_example()
    assert pos.elevation_deg + pos.zenith_deg == pytest.approx(90.0, abs=1e-12)


@pytest.mark.req("FR-009-04")
def test_noon_elevation_at_the_december_solstice_is_ninety_minus_latitude_distance_to_declination() -> None:
    lat, lon, delta = -22.5, -69.0, -23.436  # a Chilean site; declination at the 2025 December solstice
    start = dt.datetime(2025, 12, 21, 12, 0, tzinfo=UTC)
    best = max(
        sun.solar_position(start + dt.timedelta(minutes=m), lat, lon).elevation_deg for m in range(0, 24 * 60, 1)
    )
    assert abs(best - (90.0 - abs(lat - delta))) <= 0.02  # 89.064 deg


@pytest.mark.req("FR-009-04")
@pytest.mark.parametrize(
    ("lat", "lon", "elev", "when", "arg"),
    [
        (float("nan"), 0.0, 0.0, dt.datetime(2025, 1, 1, tzinfo=UTC), "latitude_deg"),
        (91.0, 0.0, 0.0, dt.datetime(2025, 1, 1, tzinfo=UTC), "latitude_deg"),
        (0.0, float("inf"), 0.0, dt.datetime(2025, 1, 1, tzinfo=UTC), "longitude_deg"),
        (0.0, 181.0, 0.0, dt.datetime(2025, 1, 1, tzinfo=UTC), "longitude_deg"),
        (0.0, 0.0, float("nan"), dt.datetime(2025, 1, 1, tzinfo=UTC), "elevation_m"),
        (0.0, 0.0, 0.0, dt.datetime(2025, 1, 1), "when_utc"),  # naive datetime
    ],
)
def test_hostile_solar_position_inputs_are_rejected(
    lat: float, lon: float, elev: float, when: dt.datetime, arg: str
) -> None:
    with pytest.raises(ValueError, match=arg):
        sun.solar_position(when, lat, lon, elevation_m=elev)


# ---------------------------------------------------------------- stage-frame vector


@pytest.mark.req("FR-009-04")
@pytest.mark.parametrize(
    ("el", "az", "expected"),
    [
        (0.0, 0.0, (0.0, 1.0, 0.0)),  # north horizon
        (0.0, 90.0, (1.0, 0.0, 0.0)),  # east horizon
        (0.0, 180.0, (0.0, -1.0, 0.0)),
        (0.0, 270.0, (-1.0, 0.0, 0.0)),
        (90.0, 0.0, (0.0, 0.0, 1.0)),  # zenith
        (45.0, 180.0, (0.0, -math.sqrt(0.5), math.sqrt(0.5))),
        (30.0, 90.0, (math.cos(math.radians(30.0)), 0.0, 0.5)),
    ],
)
def test_stage_frame_vector_matches_the_hand_evaluated_conversion(
    el: float, az: float, expected: tuple[float, float, float]
) -> None:
    v = sun.sun_direction_stage(el, az)
    assert len(v) == 3
    for got, want in zip(v, expected, strict=True):
        assert abs(got - want) <= 1e-9


@pytest.mark.req("FR-009-04")
@given(el=st.floats(-90, 90), az=st.floats(0, 360, exclude_max=True))
@settings(max_examples=EXAMPLES, deadline=None)
def test_stage_frame_vector_is_a_unit_vector_with_the_analytical_components(el: float, az: float) -> None:
    v = sun.sun_direction_stage(el, az)
    e, a = math.radians(el), math.radians(az)
    assert math.isclose(math.sqrt(sum(c * c for c in v)), 1.0, abs_tol=1e-9)
    assert abs(v[0] - math.cos(e) * math.sin(a)) <= 1e-9
    assert abs(v[1] - math.cos(e) * math.cos(a)) <= 1e-9
    assert abs(v[2] - math.sin(e)) <= 1e-9


@pytest.mark.req("FR-009-04")
@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_angles_are_rejected_by_the_vector_conversion(bad: float) -> None:
    with pytest.raises(ValueError, match="elevation_deg"):
        sun.sun_direction_stage(bad, 10.0)
    with pytest.raises(ValueError, match="azimuth_deg"):
        sun.sun_direction_stage(10.0, bad)


# ---------------------------------------------------------------- the sampler


@pytest.mark.req("FR-009-04")
def test_the_sampler_is_deterministic_for_a_generator_state_and_differs_between_seeds() -> None:
    kw = {"latitude_deg": -22.5, "longitude_deg": -69.0, "year": 2025}
    a = sun.sample_sun(np.random.default_rng(7), **kw)
    b = sun.sample_sun(np.random.default_rng(7), **kw)
    c = sun.sample_sun(np.random.default_rng(8), **kw)
    assert a == b
    assert a.utc != c.utc


@pytest.mark.req("FR-009-04")
def test_a_sample_carries_the_solar_position_of_its_instant_and_the_stage_vector() -> None:
    s = sun.sample_sun(np.random.default_rng(1), latitude_deg=-22.5, longitude_deg=-69.0, year=2025)
    assert s.utc.tzinfo is not None
    assert s.utc.utcoffset() == dt.timedelta(0)
    pos = sun.solar_position(s.utc, -22.5, -69.0)
    assert abs(s.elevation_deg - pos.elevation_deg) <= 1e-9
    assert abs(s.azimuth_deg - pos.azimuth_deg) <= 1e-9
    want = sun.sun_direction_stage(s.elevation_deg, s.azimuth_deg)
    for got, w in zip(s.direction_stage, want, strict=True):
        assert abs(got - w) <= 1e-9


@pytest.mark.req("FR-009-04")
@pytest.mark.req("P-009-12")
@given(
    seed=st.integers(0, 2**32 - 1),
    lat=st.floats(-60, 60),
    lon=st.floats(-180, 180),
    year=st.integers(2000, 2040),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_every_accepted_sample_has_at_least_five_degrees_of_elevation_inside_the_year(
    seed: int, lat: float, lon: float, year: int
) -> None:
    s = sun.sample_sun(np.random.default_rng(seed), latitude_deg=lat, longitude_deg=lon, year=year)
    assert s.elevation_deg >= 5.0
    assert dt.datetime(year, 1, 1, tzinfo=UTC) <= s.utc < dt.datetime(year + 1, 1, 1, tzinfo=UTC)
    assert sun.solar_position(s.utc, lat, lon).elevation_deg >= 5.0 - 1e-9


@pytest.mark.req("FR-009-04")
def test_the_elevation_floor_is_a_parameter() -> None:
    rng = np.random.default_rng(3)
    for _ in range(50):
        s = sun.sample_sun(rng, latitude_deg=0.0, longitude_deg=0.0, year=2025, min_elevation_deg=45.0)
        assert s.elevation_deg >= 45.0


@pytest.mark.req("FR-009-04")
def test_near_the_pole_only_the_sunlit_season_is_accepted() -> None:
    rng = np.random.default_rng(11)
    lo, hi = dt.datetime(2025, 3, 25, tzinfo=UTC), dt.datetime(2025, 9, 20, tzinfo=UTC)
    for _ in range(200):
        s = sun.sample_sun(rng, latitude_deg=89.0, longitude_deg=0.0, year=2025)
        assert s.elevation_deg >= 5.0
        assert lo <= s.utc <= hi


@pytest.mark.req("FR-009-04")
def test_instants_are_drawn_uniformly_over_the_year_at_the_equator() -> None:
    from scipy import stats

    rng = np.random.default_rng(20261007)
    samples = [sun.sample_sun(rng, latitude_deg=0.0, longitude_deg=0.0, year=2025) for _ in range(3000)]
    t0 = dt.datetime(2025, 1, 1, tzinfo=UTC)
    year_s = (dt.datetime(2026, 1, 1, tzinfo=UTC) - t0).total_seconds()
    frac = [(s.utc - t0).total_seconds() / year_s for s in samples]
    assert stats.kstest(frac, "uniform").pvalue >= 1e-3
    hours = [s.utc.hour + s.utc.minute / 60 for s in samples]
    assert min(hours) < 8.0
    assert max(hours) > 16.0  # daylight instants over the whole day, not a fixed time
    assert {s.utc.month for s in samples} == set(range(1, 13))
