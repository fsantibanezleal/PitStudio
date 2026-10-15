# ruff: noqa: E501
"""T-009-040 (metamorphic half) - P-009-01, P-009-02, P-009-03: invariants of the dust haze on linear images.

Oracles (independent of the code under test): the invariants of spec 009 section 4, each derived here from the haze law
out = t I + (1 - t) A, t = exp(-sigma d / 1000):
- P-009-01 semigroup: applying the haze over d1 and then d2 multiplies the transmittances, t1 t2 = exp(-sigma (d1 + d2) / 1000) = t(d1 + d2), and
  t2 (t1 I + (1 - t1) A) + (1 - t2) A = t1 t2 I + (1 - t1 t2) A: so dust(dust(I, d1), d2) = dust(I, d1 + d2) (atol 1e-12, float64 images, d in
  [0, 2000] m, severity 1..5);
- P-009-02 monotonicity: out - A = t (I - A), so |out - A| = t |I - A| and t = exp(-sigma d / 1000) falls with sigma: a higher severity never moves a
  pixel away from the airlight, and t lies in (0, 1] (spec says "exact (float64 comparison)"; a 1e-12 slack absorbs the last-ulp noise of subtracting A
  twice, reported as an ambiguity);
- P-009-03 equivariance: the haze is elementwise (no neighbourhood), so permuting or dihedrally transforming image and depth before the haze
  equals transforming after it (exact equality).

Expected public API: `pitstudio_pipeline.perception.corruptions.{dust_linear, transmittance, AIRLIGHT}` as in tests/unit/test_t_009_040_dust.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline" / "src"))  # pipeline lane package (uv `package = false`)

from pitstudio_pipeline.perception import corruptions as cor  # noqa: E402

EXAMPLES = 200
A = np.array([0.58, 0.46, 0.31])

shape = {"seed": st.integers(0, 2**32 - 1), "h": st.integers(1, 64), "w": st.integers(1, 64)}


def _img(seed: int, h: int, w: int) -> np.ndarray:
    return np.random.default_rng(seed).random((h, w, 3))


def _depth(seed: int, h: int, w: int, hi: float = 2000.0) -> np.ndarray:
    return np.random.default_rng(seed + 1).random((h, w)) * hi


@pytest.mark.req("P-009-01")
@given(**shape, severity=st.integers(1, 5), d2_seed=st.integers(0, 2**32 - 1))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_hazing_over_d1_then_d2_equals_hazing_over_d1_plus_d2(
    seed: int, h: int, w: int, severity: int, d2_seed: int
) -> None:
    lin = _img(seed, h, w)
    d1, d2 = _depth(seed, h, w, 1000.0), _depth(d2_seed, h, w, 1000.0)
    once = cor.dust_linear(lin, d1 + d2, severity)
    twice = cor.dust_linear(cor.dust_linear(lin, d1, severity), d2, severity)
    np.testing.assert_allclose(twice, once, rtol=0.0, atol=1e-12)


@pytest.mark.req("P-009-02")
@given(**shape, s1=st.integers(1, 4), gap=st.integers(1, 4))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_a_higher_severity_never_moves_a_pixel_away_from_the_airlight(
    seed: int, h: int, w: int, s1: int, gap: int
) -> None:
    s2 = min(5, s1 + gap)
    lin, depth = _img(seed, h, w), _depth(seed, h, w)
    d1 = np.abs(cor.dust_linear(lin, depth, s1) - A)
    d2 = np.abs(cor.dust_linear(lin, depth, s2) - A)
    assert (d2 <= d1 + 1e-12).all()


@pytest.mark.req("P-009-02")
@given(**shape, severity=st.integers(1, 5))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_the_transmittance_lies_in_the_half_open_unit_interval_and_falls_with_depth(
    seed: int, h: int, w: int, severity: int
) -> None:
    depth = _depth(seed, h, w)
    t = cor.transmittance(depth, severity)
    assert ((t > 0.0) & (t <= 1.0)).all()
    order = np.argsort(depth, axis=None)
    flat_t = t.reshape(-1)[order]
    assert (np.diff(flat_t) <= 0.0).all()  # deeper pixels never transmit more
    zero = cor.transmittance(np.zeros((1, 1)), severity)
    assert zero[0, 0] == 1.0


@pytest.mark.req("P-009-03")
@given(**shape, severity=st.integers(1, 5), perm_seed=st.integers(0, 2**32 - 1))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_a_pixel_permutation_commutes_with_the_haze(
    seed: int, h: int, w: int, severity: int, perm_seed: int
) -> None:
    lin, depth = _img(seed, h, w), _depth(seed, h, w)
    perm = np.random.default_rng(perm_seed).permutation(h * w)
    lin_p = lin.reshape(h * w, 3)[perm].reshape(h, w, 3)
    depth_p = depth.reshape(h * w)[perm].reshape(h, w)
    after = cor.dust_linear(lin, depth, severity).reshape(h * w, 3)[perm].reshape(h, w, 3)
    np.testing.assert_array_equal(cor.dust_linear(lin_p, depth_p, severity), after)


def _dihedral(k: int, a: np.ndarray) -> np.ndarray:
    """The 8 maps of the square's symmetry group on the two image axes (rotations by 90 degrees, with and without a flip)."""
    b = np.rot90(a, k % 4, axes=(0, 1))
    return b[:, ::-1] if k >= 4 else b


@pytest.mark.req("P-009-03")
@given(**shape, severity=st.integers(1, 5), k=st.integers(0, 7))
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_each_of_the_eight_dihedral_maps_commutes_with_the_haze(
    seed: int, h: int, w: int, severity: int, k: int
) -> None:
    lin, depth = _img(seed, h, w), _depth(seed, h, w)
    left = cor.dust_linear(_dihedral(k, lin), _dihedral(k, depth), severity)
    right = _dihedral(k, cor.dust_linear(lin, depth, severity))
    np.testing.assert_array_equal(left, right)
