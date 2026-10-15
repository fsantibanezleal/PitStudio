"""T-010-050: slope-radar (S4b) series builder, line-of-sight projection and the wrapping flag.

Requirements: FR-010-34, FR-010-36, P-010-15.
Spec: specs/010-slope/spec.md section 3.4 (FR-010-34, FR-010-36), section 4 (P-010-15), section 7 (Radar row);
plan.md rows FR-010-34 / FR-010-36 (hand geometry; increments of 0.24 lambda and 0.26 lambda; the Bingham 2013 worked
example).

Expected API (module `pitstudio.slope.radar`, numpy only; units: positions in m, displacements and wavelength in mm,
time in h):
- `InvalidRadarConfigError(ValueError)` (T-010-051 and T-010-055 specify its triggers; attribute `field`).
- `los_unit_vectors(radar_position_m, pixel_positions_m) -> (N, 3)`: the unit vector e from the radar to each pixel.
- `project_los(displacement_mm, radar_position_m, pixel_positions_m) -> d`: d = u . e (positive = away from the radar);
  `displacement_mm` has shape (N, 3) (one vector per pixel) or (N, T, 3); the result (N,) or (N, T).
- `gaussian_weight(pixel_positions_m, peak_position_m, sigma_w_m=30.0) -> (N,)`: exp(-|x - x_peak|^2 / (2 sigma_w^2)),
  peak 1.
- `wall_displacement_field(omega_mm, pixel_positions_m, peak_position_m, dip_vectors, sigma_w_m=30.0) -> (N, T, 3)`:
  the event
  displacement omega(t) (mm, shape (T,)) times the Gaussian weight times the unit vector of each facet's down-dip
  direction
  (`dip_vectors` (N, 3), normalised by the function).
- irst_ambiguous_scan(d_mm, wavelength_mm) -> int | None`: the first scan index k >= 1 with |d_k - d_{k-1}| >= lambda
  / 4.
- `build_radar_series(*, event_id, t_h, radar, pixels, snr, run_seed, ar1_rho=None, stratum="snr_obs") -> dict[int,
  PixelSeries]`
  with `radar` = {"position_m", "wavelength_mm", "scan_interval_min"} and `pixels` = [{"pixel_id": int, "position_m":
  [x, y, z],
  "displacement_mm": (T, 3) array}]. `PixelSeries.record` is a `radar-pixel` document of
  `contracts/displacement-series.schema.json` (d in `los_displacement_mm`, the unwrapped measurement in
  `measured_los_displacement_mm`, per-scan `wrap_flags`, `status`, `ambiguous_from_scan`, `psi_deg`);
  `PixelSeries.d_mm`,
  `.measured_mm`, `.phase`, `.noise_mm` are the arrays. With `snr` = None the series carries no noise (analytical
  checks).
  A pixel flagged ambiguous has `status` "ambiguous (phase wrapping)", `ambiguous_from_scan` = the first scan whose
  increment reaches
  lambda / 4 and `wrap_flags` True from that scan on, and is excluded from TTF evaluation (`PixelSeries.evaluable`
  False).
- `build_radar_map(series, scan_index) -> dict`: a `radar-map` document with `ambiguous_pixels` counted.

Oracles: hand geometry (radar at the origin, pixel at (100, 0, 0): motion (1, 0, 0) gives d = +1, (0, 1, 0) gives 0,
(-1, 0, 0)
gives -1); a 3-4-5 projection; the Gaussian weight at 30 m (e^-1/2); increments of 0.24 lambda and 0.26 lambda; the
Bingham 2013
worked example of the M23 page (50.8 mm/day, 240 scans/day: 0.2117 mm per scan, below lambda / 4 = 4.36 mm for lambda =
17.43 mm; one scan per day: 50.8 mm >= 4.36 mm, flagged); P-010-15 on random walls (Hypothesis).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as lem_ref
from pitstudio.slope import radar

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
ORIGIN = np.zeros(3)


def _radar(wavelength=17.4, scan_min=6.0, pos=(0.0, 0.0, 0.0)):
    return {"position_m": list(pos), "wavelength_mm": wavelength, "scan_interval_min": scan_min}


# ---------------------------------------------------------------------------------------------------------------------
# projection


@pytest.mark.req("FR-010-34")
def test_hand_geometry_parallel_perpendicular_and_toward() -> None:
    pix = np.array([[100.0, 0.0, 0.0]])
    assert radar.project_los(np.array([[1.0, 0.0, 0.0]]), ORIGIN, pix) == pytest.approx([1.0], abs=1e-15)
    assert radar.project_los(np.array([[0.0, 1.0, 0.0]]), ORIGIN, pix) == pytest.approx([0.0], abs=1e-15)
    assert radar.project_los(np.array([[0.0, 0.0, 7.0]]), ORIGIN, pix) == pytest.approx([0.0], abs=1e-15)
    assert radar.project_los(np.array([[-1.0, 0.0, 0.0]]), ORIGIN, pix) == pytest.approx(
        [-1.0], abs=1e-15
    )  # toward the radar
    assert radar.los_unit_vectors(ORIGIN, pix) == pytest.approx(np.array([[1.0, 0.0, 0.0]]))


@pytest.mark.req("FR-010-34")
def test_a_3_4_5_projection_by_hand() -> None:
    pix = np.array([[300.0, 400.0, 0.0]])  # 500 m away, e = (0.6, 0.8, 0)
    u = np.array([[10.0, 5.0, 2.0]])
    assert radar.project_los(u, ORIGIN, pix)[0] == pytest.approx(10 * 0.6 + 5 * 0.8, rel=1e-12)  # 10
    shifted = radar.project_los(u, np.array([100.0, 100.0, 50.0]), pix + np.array([100.0, 100.0, 50.0]))
    assert shifted[0] == pytest.approx(10.0, rel=1e-12)  # a translated radar and wall: the same LOS


@pytest.mark.req("FR-010-34")
def test_project_los_accepts_a_time_axis() -> None:
    pix = np.array([[100.0, 0.0, 0.0], [0.0, 100.0, 0.0]])
    u = np.zeros((2, 3, 3))
    u[:, :, 0] = [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0]]
    d = radar.project_los(u, ORIGIN, pix)
    assert d.shape == (2, 3)
    assert d[0] == pytest.approx([1.0, 2.0, 3.0])
    assert d[1] == pytest.approx([0.0, 0.0, 0.0], abs=1e-15)


@pytest.mark.req("FR-010-34")
def test_gaussian_weight_peaks_at_one_and_is_e_to_the_minus_half_at_one_sigma() -> None:
    peak = np.array([10.0, 20.0, 5.0])
    pix = np.array(
        [
            peak,
            peak + np.array([30.0, 0.0, 0.0]),
            peak + np.array([0.0, 0.0, 60.0]),
            peak + np.array([30.0 / math.sqrt(2), 30.0 / math.sqrt(2), 0.0]),
        ]
    )
    w = radar.gaussian_weight(pix, peak)  # sigma_w = 30 m
    assert w == pytest.approx([1.0, math.exp(-0.5), math.exp(-2.0), math.exp(-0.5)], rel=1e-12)
    assert radar.gaussian_weight(pix, peak, sigma_w_m=60.0)[1] == pytest.approx(math.exp(-0.125), rel=1e-12)


@pytest.mark.req("FR-010-34")
def test_the_wall_field_scales_the_event_by_the_weight_along_the_unit_dip_vector() -> None:
    omega = np.array([0.0, 1.0, 4.0])
    peak = np.array([0.0, 0.0, 0.0])
    pix = np.array([[0.0, 0.0, 0.0], [30.0, 0.0, 0.0]])
    dip = np.array([[0.0, 3.0, 4.0], [0.0, 0.0, -2.0]])  # not normalised: the function normalises
    f = radar.wall_displacement_field(omega, pix, peak, dip)
    assert f.shape == (2, 3, 3)
    assert f[0, 2] == pytest.approx(4.0 * 1.0 * np.array([0.0, 0.6, 0.8]), rel=1e-12)
    assert f[1, 2] == pytest.approx(4.0 * math.exp(-0.5) * np.array([0.0, 0.0, -1.0]), rel=1e-12)
    assert f[:, 0] == pytest.approx(0.0, abs=1e-15)


# ---------------------------------------------------------------------------------------------------------------------
# wrapping flag (FR-010-36)


@pytest.mark.req("FR-010-36")
def test_increments_of_0_24_and_0_26_wavelengths_straddle_the_lambda_over_four_rule() -> None:
    lam = 20.0
    ok = np.cumsum([0.0, 0.24 * lam, 0.24 * lam, 0.24 * lam])
    assert radar.first_ambiguous_scan(ok, lam) is None
    bad = np.cumsum([0.0, 0.24 * lam, 0.26 * lam, 0.24 * lam])
    assert radar.first_ambiguous_scan(bad, lam) == 2  # the increment ending at scan 2 is 0.26 lambda >= lambda / 4


@pytest.mark.req("FR-010-36")
def test_an_increment_of_exactly_lambda_over_four_is_ambiguous() -> None:
    assert radar.first_ambiguous_scan(np.array([0.0, 4.0, 8.0]), 16.0) == 1  # 4.0 == 16 / 4, exactly representable
    assert radar.first_ambiguous_scan(np.array([0.0, 3.9999999, 7.9999998]), 16.0) is None


@pytest.mark.req("FR-010-36")
def test_bingham_2013_worked_example_with_240_scans_per_day_and_with_a_daily_revisit() -> None:
    lam = 17.43
    per_scan = 50.8 / 240.0  # 0.2117 mm per 6-minute scan
    assert per_scan == pytest.approx(0.2117, abs=1e-4)
    assert radar.first_ambiguous_scan(np.arange(10) * per_scan, lam) is None
    assert radar.first_ambiguous_scan(np.arange(10) * 50.8, lam) == 1  # one scan a day: 50.8 mm >= 4.36 mm
    assert lam / 4 == pytest.approx(4.36, abs=0.005)


@pytest.mark.req("FR-010-36")
def test_the_ambiguous_flag_is_set_from_the_first_ambiguous_scan_on_and_counted_in_the_map() -> None:
    lam, n = 16.0, 30
    t = 0.1 * np.arange(n)
    slow = np.zeros((n, 3))
    slow[:, 0] = 0.05 * np.arange(n)
    fast = np.zeros((n, 3))
    fast[:, 0] = np.concatenate(
        [0.5 * np.arange(10), 5.0 + 5.0 * np.arange(1, n - 9)]
    )  # increment 5 mm >= 4 mm from scan 10
    pixels = [
        {"pixel_id": 1, "position_m": [100.0, 0.0, 0.0], "displacement_mm": slow},
        {"pixel_id": 2, "position_m": [100.0, 5.0, 0.0], "displacement_mm": fast},
    ]
    out = radar.build_radar_series(
        event_id="voight-test-snr-obs-000001", t_h=t, radar=_radar(lam), pixels=pixels, snr=None, run_seed=1
    )
    ok, amb = out[1], out[2]
    assert ok.record["status"] == "ok"
    assert "ambiguous_from_scan" not in ok.record
    assert not any(ok.record["wrap_flags"])
    assert ok.evaluable is True
    assert amb.record["status"] == "ambiguous (phase wrapping)"
    assert amb.record["ambiguous_from_scan"] == 10
    flags = amb.record["wrap_flags"]
    assert flags[:10] == [False] * 10
    assert flags[10:] == [True] * (n - 10)
    assert amb.evaluable is False
    for s in out.values():
        assert lem_ref.schema_errors(s.record, "displacement-series") == []
    m = radar.build_radar_map(out, 12)
    assert m["kind"] == "radar-map"
    assert m["scan_index"] == 12
    assert m["ambiguous_pixels"] == 1
    assert {p["pixel_id"]: p["status"] for p in m["pixels"]} == {1: "ok", 2: "ambiguous (phase wrapping)"}
    assert lem_ref.schema_errors(m, "displacement-series") == []


@pytest.mark.req("FR-010-34")
def test_a_noise_free_series_records_the_projected_displacement_and_the_unwrapped_measurement() -> None:
    n = 40
    t = np.arange(n) * 0.1
    u = np.zeros((n, 3))
    u[:, 0] = 0.1 * np.arange(n) ** 1.5 * 0.1  # moving along +x, away from a radar at the origin
    pix = {"pixel_id": 7, "position_m": [100.0, 0.0, 0.0], "displacement_mm": u}
    s = radar.build_radar_series(
        event_id="voight-test-snr-obs-000002", t_h=t, radar=_radar(17.4), pixels=[pix], snr=None, run_seed=3
    )[7]
    assert s.d_mm == pytest.approx(u[:, 0], rel=1e-12)
    assert s.record["los_displacement_mm"] == pytest.approx(u[:, 0].tolist(), rel=1e-12)
    # no noise and increments below lambda / 4: the unwrapped measurement is d - d(t0) = d
    assert s.measured_mm == pytest.approx(u[:, 0], abs=1e-9 * 17.4)
    assert s.record["psi_deg"] == pytest.approx(0.0, abs=1e-6)
    assert s.record["sign_convention"] == "positive = away from the radar"
    assert s.record["pixel_position_m"] == [100.0, 0.0, 0.0]
    assert s.record["radar"] == _radar(17.4)


# ---------------------------------------------------------------------------------------------------------------------
# P-010-15


@st.composite
def _geometry(draw):
    radar_pos = np.array([draw(st.floats(-2000, 2000)) for _ in range(3)])
    direction = np.array([draw(st.floats(-1, 1)) for _ in range(3)])
    assume(np.linalg.norm(direction) > 1e-3)
    direction = direction / np.linalg.norm(direction)
    dist = draw(st.floats(50.0, 5000.0))
    pixel = radar_pos + dist * direction
    u = np.array([draw(st.floats(-10, 10)) for _ in range(3)])
    return radar_pos, pixel, u


@pytest.mark.req("P-010-15")
@PROP
@given(_geometry())
def test_the_line_of_sight_displacement_never_exceeds_the_displacement(case) -> None:
    radar_pos, pixel, u = case
    d = radar.project_los(u[None, :], radar_pos, pixel[None, :])[0]
    assert abs(d) <= np.linalg.norm(u) + 1e-12 * max(1.0, np.linalg.norm(u))


@pytest.mark.req("P-010-15")
@PROP
@given(_geometry(), st.floats(-10, 10))
def test_motion_along_the_line_of_sight_is_fully_seen_and_perpendicular_motion_gives_zero(case, s) -> None:
    radar_pos, pixel, _ = case
    e = (pixel - radar_pos) / np.linalg.norm(pixel - radar_pos)
    along = radar.project_los((s * e)[None, :], radar_pos, pixel[None, :])[0]
    assert along == pytest.approx(s, abs=1e-12 * max(1.0, abs(s)))
    helper = np.array([1.0, 0.0, 0.0]) if abs(e[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    perp = np.cross(e, helper)
    perp /= np.linalg.norm(perp)
    assert radar.project_los((s * perp)[None, :], radar_pos, pixel[None, :])[0] == pytest.approx(
        0.0, abs=1e-12 * max(1.0, abs(s))
    )


@pytest.mark.req("P-010-15")
@PROP
@given(st.floats(1.0, 100.0), st.integers(5, 200), st.floats(0.01, 0.24), st.integers(0, 2**32 - 1))
def test_unwrapping_the_wrapped_phase_returns_the_projection_when_every_increment_is_below_lambda_over_four(
    lam, n, frac, seed
) -> None:
    rng = np.random.default_rng(seed)
    steps = rng.uniform(-frac, frac, n) * lam  # |increment| < 0.24 lambda < lambda / 4
    d = np.cumsum(steps) - steps[0]  # d(t0) = 0
    phi = radar.wrapped_phase(d, lam)
    back = radar.unwrap_phase(phi, lam)
    assert back == pytest.approx(d, abs=1e-9 * lam)
