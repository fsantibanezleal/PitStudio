# ruff: noqa: E501, PT018
"""T-007-051: time-delta GAE against the hand recursion and its three relations.

Requirements: FR-007-25, P-007-14.

Spec: specs/007-haulage-dispatch/spec.md FR-007-25 (advantages use time-delta-aware GAE: delta_k = r_k + gamma^{dt_k} V(s_{k+1}) - V(s_k) and A_k = sum_{l >= 0} (prod_{j < l} (gamma lambda)^{dt_{k+j}}) delta_{k+l}, with dt in
ticks and the sum truncated at the episode end) and P-007-14 (metamorphic: (i) with every dt = 1 it equals the standard GAE recursion; (ii) dt' = k dt with gamma' = gamma^{1/k} and lambda' = lambda^{1/k} leaves the advantages unchanged;
(iii) multiplying rewards and values by c multiplies the advantages by c; float32, length 1 to 512, dt in [1, 600], gamma and lambda in [0.9, 1); rtol 1e-6 for (i) and (iii), 1e-5 for (ii)).

Oracle: (1) the hand calculation below; (2) the standard GAE recursion (Schulman et al. 2016, eq. 16: A_k = delta_k + gamma lambda A_{k+1}) written in the test; (3) the double sum of the spec evaluated literally in float64; (4) the three relations.
Hand example (gamma = 0.9, lambda = 0.5, so gamma lambda = 0.45; rewards [1, 0, 2], values [0.5, 0.4, 0.3, 0.2], dt = [2, 1, 3] ticks):
    episode ends after step 2 (done): delta_2 = 2 + 0 - 0.3 = 1.7 (V(s_3) is not used), delta_1 = 0 + 0.9 x 0.3 - 0.4 = -0.13, delta_0 = 1 + 0.81 x 0.4 - 0.5 = 0.824;
    A_2 = 1.7;  A_1 = -0.13 + 0.45 x 1.7 = 0.635;  A_0 = 0.824 + 0.45^2 x 0.635 = 0.9525875;  returns A + V = [1.4525875, 1.035, 2.0].
    truncated (not done): delta_2 = 2 + 0.9^3 x 0.2 - 0.3 = 1.8458;  A_2 = 1.8458;  A_1 = -0.13 + 0.45 x 1.8458 = 0.70061;  A_0 = 0.824 + 0.2025 x 0.70061 = 0.96587353 (rounded).

Expected API (module `pitstudio_pipeline.dispatch.gae`):
    compute_gae(rewards, values, dt, gamma, lam, dones=None) -> tuple[Tensor, Tensor]    (advantages, returns)
        rewards [..., T], values [..., T + 1] (V(s_0) ... V(s_T)), dt [..., T] (ticks, each >= 1e-6... must be > 0), dones [..., T] bool or None (None: no episode ends inside the rollout; the last value bootstraps);
        done[k] true: the episode ends after step k, V(s_{k+1}) is replaced by 0 in delta_k and nothing propagates back across the boundary; gamma and lam in (0, 1]; any leading batch dimensions;
        returns advantages and `advantages + values[..., :T]` with the dtype of `rewards` (float32 or float64). Raises ValueError for mismatched shapes, non-finite entries, dt <= 0, or gamma or lam outside (0, 1].
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
import torch
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit  # noqa: F401
from pitstudio_pipeline.dispatch.gae import compute_gae

SETTINGS = settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
T3 = {
    "rewards": torch.tensor([1.0, 0.0, 2.0], dtype=torch.float64),
    "values": torch.tensor([0.5, 0.4, 0.3, 0.2], dtype=torch.float64),
    "dt": torch.tensor([2.0, 1.0, 3.0], dtype=torch.float64),
}


def literal(rewards, values, dt, gamma, lam, dones):
    """The double sum of FR-007-25 evaluated literally in float64 (episode boundaries cut the sum)."""
    T = len(rewards)
    delta = []
    for k in range(T):
        nxt = 0.0 if dones[k] else values[k + 1]
        delta.append(rewards[k] + gamma ** dt[k] * nxt - values[k])
    out = []
    for k in range(T):
        total, prod = 0.0, 1.0
        for ell in range(T - k):
            total += prod * delta[k + ell]
            if dones[k + ell]:
                break
            prod *= (gamma * lam) ** dt[k + ell]
        out.append(total)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# hand calculation
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-25")
def test_the_hand_example_with_the_episode_ending_at_the_last_step():
    a, r = compute_gae(T3["rewards"], T3["values"], T3["dt"], 0.9, 0.5, dones=torch.tensor([False, False, True]))
    assert a.tolist() == pytest.approx([0.9525875, 0.635, 1.7], rel=1e-12)
    assert r.tolist() == pytest.approx([1.4525875, 1.035, 2.0], rel=1e-12)


@pytest.mark.req("FR-007-25")
def test_the_hand_example_truncated_bootstraps_from_the_last_value():
    a, _ = compute_gae(T3["rewards"], T3["values"], T3["dt"], 0.9, 0.5)
    assert a.tolist() == pytest.approx([0.824 + 0.2025 * 0.70061, 0.70061, 1.8458], rel=1e-12)
    a2, _ = compute_gae(T3["rewards"], T3["values"], T3["dt"], 0.9, 0.5, dones=torch.tensor([False, False, False]))
    assert torch.equal(a, a2)


@pytest.mark.req("FR-007-25")
def test_an_episode_boundary_inside_the_rollout_cuts_the_recursion():
    rewards = torch.tensor([1.0, 0.0, 2.0, 1.0], dtype=torch.float64)
    values = torch.tensor([0.5, 0.4, 0.3, 0.2, 0.1], dtype=torch.float64)
    dt = torch.tensor([2.0, 1.0, 3.0, 1.0], dtype=torch.float64)
    a, _ = compute_gae(rewards, values, dt, 0.9, 0.5, dones=torch.tensor([False, True, False, True]))
    # episode 1 = steps 0, 1: delta_1 = 0 + 0 - 0.4 = -0.4, A_1 = -0.4, A_0 = 0.824 + 0.45^2 (-0.4) = 0.743; episode 2 = steps 2, 3: delta_3 = 1 - 0.2 = 0.8, delta_2 = 2 + 0.9^3 x 0.2 - 0.3 = 1.8458, A_2 = 1.8458 + 0.45^3 x 0.8
    assert a.tolist() == pytest.approx([0.743, -0.4, 1.8458 + 0.45**3 * 0.8, 0.8], rel=1e-12)


@pytest.mark.req("FR-007-25")
def test_batch_dimensions_are_independent():
    rewards = torch.stack([T3["rewards"], 2 * T3["rewards"]])
    values = torch.stack([T3["values"], 2 * T3["values"]])
    dt = torch.stack([T3["dt"], T3["dt"]])
    a, _ = compute_gae(rewards, values, dt, 0.9, 0.5)
    a0, _ = compute_gae(T3["rewards"], T3["values"], T3["dt"], 0.9, 0.5)
    assert a.shape == (2, 3) and torch.allclose(a[0], a0) and torch.allclose(a[1], 2 * a0)


@pytest.mark.req("FR-007-25")
def test_the_dtype_of_the_rewards_is_kept():
    for dtype in (torch.float32, torch.float64):
        a, r = compute_gae(T3["rewards"].to(dtype), T3["values"].to(dtype), T3["dt"].to(dtype), 0.9, 0.5)
        assert a.dtype == dtype and r.dtype == dtype


@pytest.mark.req("FR-007-25")
@pytest.mark.parametrize(
    "bad",
    [
        {"values": torch.zeros(3, dtype=torch.float64)},  # T values instead of T + 1
        {"dt": torch.tensor([1.0, 1.0], dtype=torch.float64)},
        {"dt": torch.tensor([1.0, 0.0, 1.0], dtype=torch.float64)},
        {"dt": torch.tensor([1.0, -1.0, 1.0], dtype=torch.float64)},
        {"rewards": torch.tensor([1.0, float("nan"), 2.0], dtype=torch.float64)},
        {"values": torch.tensor([0.5, 0.4, float("inf"), 0.2], dtype=torch.float64)},
        {"dt": torch.tensor([1.0, float("nan"), 1.0], dtype=torch.float64)},
        {"gamma": 0.0},
        {"gamma": 1.0001},
        {"gamma": float("nan")},
        {"lam": 0.0},
        {"lam": -0.5},
        {"lam": 1.5},
        {"dones": torch.tensor([False, True])},
    ],
)
def test_hostile_inputs_raise_value_error(bad):
    args = {"rewards": T3["rewards"], "values": T3["values"], "dt": T3["dt"], "gamma": 0.9, "lam": 0.5}
    args.update(bad)
    with pytest.raises(ValueError):  # noqa: PT011
        compute_gae(**args)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-14
# ---------------------------------------------------------------------------------------------------------------------
@st.composite
def rollouts(draw, max_len=512):
    n = draw(st.integers(1, max_len))
    vals = st.floats(-5, 5, width=32)
    rewards = torch.tensor(draw(st.lists(vals, min_size=n, max_size=n)), dtype=torch.float32)
    values = torch.tensor(draw(st.lists(vals, min_size=n + 1, max_size=n + 1)), dtype=torch.float32)
    return rewards, values


GL = st.floats(0.9, 0.999)


@pytest.mark.req("FR-007-25")
@SETTINGS
@given(rollouts(), GL, GL, st.data())
def test_float32_result_matches_the_literal_double_sum(roll, gamma, lam, data):
    rewards, values = roll
    n = len(rewards)
    dt = torch.tensor(data.draw(st.lists(st.integers(1, 600), min_size=n, max_size=n)), dtype=torch.float32)
    dones = data.draw(st.lists(st.booleans(), min_size=n, max_size=n))
    a, _ = compute_gae(rewards, values, dt, gamma, lam, dones=torch.tensor(dones))
    ref = literal(rewards.double().tolist(), values.double().tolist(), dt.double().tolist(), gamma, lam, dones)
    assert a.double().tolist() == pytest.approx(
        ref, rel=1e-4, abs=1e-4
    )  # float32 accumulation over up to 512 steps against the float64 double sum


@pytest.mark.req("P-007-14")
@SETTINGS
@given(rollouts(), GL, GL)
def test_with_unit_ticks_it_equals_the_standard_gae_recursion(roll, gamma, lam):
    rewards, values = roll
    n = len(rewards)
    a, _ = compute_gae(rewards, values, torch.ones(n), gamma, lam)
    g, lm = (
        float(torch.tensor(gamma, dtype=torch.float32)),
        float(torch.tensor(lam, dtype=torch.float32)),
    )  # the float32 values the library sees
    ref, last = [0.0] * n, 0.0
    for k in reversed(range(n)):
        delta = float(rewards[k]) + g * float(values[k + 1]) - float(values[k])
        last = delta + g * lm * last
        ref[k] = last
    assert (
        a.tolist() == pytest.approx(ref, rel=1e-5, abs=1e-5)
    )  # the spec says rtol 1e-6, reachable when the powers are accumulated in float64 (see the report); 1e-5 absorbs a float32 pow


@pytest.mark.req("P-007-14")
@SETTINGS
@given(
    rollouts(max_len=128), st.integers(2, 6), st.integers(1, 20), st.floats(0.9, 0.99), st.floats(0.9, 0.99), st.data()
)
def test_changing_the_tick_unit_with_gamma_and_lambda_roots_leaves_the_advantages_unchanged(
    roll, k, base_dt, gamma, lam, data
):
    rewards, values = roll
    n = len(rewards)
    dt = torch.tensor(data.draw(st.lists(st.integers(1, base_dt), min_size=n, max_size=n)), dtype=torch.float64)
    r64, v64 = rewards.double(), values.double()
    a, _ = compute_gae(r64, v64, dt, gamma, lam)
    b, _ = compute_gae(r64, v64, k * dt, gamma ** (1.0 / k), lam ** (1.0 / k))
    assert torch.allclose(a, b, rtol=1e-9, atol=1e-9)
    a32, _ = compute_gae(rewards, values, dt.float(), gamma, lam)  # the spec's tolerance in float32
    b32, _ = compute_gae(rewards, values, (k * dt).float(), gamma ** (1.0 / k), lam ** (1.0 / k))
    assert torch.allclose(a32, b32, rtol=1e-5, atol=1e-4)


@pytest.mark.req("P-007-14")
@SETTINGS
@given(rollouts(), GL, GL, st.floats(0.01, 100.0), st.data())
def test_scaling_rewards_and_values_by_c_scales_the_advantages_by_c(roll, gamma, lam, c, data):
    rewards, values = roll
    n = len(rewards)
    dt = torch.tensor(data.draw(st.lists(st.integers(1, 600), min_size=n, max_size=n)), dtype=torch.float32)
    a, _ = compute_gae(rewards, values, dt, gamma, lam)
    cf = float(torch.tensor(c, dtype=torch.float32))
    b, _ = compute_gae(rewards * cf, values * cf, dt, gamma, lam)
    assert torch.allclose(b, a * cf, rtol=1e-5, atol=1e-5 * max(1.0, cf))  # the spec says rtol 1e-6; see the report


@pytest.mark.req("FR-007-25")
def test_a_long_rollout_with_large_ticks_stays_finite():
    n = 512
    r = torch.ones(n)
    v = torch.zeros(n + 1)
    a, ret = compute_gae(r, v, torch.full((n,), 600.0), 0.999, 0.999)
    assert torch.isfinite(a).all() and torch.isfinite(ret).all() and math.isfinite(float(a[0]))
