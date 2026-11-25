"""T-012-061: image PSD of instance masks, quantiles, oversize share and the Swebrec fit (unit, metamorphic, hostile).

Requirements: FR-012-24, FR-012-25, FR-012-26, FR-012-27, P-012-01, P-012-02, P-012-03, P-012-04, P-012-05
(the part of T-012-030 that the D1 per-fold PSD curves of d-cases-2026-11-23 need; the watershed baseline, the x50
comparisons and the synthetic arm stay with T-012-030 to T-012-033).

Oracles:
- hand calculation: instances of area pi, 4 pi, 9 pi pixels have equivalent diameters 2, 4, 6 px, area weights 1/14, 4/14,
  9/14 and passing points (2, 1/14), (4, 5/14), (6, 1); the Q-1 median interpolates between (5/14, 4) and (1, 6) and is
  4 + 2 (1/2 - 5/14) / (1 - 5/14) = 40/9; the oversize share above 4 px is 9/14;
- exact Swebrec passing values generated with the closed form of the test (the minephys equation written out), which the
  fit must recover (P-012-05);
- symmetry, permutation, replication and unit-scaling properties of the spec (P-012-01 to P-012-04), checked on random
  label images and on exact-Swebrec points;
- hostile fit inputs of FR-012-27 and the `no-fit` status of FR-012-25.

Expected API (module `pitstudio_pipeline.fragmentation.psd`): instance_areas, image_psd, weighted_quantile, oversize_share,
fit_swebrec, fit_instances; see the module docstring (sizes in pixels, area-weighted).
"""
# ruff: noqa: E501, PT018

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.fragmentation import psd as P


def _swebrec(x, x50, xmax, b):
    x = np.asarray(x, dtype=float)
    return np.where(x < xmax, 1.0 / (1.0 + (np.log(xmax / x) / np.log(xmax / x50)) ** b), 1.0)


# ----------------------------------------------------------------------------------------------------------------------
# FR-012-24
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-012-24")
def test_the_passing_points_and_quantiles_equal_the_hand_calculation() -> None:
    psd = P.image_psd([math.pi, 4 * math.pi, 9 * math.pi])
    assert psd.sizes == pytest.approx([2.0, 4.0, 6.0], rel=1e-12)
    assert psd.passing == pytest.approx([1 / 14, 5 / 14, 1.0], rel=1e-12)
    assert psd.n_instances == 3
    assert psd.total_area_px == pytest.approx(14 * math.pi)
    assert P.weighted_quantile(psd, 0.5) == pytest.approx(40 / 9, rel=1e-12)
    assert P.weighted_quantile(psd, 0.05) == 2.0  # x_1 if F_1 >= q
    assert P.oversize_share(psd, 4.0) == pytest.approx(9 / 14, rel=1e-12)
    assert P.oversize_share(psd, 6.0) == 0.0
    assert P.oversize_share(psd, 1.0) == 1.0


@pytest.mark.req("FR-012-24")
def test_equal_sizes_are_merged_into_one_point() -> None:
    psd = P.image_psd([math.pi, math.pi, 4 * math.pi])
    assert psd.sizes == pytest.approx([2.0, 4.0], rel=1e-12)
    assert psd.passing == pytest.approx([1 / 3, 1.0], rel=1e-12)  # (pi + pi) / 6 pi


@pytest.mark.req("FR-012-24")
def test_instance_areas_count_pixels_per_id_and_drop_the_background_and_empty_ids() -> None:
    img = np.zeros((6, 6), dtype=np.uint8)
    img[0:2, 0:2] = 1  # 4 px
    img[3:6, 3:6] = 4  # 9 px, ids 2 and 3 are absent
    assert P.instance_areas(img).tolist() == [4.0, 9.0]


@pytest.mark.req("P-012-01")
@settings(max_examples=40, deadline=None)
@given(seed=st.integers(0, 10_000), k=st.integers(0, 7))
def test_the_psd_and_the_fit_are_the_same_for_the_eight_dihedral_maps(seed, k):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(5, 40))
    label = rng.integers(0, n + 1, size=(32, 32)).astype(np.int32)
    mapped = np.rot90(label, k % 4)
    if k >= 4:
        mapped = mapped.T
    a, b = P.instance_areas(label), P.instance_areas(mapped)
    assert np.array_equal(np.sort(a), np.sort(b))
    pa, fa = P.fit_instances(a)
    pb, fb = P.fit_instances(b)
    assert np.array_equal(pa.sizes, pb.sizes) and np.array_equal(pa.passing, pb.passing)
    assert fa == fb


@pytest.mark.req("P-012-03")
@settings(max_examples=40, deadline=None)
@given(areas=st.lists(st.floats(1.0, 5000.0), min_size=3, max_size=200), seed=st.integers(0, 1000))
def test_permuting_the_instance_list_leaves_the_psd_and_the_fit_unchanged(areas, seed):
    perm = np.random.default_rng(seed).permutation(len(areas))
    a, fa = P.fit_instances(areas)
    b, fb = P.fit_instances([areas[i] for i in perm])
    assert np.array_equal(a.sizes, b.sizes) and np.array_equal(a.passing, b.passing)
    assert fa.status == fb.status
    if fa.status == "ok":
        assert (fa.x50, fa.b) == pytest.approx((fb.x50, fb.b), rel=1e-9)


@pytest.mark.req("P-012-04")
@settings(max_examples=40, deadline=None)
@given(areas=st.lists(st.floats(1.0, 5000.0), min_size=3, max_size=100))
def test_duplicating_the_instance_set_leaves_the_passing_points_and_the_fit_unchanged(areas):
    a, fa = P.fit_instances(areas)
    b, fb = P.fit_instances(list(areas) * 2)
    assert np.array_equal(a.sizes, b.sizes)
    assert a.passing == pytest.approx(b.passing, rel=1e-12, abs=1e-15)
    assert fa.status == fb.status
    if fa.status == "ok":
        assert (fa.x50, fa.b) == pytest.approx((fb.x50, fb.b), rel=1e-6)


# ----------------------------------------------------------------------------------------------------------------------
# FR-012-26
# ----------------------------------------------------------------------------------------------------------------------

xmaxs = st.floats(5.0, 500.0)


@pytest.mark.req("P-012-05")
@settings(max_examples=60, deadline=None)
@given(xmax=xmaxs, ratio=st.floats(0.1, 0.8), b=st.floats(0.5, 10.0), n=st.integers(10, 40))
def test_the_fit_recovers_the_parameters_of_exact_swebrec_points(xmax, ratio, b, n):
    x50 = ratio * xmax
    sizes = xmax * np.geomspace(0.02, 1.0, n)
    fit = P.fit_swebrec(sizes, _swebrec(sizes, x50, xmax, b))
    assert fit.status == "ok"
    assert fit.x_max == xmax
    assert fit.x50 == pytest.approx(x50, rel=1e-6)
    assert fit.b == pytest.approx(b, rel=1e-6)
    assert fit.rmse < 1e-9


@pytest.mark.req("P-012-02")
@settings(max_examples=40, deadline=None)
@given(k=st.floats(1e-3, 1e3), ratio=st.floats(0.2, 0.7), b=st.floats(1.0, 6.0))
def test_scaling_every_size_scales_x50_and_xmax_and_leaves_b_unchanged(k, ratio, b):
    sizes = np.geomspace(0.02, 1.0, 20)
    passing = _swebrec(sizes, ratio, 1.0, b)
    base = P.fit_swebrec(sizes, passing)
    scaled = P.fit_swebrec(sizes * k, passing)
    assert scaled.x50 == pytest.approx(k * base.x50, rel=1e-6)
    assert scaled.x_max == pytest.approx(k * base.x_max, rel=1e-12)
    assert scaled.b == pytest.approx(base.b, rel=1e-6)


# ----------------------------------------------------------------------------------------------------------------------
# FR-012-25, FR-012-27: hostile inputs
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-012-25")
@pytest.mark.parametrize(
    "areas", [[10.0, 20.0], [10.0], [10.0, 20.0, float("nan")], [10.0, 0.0, 30.0], [10.0, -1.0, 30.0]]
)
def test_fewer_than_three_instances_or_a_bad_area_give_no_fit(areas) -> None:
    _, fit = P.fit_instances(areas)
    assert fit.status == "no-fit"
    assert fit.x50 is None and fit.b is None


@pytest.mark.req("FR-012-25")
def test_three_equal_instances_have_one_size_and_give_no_fit() -> None:
    _, fit = P.fit_instances([50.0, 50.0, 50.0])
    assert fit.status == "no-fit"


@pytest.mark.req("FR-012-27")
@pytest.mark.parametrize(
    ("sizes", "passing", "name"),
    [
        ([0.0, 1.0, 2.0], [0.1, 0.5, 1.0], "sizes"),
        ([1.0, float("nan"), 2.0], [0.1, 0.5, 1.0], "sizes"),
        ([1.0, 1.0, 2.0], [0.1, 0.5, 1.0], "sizes"),
        ([3.0, 2.0, 1.0], [0.1, 0.5, 1.0], "sizes"),
        ([1.0, 2.0, 3.0], [0.1, 1.5, 1.0], "passing"),
        ([1.0, 2.0, 3.0], [0.6, 0.5, 1.0], "passing"),
        ([1.0, 2.0], [0.5, 1.0], "sizes"),
        ([1.0, 2.0, 3.0], [0.5, 1.0], "sizes"),
    ],
)
def test_hostile_fit_inputs_raise_value_error_naming_the_argument(sizes, passing, name) -> None:
    with pytest.raises(ValueError, match=name):
        P.fit_swebrec(sizes, passing)


@pytest.mark.req("FR-012-24")
@pytest.mark.parametrize("areas", [[], [1.0, float("inf")], [1.0, 0.0], [[1.0, 2.0]]])
def test_hostile_areas_raise_value_error(areas) -> None:
    with pytest.raises(ValueError, match="areas"):
        P.image_psd(areas)
