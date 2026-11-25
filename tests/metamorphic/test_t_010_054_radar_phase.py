"""T-010-054: S4b sign convention, phase law, keyed noise and temporal unwrapping.

Requirements: FR-010-41, P-010-16, P-010-17.
Spec: specs/010-slope/spec.md section 3.4 (FR-010-41), section 4 (P-010-16, P-010-17); plan.md row FR-010-41
(analytical phase
of a linear motion, `numpy.unwrap` as reference, noise statistics within the 99.9 % interval) and the radar tolerances
(phase 1e-9 rad, projection atol 1e-12 m).

Expected API: module `pitstudio.slope.radar` of T-010-050 plus `noise_series(run_seed, pixel_id, n_scans, sd_mm,
rho=None)
-> (n,)`: white Gaussian noise (rho None) or a stationary AR(1) series with lag-1 correlation rho and marginal sd
`sd_mm`
(e_k = rho e_k-1 + sqrt(1 - rho^2) w_k, e_0 = w_0), every standard normal w_k drawn by a counter-based generator (for
example
`numpy.random.Philox`) keyed by (run seed, pixel id, scan index): the value at scan k does not depend on the series
length or on
any other pixel. `build_radar_series` draws white noise of sd (d_end - d_0) / SNR with that generator, plus an AR(1)
term of
the same marginal sd when `ar1_rho` is given (atmospheric stratum), phase phi = wrap_(-pi, pi)[(4 pi / lambda) (d -
d_0 + n)],
measured series (lambda / 4 pi) numpy.unwrap(phi); `PixelSeries.phase`, `.measured_mm`, `.noise_mm`, `.d_mm` expose
the arrays.

Oracles: the definition of the sign convention (motion straight away from the radar is +s, toward it is -s); the
analytical phase
phi = 4 pi v t / lambda (wrapped) of a linear motion; the reference implementation `numpy.unwrap`; the 99.9 % normal
interval of a sample standard deviation (n = 20,000: +-3.3 / sqrt(2 n) = 1.65 %); metamorphic relations on random
geometry
(Hypothesis, 200 examples): linearity, rigid motion, lambda/2 periodicity, lambda-displacement co-scaling (lambda x k
stays in
the (1 mm, 1 m) guard of FR-010-42, so k is drawn from [0.3, 10] for lambda in [5, 50] mm: a spec-range clash noted in
the
report), pixel-set invariance.
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


def _wrap(x):
    return (np.asarray(x, dtype=float) + math.pi) % (2 * math.pi) - math.pi


def _circ(a, b):
    """Circular difference of two phase arrays, in (-pi, pi]."""
    return np.abs(_wrap(np.asarray(a) - np.asarray(b)))


def _radar(lam=17.4):
    return {"position_m": [0.0, -1500.0, 20.0], "wavelength_mm": lam, "scan_interval_min": 6.0}


# ---------------------------------------------------------------------------------------------------------------------
# sign convention and projection (P-010-16)


@st.composite
def _scene(draw):
    radar_pos = np.array([draw(st.floats(-1000, 1000)) for _ in range(3)])
    direction = np.array([draw(st.floats(-1, 1)) for _ in range(3)])
    assume(np.linalg.norm(direction) > 1e-2)
    direction /= np.linalg.norm(direction)
    pixel = radar_pos + draw(st.floats(50, 5000)) * direction
    u1 = np.array([draw(st.floats(-10, 10)) for _ in range(3)])
    u2 = np.array([draw(st.floats(-10, 10)) for _ in range(3)])
    return radar_pos, pixel, u1, u2


@pytest.mark.req("P-010-16")
@PROP
@given(_scene(), st.floats(-10, 10), st.floats(-10, 10))
def test_the_projection_is_linear_in_the_displacement(scene, a, b) -> None:
    r, p, u1, u2 = scene
    d = lambda u: radar.project_los(u[None, :], r, p[None, :])[0]  # noqa: E731
    assert d(a * u1 + b * u2) == pytest.approx(a * d(u1) + b * d(u2), abs=1e-12)


@pytest.mark.req("P-010-16")
@PROP
@given(_scene(), st.integers(0, 2**32 - 1), st.floats(-1e4, 1e4))
def test_a_rigid_motion_of_the_radar_and_the_wall_leaves_the_projection_unchanged(scene, seed, shift) -> None:
    r, p, u1, _ = scene
    q, _ = np.linalg.qr(np.random.default_rng(seed).standard_normal((3, 3)))  # a random orthogonal matrix
    t = np.array([shift, -0.5 * shift, 0.25 * shift])
    before = radar.project_los(u1[None, :], r, p[None, :])[0]
    after = radar.project_los((q @ u1)[None, :], q @ r + t, (q @ p + t)[None, :])[0]
    assert after == pytest.approx(before, abs=1e-12)


@pytest.mark.req("P-010-16")
@PROP
@given(_scene(), st.floats(0.0, 10.0))
def test_a_pixel_moving_straight_away_by_s_gives_plus_s_and_toward_gives_minus_s(scene, s) -> None:
    r, p, _, _ = scene
    e = (p - r) / np.linalg.norm(p - r)
    assert radar.project_los((s * e)[None, :], r, p[None, :])[0] == pytest.approx(s, abs=1e-12)
    assert radar.project_los((-s * e)[None, :], r, p[None, :])[0] == pytest.approx(-s, abs=1e-12)


@pytest.mark.req("FR-010-41")
def test_the_record_states_the_sign_convention_and_keeps_d_the_measurement_and_the_wrap_flags() -> None:
    n = 20
    u = np.column_stack([np.zeros(n), 0.02 * np.arange(n), np.zeros(n)])  # +y: away from a radar at y = -1500
    pix = {"pixel_id": 3, "position_m": [0.0, 0.0, 20.0], "displacement_mm": u}
    s = radar.build_radar_series(
        event_id="voight-test-snr-obs-000003",
        t_h=0.1 * np.arange(n),
        radar=_radar(),
        pixels=[pix],
        snr=None,
        run_seed=2,
    )[3]
    rec = s.record
    assert rec["sign_convention"] == "positive = away from the radar"
    assert rec["los_displacement_mm"] == pytest.approx(u[:, 1].tolist())  # positive: moving away
    assert {"los_displacement_mm", "measured_los_displacement_mm", "wrap_flags"} <= set(rec)
    assert len(rec["wrap_flags"]) == len(rec["measured_los_displacement_mm"]) == n
    assert lem_ref.schema_errors(rec, "displacement-series") == []
    toward = {**pix, "displacement_mm": -u}
    s2 = radar.build_radar_series(
        event_id="voight-test-snr-obs-000003",
        t_h=0.1 * np.arange(n),
        radar=_radar(),
        pixels=[toward],
        snr=None,
        run_seed=2,
    )[3]
    assert s2.d_mm == pytest.approx(-u[:, 1])  # toward the radar: negative


# ---------------------------------------------------------------------------------------------------------------------
# phase law and temporal unwrapping (FR-010-41)


@pytest.mark.req("FR-010-41")
@pytest.mark.parametrize("lam", [5.0, 17.4, 50.0])
def test_the_phase_of_a_linear_motion_is_four_pi_v_t_over_lambda_wrapped(lam) -> None:
    n, v = 200, 0.015 * lam  # 0.015 lambda per scan, far below the lambda / 4 limit; the total reaches 3 lambda (wraps)
    t = np.arange(n) * 0.1  # h
    steps = np.arange(n) * v
    u = np.column_stack([np.zeros(n), steps, np.zeros(n)])
    pix = {"pixel_id": 1, "position_m": [0.0, 0.0, 20.0], "displacement_mm": u}
    s = radar.build_radar_series(
        event_id="voight-test-snr-obs-000004", t_h=t, radar=_radar(lam), pixels=[pix], snr=None, run_seed=1
    )[1]
    expected = _wrap(4 * math.pi * steps / lam)  # phi = (4 pi / lambda) d, d(t0) = 0
    assert _circ(s.phase, expected).max() <= 1e-9
    assert s.measured_mm == pytest.approx(steps, abs=1e-9 * lam)  # unwrapped back to the displacement
    assert not any(s.record["wrap_flags"])


@pytest.mark.req("FR-010-41")
def test_the_measured_series_is_numpy_unwrap_of_the_phase_scaled_by_lambda_over_four_pi() -> None:
    n, lam = 300, 17.4
    rng = np.random.default_rng(5)
    u = np.column_stack(
        [np.zeros(n), np.cumsum(rng.uniform(0.0, 0.9, n)), np.zeros(n)]
    )  # increments below lambda / 4 = 4.35
    pix = {"pixel_id": 9, "position_m": [0.0, 0.0, 20.0], "displacement_mm": u}
    s = radar.build_radar_series(
        event_id="voight-test-snr-obs-000005",
        t_h=0.1 * np.arange(n),
        radar=_radar(lam),
        pixels=[pix],
        snr=60.0,
        run_seed=11,
    )[9]
    assert s.measured_mm == pytest.approx(lam / (4 * math.pi) * np.unwrap(s.phase), rel=1e-12, abs=1e-12)
    assert s.record["measured_los_displacement_mm"] == pytest.approx(s.measured_mm.tolist(), rel=1e-12, abs=1e-12)
    # the phase is the wrapped (4 pi / lambda) (d - d_0 + noise), checked against the arrays the series exposes
    assert _circ(s.phase, 4 * math.pi / lam * (s.d_mm - s.d_mm[0] + s.noise_mm)).max() <= 1e-9
    assert np.all(np.abs(s.phase) <= math.pi + 1e-12)


@pytest.mark.req("FR-010-41")
def test_the_white_noise_has_the_declared_sd_and_the_snr_rule() -> None:
    n, lam = 20_000, 17.4
    u = np.column_stack(
        [np.zeros(n), np.linspace(0.0, 40.0, n), np.zeros(n)]
    )  # range 40 mm of LOS displacement, 1 mm per 500 scans
    pix = {"pixel_id": 4, "position_m": [0.0, 0.0, 20.0], "displacement_mm": u}
    s = radar.build_radar_series(
        event_id="voight-test-snr-obs-000006",
        t_h=0.1 * np.arange(n),
        radar=_radar(lam),
        pixels=[pix],
        snr=80.0,
        run_seed=21,
    )[4]
    sigma = 40.0 / 80.0  # sigma_d = range / SNR
    z = 3.3 / math.sqrt(2 * n)  # 99.9 % interval of a sample sd
    assert s.noise_mm.std(ddof=1) == pytest.approx(sigma, rel=z)
    assert abs(s.noise_mm.mean()) < 3.3 * sigma / math.sqrt(n)
    assert abs(np.corrcoef(s.noise_mm[1:], s.noise_mm[:-1])[0, 1]) < 3.3 / math.sqrt(n)  # white


@pytest.mark.req("FR-010-41")
def test_the_atmospheric_stratum_adds_an_ar1_term_of_the_same_marginal_sd() -> None:
    n, lam = 8_000, 17.4
    u = np.column_stack([np.zeros(n), np.linspace(0.0, 40.0, n), np.zeros(n)])
    pix = {"pixel_id": 4, "position_m": [0.0, 0.0, 20.0], "displacement_mm": u}
    kw = {
        "event_id": "voight-test-snr-obs-000007",
        "t_h": 0.1 * np.arange(n),
        "radar": _radar(lam),
        "pixels": [pix],
        "snr": 80.0,
        "run_seed": 21,
    }
    white = radar.build_radar_series(**kw)[4].noise_mm
    atmo = radar.build_radar_series(ar1_rho=0.9, stratum="snr_obs_atmospheric", **kw)[4].noise_mm
    sigma = 0.5
    assert white.std(ddof=1) == pytest.approx(sigma, rel=0.06)
    assert atmo.std(ddof=1) == pytest.approx(math.sqrt(2.0) * sigma, rel=0.2)  # white + AR(1), independent terms
    r = atmo - atmo.mean()
    assert float((r[1:] * r[:-1]).sum() / (r * r).sum()) == pytest.approx(0.45, abs=0.08)  # 0.9 x var(AR) / var(total)


@pytest.mark.req("FR-010-41")
def test_noise_series_is_keyed_by_run_seed_pixel_and_scan_not_by_the_series_length() -> None:
    a = radar.noise_series(7, 12, 50, 0.4)
    b = radar.noise_series(7, 12, 120, 0.4)
    assert np.array_equal(a, b[:50])  # counter-based: scan k does not depend on the length
    assert not np.array_equal(a, radar.noise_series(8, 12, 50, 0.4))  # another run seed
    assert not np.array_equal(a, radar.noise_series(7, 13, 50, 0.4))  # another pixel
    assert radar.noise_series(7, 12, 50, 0.8) == pytest.approx(2.0 * a, rel=1e-12)  # scales with sd
    ar = radar.noise_series(7, 12, 50, 0.4, rho=0.9)
    assert np.array_equal(ar, radar.noise_series(7, 12, 120, 0.4, rho=0.9)[:50])
    big = radar.noise_series(1, 5, 20_000, 0.7, rho=0.9)
    assert big.std(ddof=1) == pytest.approx(0.7, rel=0.12)  # the AR(1) series is correlated: its effective n is ~100
    assert float((big[1:] * big[:-1]).sum() / (big * big).sum()) == pytest.approx(0.9, abs=0.03)


# ---------------------------------------------------------------------------------------------------------------------
# P-010-17


@st.composite
def _phase_case(draw):
    lam = draw(st.floats(5.0, 50.0))
    n = draw(st.integers(2, 2000))
    seed = draw(st.integers(0, 2**32 - 1))
    d = np.cumsum(np.random.default_rng(seed).uniform(-0.3, 0.3, n) * lam)
    return lam, d - d[0]


@pytest.mark.req("P-010-17")
@PROP
@given(_phase_case())
def test_adding_half_a_wavelength_to_the_displacement_leaves_the_phase_unchanged(case) -> None:
    lam, d = case
    assert _circ(radar.wrapped_phase(d + lam / 2.0, lam), radar.wrapped_phase(d, lam)).max() <= 1e-9
    assert _circ(radar.wrapped_phase(d + 3.0 * lam, lam), radar.wrapped_phase(d, lam)).max() <= 1e-9


def _pixels(n_pix, n_scans, seed):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_pix):
        pos = [float(rng.uniform(-60, 60)), float(rng.uniform(-30, 30)), float(rng.uniform(0, 40))]
        u = np.cumsum(rng.uniform(0.0, 0.8, (n_scans, 3)), axis=0)
        out.append({"pixel_id": 1000 + i, "position_m": pos, "displacement_mm": u})
    return out


@pytest.mark.req("P-010-17")
@PROP
@given(st.floats(5.0, 50.0), st.floats(0.3, 10.0), st.integers(2, 40), st.integers(0, 2**32 - 1))
def test_scaling_the_wavelength_and_the_displacement_by_the_same_factor_leaves_the_phase_unchanged(
    lam, k, n_scans, seed
) -> None:
    pixels = _pixels(2, n_scans, seed)
    scaled = [{**p, "displacement_mm": k * p["displacement_mm"]} for p in pixels]
    kw = {
        "event_id": "voight-test-snr-obs-000008",
        "t_h": 0.1 * np.arange(n_scans),
        "snr": 50.0,
        "run_seed": seed % 997,
    }
    a = radar.build_radar_series(radar=_radar(lam), pixels=pixels, **kw)
    b = radar.build_radar_series(radar=_radar(lam * k), pixels=scaled, **kw)  # SNR fixed: the noise scales with k too
    for pid in a:
        assert _circ(a[pid].phase, b[pid].phase).max() <= 1e-9


@pytest.mark.req("P-010-17")
@PROP
@given(st.integers(1, 12), st.integers(2, 30), st.integers(0, 2**32 - 1))
def test_a_pixels_noise_and_phase_do_not_change_when_other_pixels_are_added_removed_or_reordered(
    n_pix, n_scans, seed
) -> None:
    pixels = _pixels(n_pix, n_scans, seed)
    kw = {
        "event_id": "voight-test-snr-obs-000009",
        "t_h": 0.1 * np.arange(n_scans),
        "radar": _radar(),
        "snr": 50.0,
        "run_seed": 5,
    }
    full = radar.build_radar_series(pixels=pixels, **kw)
    order = np.random.default_rng(seed).permutation(n_pix)
    shuffled = radar.build_radar_series(pixels=[pixels[i] for i in order], **kw)
    extra = radar.build_radar_series(pixels=[*pixels, {**pixels[0], "pixel_id": 99_999}], **kw)
    for p in pixels:
        pid = p["pixel_id"]
        alone = radar.build_radar_series(pixels=[p], **kw)[pid]
        for other in (full[pid], shuffled[pid], extra[pid]):
            assert np.array_equal(other.noise_mm, alone.noise_mm)
            assert np.array_equal(other.phase, alone.phase)
    assert not np.array_equal(
        extra[99_999].noise_mm, extra[pixels[0]["pixel_id"]].noise_mm
    )  # distinct pixel id, distinct stream
