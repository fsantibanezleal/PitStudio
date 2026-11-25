"""T-011-030 - FR-011-18, P-011-08: smooth and hard heap repose observables of the DEM calibration.

Oracles (independent of the code under test):
- the soft-max envelope formula of spec section 7 evaluated by hand on tiny cases:
      h_b = (1 / beta) ln sum_i w_ib exp(beta z_i^top),  beta = 10 / d,  w_ib = exp(-(r_i - r_b)^2 / (2 (dr / 2)^2)),
      dr = 2 d, z^top = z + d / 2.
  One bin, two particles on the bin centre (w = 1) at top heights 1 and 2 (d = 0.1, beta = 100): h = 2 + ln(1 +
      e^-100)/100 = 2
  to 1e-40; one particle at r_b + dr / 2 (w = exp(-1/2)) alone: h = z^top + ln(exp(-1/2)) / beta = z^top - 0.5 / beta;
- a reference least-squares fit written in this file (numpy.polyfit over the frozen bins) for theta_s = arctan(-slope);
- analytic conical heaps (P-011-08): theta in [20, 45] deg, surface points on the cone z = H - r tan(theta), H = 20
    d, with a
  dense surface sampling and a filler below; smooth and hard observables must agree within 0.5 deg;
- the relations of plan 011: translation of the axis, rotation about the axis, permutation, scaling of every length
  (beta = 10 / d and the bins scale with d), and linearity of the smooth observable in a small perturbation (the bin
  range being frozen, theta_s is a smooth function of the particle positions: halving the perturbation halves the
      change).

Expected public API (module `pitstudio.calibration.observables`, under `src/pitstudio/calibration/`):

    smooth_envelope(positions, *, d, axis_xy, bin_centres) -> np.ndarray [n_bins]
        positions [N, 3] (x, y, z up), radial distance r_i from `axis_xy`, the soft-max envelope above.
    hard_envelope(positions, *, d, axis_xy, bin_centres) -> np.ndarray [n_bins]
        maximum top height per radial bin of width 2 d centred on `bin_centres`; nan for an empty bin.
    freeze_bin_range(positions, *, d, axis_xy) -> tuple[int, int]
        (first_bin, last_bin), inclusive, of the radial bins (index b: r in [2 d b, 2 d (b + 1))) whose hard
        envelope height lies between 20 % and 80 % of the heap height (maximum top height); called once at the start
        of the recorded window.
    smooth_repose_deg(positions, *, d, axis_xy, bin_range) -> float
        arctan of minus the least-squares slope of the smooth envelope h_b against the bin centres r_b = 2 d (b + 1/2)
        over the frozen bins, in degrees.
    hard_repose_deg(positions, *, d, axis_xy, bin_range=None) -> float
        the same with the hard envelope; bin_range None freezes the range from the positions themselves.
    Hostile input (empty or non-[N, 3] positions, non-finite value, d <= 0 or non-finite, a bin range with fewer than 2
    bins or reversed) raises ValueError.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.calibration import observables as hobs  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
HEAVY = min(EXAMPLES, 100)  # every example builds and fits a three-dimensional heap of ~2 x 10^3 points


def cone(theta_deg: float, d: float, height_over_d: float = 70.0, axis=(0.0, 0.0)) -> np.ndarray:
    """Surface points on z_top = H - r tan(theta) (centres d / 2 lower), one ring every d / 4 along the slope.

    Every ring holds the same number (8) of points, so the number of near-top points per radial bin does not grow with
    r. This is the regime of the spec's tolerance argument (plan 011, "Smooth vs hard 0.5 deg": a near-uniform
    ln(n_b) / beta offset that the slope fit removes). With a physical packing density n_b grows like r and the
    offset ln(n_b) / beta then adds a slope of about d / (10 r). Heaps are also tall (H = 70 d): the
        Gaussian-weighted soft
    maximum of a linear flank peaks at r_b - 10 d tan(theta) (hand calculation: the exponent beta z(r') - (r' - r_b)^2 /
    (2 d^2) is stationary there), so bins closer to the axis than 10 d tan(theta) see the truncated apex and are biased
    by up to ~0.6 deg at H = 20 d (reported as an ambiguity of P-011-08, not asserted here).
    """
    th = math.radians(theta_deg)
    h = height_over_d * d
    slant = h / math.sin(th)
    pts = []
    for k in range(int(slant / (d / 4)) + 1):
        s = (k + 0.37) * (d / 4)
        r = s * math.cos(th)
        z_top = h - s * math.sin(th)
        if z_top < d:
            break
        phi = 2 * math.pi * (np.arange(8) + 0.21 * k) / 8
        pts.append(np.column_stack([axis[0] + r * np.cos(phi), axis[1] + r * np.sin(phi), np.full(8, z_top - d / 2)]))
    return np.vstack(pts)


def reference_smooth(pos: np.ndarray, d: float, axis, centres: np.ndarray) -> np.ndarray:
    beta = 10.0 / d
    dr = 2.0 * d
    r = np.hypot(pos[:, 0] - axis[0], pos[:, 1] - axis[1])
    ztop = pos[:, 2] + d / 2
    out = []
    for rb in centres:
        w = np.exp(-((r - rb) ** 2) / (2.0 * (dr / 2.0) ** 2))
        out.append(np.log(np.sum(w * np.exp(beta * (ztop - ztop.max())))) / beta + ztop.max())
    return np.array(out)


def centres_for(rng_bins: tuple[int, int], d: float) -> np.ndarray:
    return 2.0 * d * (np.arange(rng_bins[0], rng_bins[1] + 1) + 0.5)


def reference_theta(h: np.ndarray, centres: np.ndarray) -> float:
    return math.degrees(math.atan(-np.polyfit(centres, h, 1)[0]))


# ------------------------------------------------------------------ FR-011-18 envelope formula by hand


@pytest.mark.req("FR-011-18")
def test_two_particles_on_the_bin_centre_give_the_soft_maximum_by_hand() -> None:
    d = 0.1
    pos = np.array([[0.4, 0.0, 1.0 - d / 2], [0.4, 0.0, 2.0 - d / 2]])  # r = 0.4 = r_b, top heights 1 and 2
    h = hobs.smooth_envelope(pos, d=d, axis_xy=(0.0, 0.0), bin_centres=np.array([0.4]))
    beta = 10.0 / d
    expected = 2.0 + math.log(1.0 + math.exp(-beta * 1.0)) / beta  # ln(e^{beta} + e^{2 beta}) / beta
    assert h[0] == pytest.approx(expected, abs=1e-12)


@pytest.mark.req("FR-011-18")
def test_one_particle_half_a_bin_width_off_centre_is_down_weighted_by_exp_minus_half() -> None:
    d = 0.1
    dr = 2 * d
    pos = np.array([[0.4 + dr / 2, 0.0, 1.0 - d / 2]])  # w = exp(-(dr/2)^2 / (2 (dr/2)^2)) = exp(-1/2)
    h = hobs.smooth_envelope(pos, d=d, axis_xy=(0.0, 0.0), bin_centres=np.array([0.4]))
    assert h[0] == pytest.approx(1.0 - 0.5 / (10.0 / d), abs=1e-12)


@pytest.mark.req("FR-011-18")
def test_hard_envelope_is_the_maximum_top_height_per_bin_and_nan_for_an_empty_bin() -> None:
    d = 0.1
    # bins of width 0.2 centred 0.1, 0.3, 0.5: particles at r = 0.05, 0.15 (bin 0) and 0.45 (bin 2)
    pos = np.array([[0.05, 0, 0.30], [0.15, 0, 0.55], [0.45, 0, 0.20]])
    h = hobs.hard_envelope(pos, d=d, axis_xy=(0.0, 0.0), bin_centres=np.array([0.1, 0.3, 0.5]))
    assert h[0] == pytest.approx(0.55 + d / 2, abs=1e-12)
    assert math.isnan(h[1])
    assert h[2] == pytest.approx(0.20 + d / 2, abs=1e-12)


@pytest.mark.req("FR-011-18")
@settings(max_examples=HEAVY, deadline=None)
@given(theta=st.floats(20.0, 45.0), d=st.floats(2e-3, 8e-3))
def test_smooth_repose_equals_the_reference_fit_over_the_frozen_bins(theta: float, d: float) -> None:
    pos = cone(theta, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    got = hobs.smooth_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    c = centres_for(rng_bins, d)
    expected = reference_theta(reference_smooth(pos, d, (0.0, 0.0), c), c)
    assert got == pytest.approx(expected, rel=1e-9, abs=1e-9)


@pytest.mark.req("FR-011-18")
def test_frozen_range_selects_the_bins_between_twenty_and_eighty_percent_of_the_heap_height() -> None:
    d = 0.004
    theta = 30.0
    pos = cone(theta, d, 20.0)
    first, last = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    # z_top = H - r tan(theta) between 0.2 H and 0.8 H  <=>  r in [0.2 H / t, 0.8 H / t] = [6.93 d, 27.7 d];
    # bin centres 2 d (b + 1/2): b from 2.97 to 13.35 (hand calculation); one bin of slack at each end.
    assert 2 <= first <= 4
    assert 12 <= last <= 14


@pytest.mark.req("FR-011-18")
def test_the_frozen_range_is_kept_when_a_particle_later_crosses_a_height_threshold() -> None:
    d = 0.004
    pos = cone(30.0, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    moved = pos.copy()
    moved[np.argmax(pos[:, 2]), 2] += 6.0 * d  # lifts the apex above the old height: a re-derived range would shift
    got = hobs.smooth_repose_deg(moved, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    c = centres_for(rng_bins, d)
    assert got == pytest.approx(reference_theta(reference_smooth(moved, d, (0.0, 0.0), c), c), rel=1e-9, abs=1e-9)


# ------------------------------------------------------------------ P-011-08 agreement and metamorphic relations


@pytest.mark.req("P-011-08")
@settings(max_examples=HEAVY, deadline=None)
@given(theta=st.floats(20.0, 45.0), d=st.floats(2e-3, 8e-3))
def test_smooth_and_hard_observables_agree_within_half_a_degree_on_conical_heaps(theta: float, d: float) -> None:
    pos = cone(theta, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    smooth = hobs.smooth_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    hard = hobs.hard_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    assert abs(smooth - hard) <= 0.5
    assert abs(smooth - theta) <= 1.0  # and both stay near the analytic slope (coarse sanity bound, not the spec's)


@pytest.mark.req("P-011-08")
@pytest.mark.parametrize("theta", [20.0, 30.0, 45.0])
def test_hard_repose_without_a_range_freezes_it_from_the_positions(theta: float) -> None:
    d = 0.004
    pos = cone(theta, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    assert hobs.hard_repose_deg(pos, d=d, axis_xy=(0.0, 0.0)) == pytest.approx(
        hobs.hard_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins), abs=1e-12
    )


@pytest.mark.req("FR-011-18")
@settings(max_examples=HEAVY, deadline=None)
@given(
    theta=st.floats(20.0, 45.0),
    shift=st.tuples(st.floats(-5.0, 5.0), st.floats(-5.0, 5.0)),
    rot=st.floats(0.0, 2 * math.pi),
    seed=st.integers(0, 2**32 - 1),
)
def test_metamorphic_translation_rotation_about_the_axis_and_permutation_leave_theta_unchanged(
    theta: float, shift: tuple[float, float], rot: float, seed: int
) -> None:
    d = 0.004
    pos = cone(theta, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    base = hobs.smooth_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    moved = pos + np.array([shift[0], shift[1], 0.0])
    assert hobs.smooth_repose_deg(moved, d=d, axis_xy=shift, bin_range=rng_bins) == pytest.approx(base, abs=1e-8)
    c, s = math.cos(rot), math.sin(rot)
    rotated = np.column_stack([c * pos[:, 0] - s * pos[:, 1], s * pos[:, 0] + c * pos[:, 1], pos[:, 2]])
    assert hobs.smooth_repose_deg(rotated, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins) == pytest.approx(base, abs=1e-8)
    perm = np.random.default_rng(seed).permutation(len(pos))
    assert hobs.smooth_repose_deg(pos[perm], d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins) == pytest.approx(
        base, abs=1e-8
    )


@pytest.mark.req("FR-011-18")
@settings(max_examples=HEAVY, deadline=None)
@given(theta=st.floats(20.0, 45.0), k=st.floats(0.1, 10.0))
def test_metamorphic_scaling_every_length_by_k_leaves_theta_unchanged(theta: float, k: float) -> None:
    d = 0.004
    pos = cone(theta, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    base = hobs.smooth_repose_deg(pos, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    scaled = hobs.smooth_repose_deg(pos * k, d=d * k, axis_xy=(0.0, 0.0), bin_range=rng_bins)
    assert scaled == pytest.approx(base, rel=1e-8, abs=1e-8)


@pytest.mark.req("FR-011-18")
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_metamorphic_smooth_observable_changes_linearly_with_a_small_perturbation(seed: int) -> None:
    d = 0.004
    pos = cone(30.0, d)
    rng_bins = hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
    u = np.random.default_rng(seed).normal(size=pos.shape)
    u /= np.abs(u).max()

    def theta_at(eps: float) -> float:
        return hobs.smooth_repose_deg(pos + eps * d * u, d=d, axis_xy=(0.0, 0.0), bin_range=rng_bins)

    t0 = theta_at(0.0)
    d1 = theta_at(1e-3) - t0
    d2 = theta_at(5e-4) - t0
    assert d1 != 0.0
    assert d2 / d1 == pytest.approx(0.5, abs=0.02)  # first-order (smooth) behaviour; a hard maximum would jump


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-18")
@pytest.mark.parametrize(
    "positions",
    [np.zeros((0, 3)), np.zeros((5, 2)), np.array([[0.0, 0.0, np.nan], [1.0, 0.0, 1.0]])],
    ids=["empty", "two-columns", "nan"],
)
def test_hostile_positions_are_rejected(positions: np.ndarray) -> None:
    with pytest.raises(ValueError, match=r"."):
        hobs.hard_repose_deg(positions, d=0.004, axis_xy=(0.0, 0.0), bin_range=(2, 8))
    with pytest.raises(ValueError, match=r"."):
        hobs.smooth_repose_deg(positions, d=0.004, axis_xy=(0.0, 0.0), bin_range=(2, 8))


@pytest.mark.req("FR-011-18")
@pytest.mark.parametrize("bad_range", [(5, 5), (8, 2), (-1, 4)])
def test_a_bin_range_with_fewer_than_two_bins_or_reversed_is_rejected(bad_range: tuple[int, int]) -> None:
    pos = cone(30.0, 0.004)
    with pytest.raises(ValueError, match=r"."):
        hobs.smooth_repose_deg(pos, d=0.004, axis_xy=(0.0, 0.0), bin_range=bad_range)


@pytest.mark.req("FR-011-18")
@pytest.mark.parametrize("d", [0.0, -0.004, float("nan"), float("inf")])
def test_hostile_particle_diameter_is_rejected(d: float) -> None:
    pos = cone(30.0, 0.004)
    with pytest.raises(ValueError, match=r"."):
        hobs.freeze_bin_range(pos, d=d, axis_xy=(0.0, 0.0))
