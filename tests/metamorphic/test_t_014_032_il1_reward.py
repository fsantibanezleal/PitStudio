# ruff: noqa: E501
"""T-014-032: IL-1 reward terms, the speed limit from the haulage envelopes and shaping that telescopes.

Requirements: FR-014-11, P-014-10.

Spec: specs/014-robot-learning/spec.md FR-014-11: the weighted sum, with weights fixed in the task configuration, of potential-based
progress gamma Phi(s') - Phi(s) (Phi the arc length along the route); -|e_lat|; -|e_psi|; -max(0, v - v_lim) with v_lim(grade,
payload) from the `minephys.haulage` rimpull/retarder envelopes capped at the site limit (default 40 km/h); -|jerk|; a collision
penalty; a penalty while TTC < 3 s; and -P_trac dt (energy). P-014-10: (MR1) the progress terms telescope, sum_t gamma^t F_t =
gamma^T Phi(s_T) - Phi(s_0); (MR2) a stationary truck at gamma = 1 earns zero progress reward; (MR3) mirroring the world leaves every
reward term unchanged; rtol 1e-9 (float64). Plan oracle: "hand-computed reward for a scripted 3-step trajectory".

Oracle: (1) a scripted 3-step trajectory whose six weighted rewards are computed by hand below with the weights of the valid contract
example `il-task.valid.json` (progress 1, lateral 0.5, heading 0.2, overspeed 1, jerk 0.01, collision 100, ttc 5, energy 0.001),
gamma = 0.99, dt = 0.05 s; (2) the telescoping identity as algebra; (3) v_lim by hand: for a steady state on a grade the table
envelope gives the largest speed whose rimpull covers m g (RR + grade) (uphill) or whose retarder force covers m g (-RR - grade)
(downhill), by linear interpolation of the envelope between its samples, capped at the site limit; worked numbers are in the test.
The truck data are those of `machine-params.valid.json` (empty mass 160,000 kg, rated payload 220,000 kg).

Expected API of the implementation (module `pitstudio.robots.reward`, NumPy / float64):
    TTC_PENALTY_THRESHOLD = 3.0
    speed_limit(grade, payload_fraction, *, empty_mass_kg, rated_payload_kg, rolling_resistance, envelope,
                site_limit_kmh=40.0, g=9.81) -> float
        v_lim in m/s. envelope: sequence of (speed [m/s], rimpull [N], retarder [N]) rows, speeds strictly increasing, the two
        force columns non-increasing. m = empty + payload_fraction * rated; TR = rolling_resistance + grade (small-angle grade
        resistance). TR > 0: v_up = the largest speed at which the interpolated rimpull >= m g TR (the last envelope speed when
        the rimpull never falls below it, 0 when even the first sample is below it); TR < 0: v_down from the retarder force and
        m g (-TR); TR = 0: no force limit. v_lim = min(site_limit_kmh / 3.6, v_up or v_down). ValueError naming `envelope`,
        `payload_fraction` (outside [0, 1]), `grade` or `rolling_resistance` (non-finite) for invalid input.
    il1_reward_terms(*, phi, phi_next, gamma, e_lat, e_psi, speed, v_lim, jerk, collided, ttc, traction_power, dt) -> dict[str, float]
        the unweighted signed terms: progress = gamma phi_next - phi; lateral_error = -|e_lat|; heading_error = -|e_psi|;
        overspeed = -max(0, speed - v_lim); jerk = -|jerk|; collision = -1.0 if collided else 0.0; ttc = -1.0 if ttc <
        TTC_PENALTY_THRESHOLD else 0.0; energy = -traction_power * dt (traction_power in W, dt in s).
    il1_reward(terms, weights) -> float
        sum over the eight keys of weights[key] * terms[key]; ValueError naming the key when weights lack a term or hold
        an unknown key.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.reward import TTC_PENALTY_THRESHOLD, il1_reward, il1_reward_terms, speed_limit

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "specs" / "014-robot-learning" / "contracts" / "examples"
WEIGHTS = json.loads((EX / "il-task.valid.json").read_text("utf-8"))["reward_weights"]
TRUCK = json.loads((EX / "machine-params.valid.json").read_text("utf-8"))
GAMMA = 0.99
DT = 0.05
KEYS = ("progress", "lateral_error", "heading_error", "overspeed", "jerk", "collision", "ttc", "energy")

STEP = {"gamma": GAMMA, "dt": DT}


def terms(**kw):
    base = {
        "phi": 0.0, "phi_next": 0.0, "e_lat": 0.0, "e_psi": 0.0, "speed": 5.0, "v_lim": 7.0, "jerk": 0.0,
        "collided": False, "ttc": 30.0, "traction_power": 0.0, **STEP,
    }  # fmt: skip
    base.update(kw)
    return il1_reward_terms(**base)


# --------------------------------------------------------------------------------- scripted 3-step trajectory
SCRIPT = [
    # step 1: moves 1.0 m, 0.2 m left, heading error -0.1, 1 m/s over the limit, jerk 2, TTC 10 s, 20 kW traction
    (
        {"phi": 0.0, "phi_next": 1.0, "e_lat": 0.2, "e_psi": -0.1, "speed": 8.0, "v_lim": 7.0, "jerk": 2.0,
         "collided": False, "ttc": 10.0, "traction_power": 20_000.0},
        {"progress": 0.99, "lateral_error": -0.2, "heading_error": -0.1, "overspeed": -1.0, "jerk": -2.0,
         "collision": 0.0, "ttc": 0.0, "energy": -1000.0},
        # 0.99 + 0.5 (-0.2) + 0.2 (-0.1) + 1 (-1) + 0.01 (-2) + 0 + 0 + 0.001 (-1000) = -1.15
        -1.15,
    ),
    # step 2: moves 1.5 m, 0.4 m right, heading error 0.3, within the limit, jerk 1, TTC 2 s (< 3 s), no traction
    (
        {"phi": 1.0, "phi_next": 2.5, "e_lat": -0.4, "e_psi": 0.3, "speed": 6.0, "v_lim": 7.0, "jerk": 1.0,
         "collided": False, "ttc": 2.0, "traction_power": 0.0},
        {"progress": 0.99 * 2.5 - 1.0, "lateral_error": -0.4, "heading_error": -0.3, "overspeed": 0.0, "jerk": -1.0,
         "collision": 0.0, "ttc": -1.0, "energy": 0.0},
        # 1.475 + 0.5 (-0.4) + 0.2 (-0.3) + 0 + 0.01 (-1) + 0 + 5 (-1) + 0 = -3.795
        -3.795,
    ),
    # step 3: stationary at phi = 2.5, collision, TTC 0.5 s
    (
        {"phi": 2.5, "phi_next": 2.5, "e_lat": 0.0, "e_psi": 0.0, "speed": 0.0, "v_lim": 7.0, "jerk": 0.0,
         "collided": True, "ttc": 0.5, "traction_power": 0.0},
        {"progress": 0.99 * 2.5 - 2.5, "lateral_error": 0.0, "heading_error": 0.0, "overspeed": 0.0, "jerk": 0.0,
         "collision": -1.0, "ttc": -1.0, "energy": 0.0},
        # -0.025 + 100 (-1) + 5 (-1) = -105.025
        -105.025,
    ),
]  # fmt: skip


@pytest.mark.req("FR-014-11")
def test_the_weights_of_the_contract_example_are_the_ones_used_by_the_hand_calculation() -> None:
    assert WEIGHTS == {
        "progress": 1.0, "lateral_error": 0.5, "heading_error": 0.2, "overspeed": 1.0, "jerk": 0.01, "collision": 100.0,
        "ttc": 5.0, "energy": 0.001,
    }  # fmt: skip
    assert TTC_PENALTY_THRESHOLD == 3.0


@pytest.mark.req("FR-014-11")
@pytest.mark.parametrize("i", [0, 1, 2])
def test_each_term_of_the_scripted_trajectory(i) -> None:
    kw, want_terms, _ = SCRIPT[i]
    got = il1_reward_terms(**kw, **STEP)
    assert set(got) == set(KEYS)
    for k in KEYS:
        assert got[k] == pytest.approx(want_terms[k], rel=1e-9, abs=1e-12), k


@pytest.mark.req("FR-014-11")
@pytest.mark.parametrize("i", [0, 1, 2])
def test_the_weighted_reward_of_the_scripted_trajectory_is_the_hand_calculation(i) -> None:
    kw, _, want = SCRIPT[i]
    assert il1_reward(il1_reward_terms(**kw, **STEP), WEIGHTS) == pytest.approx(want, rel=1e-9)


@pytest.mark.req("FR-014-11")
def test_the_ttc_penalty_applies_strictly_below_three_seconds() -> None:
    assert terms(ttc=2.999)["ttc"] == -1.0
    assert terms(ttc=3.0)["ttc"] == 0.0
    assert terms(ttc=30.0)["ttc"] == 0.0
    assert terms(ttc=math.inf)["ttc"] == 0.0
    assert terms(ttc=0.0)["ttc"] == -1.0


@pytest.mark.req("FR-014-11")
def test_overspeed_penalises_only_the_excess_over_the_limit() -> None:
    assert terms(speed=9.5, v_lim=7.0)["overspeed"] == pytest.approx(-2.5, rel=1e-12)
    assert terms(speed=7.0, v_lim=7.0)["overspeed"] == 0.0
    assert terms(speed=2.0, v_lim=7.0)["overspeed"] == 0.0


@pytest.mark.req("FR-014-11")
def test_the_weights_scale_the_terms_linearly_and_zero_weights_switch_a_term_off() -> None:
    t = il1_reward_terms(**SCRIPT[0][0], **STEP)
    doubled = {k: 2.0 * v for k, v in WEIGHTS.items()}
    assert il1_reward(t, doubled) == pytest.approx(2.0 * il1_reward(t, WEIGHTS), rel=1e-12)
    only_progress = {k: (1.0 if k == "progress" else 0.0) for k in KEYS}
    assert il1_reward(t, only_progress) == pytest.approx(0.99, rel=1e-12)


@pytest.mark.req("FR-014-11")
@pytest.mark.parametrize("bad_key", ["bonus", "Progress", ""])
def test_weights_with_an_unknown_key_are_rejected_naming_it(bad_key) -> None:
    t = il1_reward_terms(**SCRIPT[0][0], **STEP)
    with pytest.raises(ValueError, match=rf"{bad_key}" if bad_key else r".+"):
        il1_reward(t, {**WEIGHTS, bad_key: 1.0})


@pytest.mark.req("FR-014-11")
@pytest.mark.parametrize("missing", KEYS)
def test_weights_missing_a_term_are_rejected_naming_it(missing) -> None:
    t = il1_reward_terms(**SCRIPT[0][0], **STEP)
    with pytest.raises(ValueError, match=missing):
        il1_reward(t, {k: v for k, v in WEIGHTS.items() if k != missing})


# ---------------------------------------------------------------------------------------------------- P-014-10
@pytest.mark.req("P-014-10")
def test_mr1_the_scripted_progress_terms_telescope() -> None:
    f = [il1_reward_terms(**kw, **STEP)["progress"] for kw, _t, _w in SCRIPT]
    assert sum(GAMMA**t * f[t] for t in range(3)) == pytest.approx(GAMMA**3 * 2.5 - 0.0, rel=1e-9)  # 2.4257475


@pytest.mark.req("P-014-10")
@given(st.lists(st.floats(0.0, 500.0), min_size=2, max_size=60), st.floats(0.5, 1.0))
@settings(max_examples=300, deadline=None)
def test_mr1_property_discounted_progress_sums_to_the_boundary_potentials(phis, gamma) -> None:
    total = 0.0
    for t in range(len(phis) - 1):
        f = il1_reward_terms(**{**_base(), "phi": phis[t], "phi_next": phis[t + 1], "gamma": gamma})["progress"]
        total += gamma**t * f
    T = len(phis) - 1
    assert total == pytest.approx(gamma**T * phis[T] - phis[0], rel=1e-9, abs=1e-9)


def _base() -> dict:
    return {
        "phi": 0.0, "phi_next": 0.0, "gamma": 1.0, "e_lat": 0.0, "e_psi": 0.0, "speed": 5.0, "v_lim": 7.0, "jerk": 0.0,
        "collided": False, "ttc": 30.0, "traction_power": 0.0, "dt": DT,
    }  # fmt: skip


@pytest.mark.req("P-014-10")
@given(st.floats(0.0, 500.0), st.integers(1, 50))
@settings(max_examples=100, deadline=None)
def test_mr2_a_stationary_truck_at_gamma_one_earns_zero_progress(phi, n) -> None:
    for _ in range(n):
        assert il1_reward_terms(**{**_base(), "phi": phi, "phi_next": phi, "gamma": 1.0})["progress"] == 0.0


@pytest.mark.req("P-014-10")
@given(
    st.floats(-5.0, 5.0), st.floats(-math.pi, math.pi), st.floats(0.0, 20.0), st.floats(0.0, 20.0),
    st.floats(-50.0, 50.0), st.booleans(), st.floats(0.0, 30.0), st.floats(0.0, 5e5),
)  # fmt: skip
@settings(max_examples=200, deadline=None)
def test_mr3_mirroring_the_world_leaves_every_reward_term_unchanged(
    e_lat, e_psi, speed, v_lim, jerk, hit, ttc, power
) -> None:
    kw = {**_base(), "phi": 3.0, "phi_next": 3.4, "gamma": 0.99, "speed": speed, "v_lim": v_lim, "jerk": jerk, "collided": hit,
          "ttc": ttc, "traction_power": power}  # fmt: skip
    plain = il1_reward_terms(**{**kw, "e_lat": e_lat, "e_psi": e_psi})
    mirrored = il1_reward_terms(**{**kw, "e_lat": -e_lat, "e_psi": -e_psi})  # P-014-09 MR2: e_lat and e_psi change sign
    for k in KEYS:
        assert mirrored[k] == pytest.approx(plain[k], rel=1e-9, abs=1e-12)


# --------------------------------------------------------------------------------------------------- v_lim
ENVELOPE_UP = [(0.0, 900_000.0, 800_000.0), (5.0, 700_000.0, 500_000.0), (10.0, 350_000.0, 250_000.0),
               (15.0, 200_000.0, 150_000.0), (20.0, 100_000.0, 100_000.0)]  # fmt: skip
KW = {
    "empty_mass_kg": TRUCK["empty_mass_kg"], "rated_payload_kg": TRUCK["rated_payload_kg"], "rolling_resistance": 0.03,
    "envelope": ENVELOPE_UP,
}  # fmt: skip
SITE = 40.0 / 3.6  # 11.111 m/s


@pytest.mark.req("FR-014-11")
def test_the_site_limit_caps_the_speed_where_the_envelope_allows_more() -> None:
    # flat road, half payload: m = 160,000 + 110,000 = 270,000 kg; F = m g 0.03 = 79,461 N, covered up to > 20 m/s
    assert speed_limit(0.0, 0.5, **KW) == pytest.approx(SITE, rel=1e-12)
    # 8 % uphill: F = 270,000 * 9.81 * 0.11 = 291,357 N -> envelope speed 11.95 m/s, above the 11.11 m/s site limit
    assert speed_limit(0.08, 0.5, **KW) == pytest.approx(SITE, rel=1e-12)


@pytest.mark.req("FR-014-11")
def test_a_steep_uphill_is_limited_by_the_rimpull_envelope() -> None:
    # 12 % uphill, half payload: F = 270,000 * 9.81 * 0.15 = 397,305 N, between 5 m/s (700 kN) and 10 m/s (350 kN):
    # v = 5 + 5 (700,000 - 397,305) / 350,000 = 9.32421 m/s
    assert speed_limit(0.12, 0.5, **KW) == pytest.approx(5.0 + 5.0 * (700_000.0 - 397_305.0) / 350_000.0, rel=1e-9)
    assert speed_limit(0.12, 0.5, **KW) == pytest.approx(9.32421, abs=1e-4)


@pytest.mark.req("FR-014-11")
def test_a_steep_downhill_is_limited_by_the_retarder_envelope() -> None:
    # -15 % grade, full payload: m = 380,000 kg, TR = 0.03 - 0.15 = -0.12, F = 380,000 * 9.81 * 0.12 = 447,336 N, between
    # 5 m/s (500 kN) and 10 m/s (250 kN): v = 5 + 5 (500,000 - 447,336) / 250,000 = 6.05328 m/s
    assert speed_limit(-0.15, 1.0, **KW) == pytest.approx(5.0 + 5.0 * (500_000.0 - 447_336.0) / 250_000.0, rel=1e-9)
    assert speed_limit(-0.15, 1.0, **KW) == pytest.approx(6.05328, abs=1e-4)


@pytest.mark.req("FR-014-11")
def test_a_force_the_envelope_never_covers_gives_zero_and_one_it_always_covers_gives_the_cap() -> None:
    assert speed_limit(0.60, 1.0, **KW) == 0.0  # m g TR = 380,000 * 9.81 * 0.63 = 2.35 MN > 900 kN at standstill
    assert speed_limit(0.0, 0.0, **{**KW, "rolling_resistance": 0.0}) == pytest.approx(SITE, rel=1e-12)


@pytest.mark.req("FR-014-11")
def test_the_site_limit_is_a_parameter() -> None:
    assert speed_limit(0.0, 0.5, site_limit_kmh=30.0, **KW) == pytest.approx(30.0 / 3.6, rel=1e-12)
    # 20 km/h = 5.556 m/s is below the envelope speed 9.32 m/s of the 12 % grade, so the site limit caps it
    assert speed_limit(0.12, 0.5, site_limit_kmh=20.0, **KW) == pytest.approx(20.0 / 3.6, rel=1e-12)


@pytest.mark.req("FR-014-11")
@given(st.floats(-0.12, 0.12), st.floats(0.0, 1.0), st.floats(0.0, 1.0))
@settings(max_examples=200, deadline=None)
def test_property_the_limit_is_within_zero_and_the_site_limit_and_falls_with_payload(grade, p1, p2) -> None:
    lo, hi = min(p1, p2), max(p1, p2)
    v_lo = speed_limit(grade, lo, **KW)
    v_hi = speed_limit(grade, hi, **KW)
    assert 0.0 <= v_hi <= v_lo <= SITE + 1e-12


@pytest.mark.req("FR-014-11")
@pytest.mark.parametrize(
    ("over", "name"),
    [
        ({"payload_fraction": 1.2}, "payload_fraction"),
        ({"payload_fraction": -0.1}, "payload_fraction"),
        ({"payload_fraction": math.nan}, "payload_fraction"),
        ({"grade": math.nan}, "grade"),
        ({"grade": math.inf}, "grade"),
        ({"envelope": []}, "envelope"),
        ({"envelope": [(0.0, 1.0, 1.0)]}, "envelope"),
        ({"envelope": [(5.0, 9e5, 9e5), (5.0, 8e5, 8e5)]}, "envelope"),  # speeds not increasing
        ({"envelope": [(0.0, 8e5, 9e5), (5.0, 9e5, 8e5)]}, "envelope"),  # rimpull rises with speed
    ],
)
def test_invalid_inputs_raise_value_error_naming_the_argument(over, name) -> None:
    args = {"grade": 0.05, "payload_fraction": 0.5, **KW}
    args.update(over)
    grade = args.pop("grade")
    payload = args.pop("payload_fraction")
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        speed_limit(grade, payload, **args)
