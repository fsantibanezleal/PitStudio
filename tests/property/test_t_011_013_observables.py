"""T-011-013 - FR-011-05, P-011-06, P-011-07: repose-angle and run-out observables of the GNS evaluation.

Oracles (independent of the code under test):
- analytic piles (plan 011 test strategy FR-011-05, P-011-06): particle centres laid on a flank of exact slope theta,
  one surface point every d / 8 along the slope (a dense sampling of the free surface: only the highest points of
  each bin matter to the extractor), their centres d / 2 below the analytic free surface, so the free surface
  seen by the extractor is the analytic line y = H - x tan(theta) (H = pile height >= 30 d). The extractor must return
  theta within 0.4 deg (spec P-011-06; the spec states <= 0.35 deg measured for piles >= 30 d high);
- hand-computed percentiles (spec section 7): 1,000 particles whose top 20 (and, for the pile family, bottom 20) share
  one x, so that the 99th (1st) percentile is that x under every percentile definition: x99 = 1.7 gives
  L = x99 - L0 = 1.7 - 0.2 = 1.5 (collapse), x99 = 1.2, x1 = -0.8, x_p = 0.1 gives L = mean(1.2 - 0.1, 0.1 + 0.8) = 1.0
  (pile), x99 = 1.2, x_c = 0.3 gives L = 0.9 (dump);
- the metamorphic relations of P-011-06 and P-011-07 (permutation, translation, mirroring, length scaling, outward
  moves never decrease L).

Conventions fixed by spec section 7 and used here: the free surface is the maximum particle top height (y + d / 2) per
bin of width 2 d measured from the family's reference abscissa (wall x = 0 for the column collapse, the pour point
x_p for the pile, the crest x_c for the dump), over the bins whose surface height lies between 20 % and 80 % of the
pile height; the dump flank is the one on the side x > x_c.

Expected public API (module `pitstudio.granular.observables`, under `src/pitstudio/granular/`):

    repose_angle_deg(positions, *, d, family, geometry) -> float
        positions: float array [N, 2] (x, y of the particle centres at the rest time), metres;
        d: particle diameter (m); family in {"column-collapse", "pile-formation", "dump-over-crest"};
        geometry: the recorded geometry parameters of the rollout (DC-011-01 `geometry`): "column_width_m" for the
        collapse, "pour_point_x_m" for the pile, "crest_x_m" for the dump.
    run_out(positions, *, family, geometry) -> float
        x99 - L0 (collapse), mean of (x99 - x_p) and (x_p - x1) (pile), x99 - x_c (dump); x99 and x1 are the 99th and
        1st percentiles of the particle x.
    observables(positions, *, d, family, geometry) -> dict   {"repose_deg": float, "run_out_m": float}
    Hostile input (empty or non-[N, 2] array, non-finite value, d <= 0 or non-finite, unknown family) raises ValueError.
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

from pitstudio.granular import observables as obs  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
FAMILIES = ("column-collapse", "pile-formation", "dump-over-crest")


def flank(theta_deg: float, height: float, d: float, x0: float, sign: int) -> np.ndarray:
    """Centres d / 2 below the analytic surface y = height - tan(theta) |x - x0|, every d / 8 along the slope."""
    th = math.radians(theta_deg)
    n = int(height / math.sin(th) / d) * 8 + 4
    xs = x0 + sign * (np.arange(n) + 0.37) * d * 0.125 * math.cos(th)
    ys = height - math.tan(th) * np.abs(xs - x0) - d / 2
    keep = ys >= d / 2
    return np.column_stack([xs[keep], ys[keep]])


def analytic_pile(family: str, theta: float, height_over_d: float, d: float, ref_x: float) -> tuple[np.ndarray, dict]:
    h = height_over_d * d
    if family == "column-collapse":
        return flank(theta, h, d, 0.0, +1), {"column_width_m": 0.2}
    if family == "pile-formation":
        return np.vstack([flank(theta, h, d, ref_x, +1), flank(theta, h, d, ref_x, -1)]), {"pour_point_x_m": ref_x}
    plateau = np.column_stack([ref_x - (np.arange(1, 30) + 0.37) * d * 0.5, np.full(29, h - d / 2)])
    return np.vstack([plateau, flank(theta, h, d, ref_x, +1)]), {"crest_x_m": ref_x}


# ---------------------------------------------------------------- FR-011-05 / P-011-06 repose


@pytest.mark.req("FR-011-05")
@pytest.mark.req("P-011-06")
@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("theta", [20.0, 27.5, 35.0, 45.0])
def test_analytic_pile_returns_its_slope_within_point_four_degrees(family: str, theta: float) -> None:
    d = 0.004
    pts, geo = analytic_pile(family, theta, 40.0, d, 0.3)
    assert abs(obs.repose_angle_deg(pts, d=d, family=family, geometry=geo) - theta) <= 0.4


@pytest.mark.req("P-011-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    family=st.sampled_from(FAMILIES),
    theta=st.floats(20.0, 45.0),
    height_over_d=st.floats(30.0, 45.0),
    d=st.floats(1e-3, 1e-2),
    ref_x=st.floats(-5.0, 5.0),
)
def test_property_extractor_error_below_point_four_degrees_for_piles_at_least_thirty_d_high(
    family: str, theta: float, height_over_d: float, d: float, ref_x: float
) -> None:
    pts, geo = analytic_pile(family, theta, height_over_d, d, ref_x)
    assert abs(obs.repose_angle_deg(pts, d=d, family=family, geometry=geo) - theta) <= 0.4


@pytest.mark.req("P-011-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    family=st.sampled_from(FAMILIES),
    theta=st.floats(20.0, 45.0),
    seed=st.integers(0, 2**32 - 1),
)
def test_permutation_of_the_particles_leaves_the_angle_exactly_unchanged(family: str, theta: float, seed: int) -> None:
    d = 0.004
    pts, geo = analytic_pile(family, theta, 35.0, d, 0.3)
    perm = np.random.default_rng(seed).permutation(len(pts))
    a = obs.repose_angle_deg(pts, d=d, family=family, geometry=geo)
    b = obs.repose_angle_deg(pts[perm], d=d, family=family, geometry=geo)
    assert a == b


@pytest.mark.req("P-011-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    family=st.sampled_from(("pile-formation", "dump-over-crest")),
    theta=st.floats(20.0, 45.0),
    shift=st.floats(-50.0, 50.0),
)
def test_translation_of_particles_and_reference_abscissa_together_leaves_the_angle_unchanged(
    family: str, theta: float, shift: float
) -> None:
    d = 0.004
    pts, geo = analytic_pile(family, theta, 35.0, d, 0.3)
    key = "pour_point_x_m" if family == "pile-formation" else "crest_x_m"
    moved = pts + np.array([shift, 0.0])
    geo2 = {key: geo[key] + shift}
    a = obs.repose_angle_deg(pts, d=d, family=family, geometry=geo)
    b = obs.repose_angle_deg(moved, d=d, family=family, geometry=geo2)
    assert b == pytest.approx(a, abs=1e-9)  # spec: exact; 1e-9 deg admits the rounding of the shifted coordinates


@pytest.mark.req("P-011-06")
@settings(max_examples=EXAMPLES, deadline=None)
@given(theta=st.floats(20.0, 45.0), ref_x=st.floats(-5.0, 5.0))
def test_mirroring_the_pile_about_the_pour_point_leaves_the_angle_unchanged(theta: float, ref_x: float) -> None:
    d = 0.004
    pts, geo = analytic_pile("pile-formation", theta, 35.0, d, ref_x)
    mirrored = pts.copy()
    mirrored[:, 0] = 2.0 * ref_x - pts[:, 0]
    a = obs.repose_angle_deg(pts, d=d, family="pile-formation", geometry=geo)
    b = obs.repose_angle_deg(mirrored, d=d, family="pile-formation", geometry=geo)
    assert b == pytest.approx(a, abs=1e-9)


# ---------------------------------------------------------------- FR-011-05 / P-011-07 run-out


def plateau_cloud(n_bulk_lo: float, n_bulk_hi: float, x_top: float, x_bottom: float | None) -> np.ndarray:
    """1,000 particles: 20 at x_top, 20 at x_bottom (if given), the rest evenly spread strictly between."""
    n_low = 20 if x_bottom is not None else 0
    bulk = np.linspace(n_bulk_lo, n_bulk_hi, 1000 - 20 - n_low)
    xs = np.concatenate([bulk, np.full(20, x_top)] + ([np.full(20, x_bottom)] if x_bottom is not None else []))
    return np.column_stack([xs, np.full(xs.size, 0.01)])


@pytest.mark.req("FR-011-05")
def test_column_collapse_run_out_is_x99_minus_the_column_width_by_hand() -> None:
    pts = plateau_cloud(0.0, 1.0, 1.7, None)
    assert obs.run_out(pts, family="column-collapse", geometry={"column_width_m": 0.2}) == pytest.approx(1.5, abs=1e-12)


@pytest.mark.req("FR-011-05")
def test_pile_run_out_is_the_mean_of_the_two_flank_distances_by_hand() -> None:
    pts = plateau_cloud(-0.5, 0.9, 1.2, -0.8)
    assert obs.run_out(pts, family="pile-formation", geometry={"pour_point_x_m": 0.1}) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.req("FR-011-05")
def test_dump_run_out_is_x99_minus_the_crest_abscissa_by_hand() -> None:
    pts = plateau_cloud(0.2, 1.0, 1.2, None)
    assert obs.run_out(pts, family="dump-over-crest", geometry={"crest_x_m": 0.3}) == pytest.approx(0.9, abs=1e-12)


@pytest.mark.req("FR-011-05")
def test_observables_returns_both_quantities_from_one_call() -> None:
    d = 0.004
    pts, geo = analytic_pile("column-collapse", 30.0, 40.0, d, 0.0)
    out = obs.observables(pts, d=d, family="column-collapse", geometry=geo)
    assert set(out) >= {"repose_deg", "run_out_m"}
    assert out["repose_deg"] == obs.repose_angle_deg(pts, d=d, family="column-collapse", geometry=geo)
    assert out["run_out_m"] == obs.run_out(pts, family="column-collapse", geometry=geo)


def geometry_for(family: str, ref: float) -> dict:
    return {
        "column-collapse": {"column_width_m": 0.2},
        "pile-formation": {"pour_point_x_m": ref},
        "dump-over-crest": {"crest_x_m": ref},
    }[family]


def shifted_geometry(family: str, geo: dict, dx: float, k: float = 1.0) -> dict:
    if family == "column-collapse":
        return {"column_width_m": geo["column_width_m"] * k}
    key = "pour_point_x_m" if family == "pile-formation" else "crest_x_m"
    return {key: geo[key] * k + dx}


@pytest.mark.req("P-011-07")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    family=st.sampled_from(("pile-formation", "dump-over-crest")),
    seed=st.integers(0, 2**32 - 1),
    shift=st.floats(-100.0, 100.0),
)
def test_translating_the_state_and_the_reference_together_leaves_the_run_out_unchanged(
    family: str, seed: int, shift: float
) -> None:
    rng = np.random.default_rng(seed)
    pts = np.column_stack([rng.uniform(-1, 2, 400), rng.uniform(0, 0.3, 400)])
    geo = geometry_for(family, 0.4)
    a = obs.run_out(pts, family=family, geometry=geo)
    b = obs.run_out(pts + np.array([shift, 0.0]), family=family, geometry=shifted_geometry(family, geo, shift))
    assert b == pytest.approx(a, rel=1e-9, abs=1e-9)


@pytest.mark.req("P-011-07")
@settings(max_examples=EXAMPLES, deadline=None)
@given(family=st.sampled_from(FAMILIES), seed=st.integers(0, 2**32 - 1), k=st.floats(0.1, 10.0))
def test_scaling_every_length_by_k_scales_the_run_out_by_k(family: str, seed: int, k: float) -> None:
    rng = np.random.default_rng(seed)
    pts = np.column_stack([rng.uniform(0.0, 2.0, 400), rng.uniform(0, 0.3, 400)])
    geo = geometry_for(family, 0.4)
    a = obs.run_out(pts, family=family, geometry=geo)
    b = obs.run_out(pts * k, family=family, geometry=shifted_geometry(family, geo, 0.0, k))
    assert b == pytest.approx(a * k, rel=1e-9, abs=1e-12)


@pytest.mark.req("P-011-07")
@settings(max_examples=EXAMPLES, deadline=None)
@given(
    family=st.sampled_from(FAMILIES),
    seed=st.integers(0, 2**32 - 1),
    which=st.integers(0, 399),
    delta=st.floats(0.0, 3.0),
)
def test_moving_any_particle_outward_never_decreases_the_run_out(
    family: str, seed: int, which: int, delta: float
) -> None:
    rng = np.random.default_rng(seed)
    pts = np.column_stack([rng.uniform(-1.0, 2.0, 400), rng.uniform(0, 0.3, 400)])
    geo = geometry_for(family, 0.4)
    before = obs.run_out(pts, family=family, geometry=geo)
    moved = pts.copy()
    ref = 0.4 if family != "column-collapse" else 0.0
    outward = 1.0 if (family != "pile-formation" or moved[which, 0] >= ref) else -1.0
    moved[which, 0] += outward * delta
    assert obs.run_out(moved, family=family, geometry=geo) >= before - 1e-12


# ---------------------------------------------------------------- hostile inputs


@pytest.mark.req("FR-011-05")
@pytest.mark.parametrize(
    "positions",
    [
        np.zeros((0, 2)),
        np.zeros((5, 3)),
        np.array([[0.0, np.nan], [1.0, 1.0]]),
        np.array([[np.inf, 0.0], [1.0, 1.0]]),
    ],
    ids=["empty", "three-columns", "nan", "inf"],
)
def test_hostile_positions_are_rejected_with_value_error(positions: np.ndarray) -> None:
    with pytest.raises(ValueError, match=r"."):
        obs.repose_angle_deg(positions, d=0.004, family="column-collapse", geometry={"column_width_m": 0.2})
    with pytest.raises(ValueError, match=r"."):
        obs.run_out(positions, family="column-collapse", geometry={"column_width_m": 0.2})


@pytest.mark.req("FR-011-05")
@pytest.mark.parametrize("d", [0.0, -0.004, float("nan"), float("inf")])
def test_hostile_particle_diameter_is_rejected(d: float) -> None:
    pts, geo = analytic_pile("column-collapse", 30.0, 40.0, 0.004, 0.0)
    with pytest.raises(ValueError, match=r"."):
        obs.repose_angle_deg(pts, d=d, family="column-collapse", geometry=geo)


@pytest.mark.req("FR-011-05")
def test_unknown_family_is_rejected() -> None:
    pts, _ = analytic_pile("column-collapse", 30.0, 40.0, 0.004, 0.0)
    with pytest.raises(ValueError, match="family"):
        obs.repose_angle_deg(pts, d=0.004, family="landslide", geometry={})
