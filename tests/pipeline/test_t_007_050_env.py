# ruff: noqa: E501, PT018
"""T-007-050: the vectorised environment on CPU: tick script, masks, deterministic and MVA oracles, batch independence, relabelling, time dilation; hostile configurations rejected before any allocation.

Requirements: FR-007-23, FR-007-24, FR-007-43, P-007-13, P-007-08.

Spec: specs/007-haulage-dispatch/spec.md FR-007-23 (the vectorised environment `pitstudio_pipeline.dispatch.env` simulates B >= 1 independent copies of a scenario's haul cycle as PyTorch tensors on CPU or CUDA; fleets are padded to 40
trucks with a mask; it is event-stepped with a decision tick dt <= 10 s and uses the bundle's free-flow leg times, mean service times and variate-profile families; the reward of decision k is the fleet's tonnes dumped in (t_k, t_{k+1}]
divided by 1,000, with no other shaping), FR-007-24 (the environment masks every target that is not serviceable or not reachable for the deciding truck), FR-007-43 (B < 1, a bundle with more than 40 trucks or 16 targets, dt <= 0 s or
> 10 s, or a non-finite or negative leg or service time raises `InvalidEnvConfig` before allocating any tensor), P-007-13 ((a) under the `deterministic` profile it reproduces P-007-09(b); (b) under the `exponential` profile with `fixed`
dispatch it reproduces exact MVA within max(3 SE, 1 %); (c) the trajectory of copy b is identical for B = 1 and B = 64 with the same per-copy seed; (d) a strictly increasing relabelling of truck ids leaves the copy's tonnes series
unchanged; CPU device), P-007-08 (time dilation by 2 doubles every time exactly; tonnes identical), spec section 8 item 7 (observation features: truck token of 12 and target token of 9; reward) and DC-007-04 (input shapes [B, 40, 12],
[B, 16, 9], masks [B, 40] and [B, 16]).

Oracle: hand calculation on the two-truck script network (tests/support/p007_env.py: loaders 1 and 2, dump 3; roads of 1,500 m and 3,000 m at 20 km/h, legs 270 s and 540 s; loading 258 s, dumping 55 s, payload 227 t):
    truck 1 (start loader 1): loads [0, 258], arrives at the dump at 258 + 270 = 528, dumps [528, 583];  truck 2 (start loader 2): loads [0, 258], arrives at 258 + 540 = 798, dumps [798, 853].
    A truck that finishes dumping is decided at the next tick: with dt = 10 s truck 1 at ceil(583 / 10) x 10 = 590 and truck 2 at ceil(853 / 10) x 10 = 860; with dt = 7 s at 588 and 854.
    Rewards (horizon 1,200 s): decision 0 (590 s) -> decision 1 (860 s): the dump completed at 853 s is in (590, 860]: 227 / 1000 = 0.227; decision 1 -> horizon: no dump completes (the next ones arrive at 1,388 s or later): 0.
    Features at decision 0: ETAs of the deciding truck from the dump: loader 1 270 s = 0.075 h, loader 2 540 s = 0.15 h; loader mean service 258 s = 0.071667 h; spots 1 / 4 = 0.25; truck 2 is travelling loaded with
    208 s (0.057778 h) left (798 - 590) and payload / mean payload = 1.
    A single truck: one cycle is 258 + 270 + 55 + 270 = 853 s; with dt = 1 s no tick delay arises, the first dump completes at 583 s and the 34th at 583 + 33 x 853 = 28,732 s <= 28,800 s: 34 x 227 = 7,718 t in 8 h.
    The closed-form cycle rate min(N / 853, 1 / 258, 1 / 55) cycles per second (P-007-09(b)) and exact MVA (test_t_007_017) for the exponential family; the relations of P-007-13 and P-007-08.

Expected API (module `pitstudio_pipeline.dispatch.env`; errors in `pitstudio_pipeline.haulage.errors`):
    errors.InvalidEnvConfig(HaulError)
    EnvConfig.from_bundle(bundle: dict, *, dt_s: float = 10.0, dilation: float = 1.0) -> EnvConfig
        validates (InvalidEnvConfig, nothing allocated): 1 <= trucks <= 40, 1 <= loaders <= 16 (the targets), 0 < dt_s <= 10 and finite, every segment length, speed limit and service time (loader class pass_time_s / spot_time_s, dump_mean_s)
        finite and positive (non-negative for lengths), `dilation` > 0 multiplies the loader pass and spot times and divides the accelerations (P-007-08 on the environment).
    VectorEnv(config: EnvConfig, *, batch: int, seeds: Sequence[int], device: str = "cpu")
        `batch` a positive int (InvalidEnvConfig otherwise, before any tensor is allocated); `seeds` has one entry per copy (the per-copy generators are derived from them); targets are the bundle's loaders in ascending node order
        (slot 0 is the lowest node id); trucks occupy slots 0..n-1 in ascending id order.
        reset() -> StepResult;   step(actions: torch.LongTensor [B]) -> StepResult      one decision per copy per step (copies that are done ignore the action)
        StepResult(obs, reward, done, info): obs = {"truck": float32 [B, 40, 12], "target": float32 [B, 16, 9], "truck_mask": bool [B, 40], "target_mask": bool [B, 16]}; reward float32 [B]; done bool [B];
        info = {"time_s": float64 [B] (the decision time of the observation), "deciding": int64 [B] (truck slot), "tonnes": float64 [B] (cumulative tonnes dumped)}
        Semantics: all trucks start at their start loader at t = 0 (no stagger) and begin loading; a truck that completes a dump is decided at the next tick (a multiple of dt_s at or after its completion); the decision names a
        target slot, the truck travels the free-flow leg from the dump to that loader, queues FCFS (capacity n_spots) and loads (mean service time, profile families), then travels to the loader's declared dump, queues FCFS
        and dumps; decisions are taken one per step in (time, truck slot) order; reward = tonnes completed in (t_k, t_{k+1}] / 1000 (t_{K+1} = horizon for the last decision); done when no decision remains before the horizon.
        A masked or out-of-range action raises ValueError. Truck token (12): state one-hot [travel-empty, queue-loader, loading, travel-loaded, queue-dump, dumping, parked] (indices 0-6), payload / mean payload (7), time left in the state in
        hours (8), ETA to the current target in hours (9), deciding flag (10), valid flag (11). Target token (9): loader/dump flag (0), queued / 40 (1), inbound / 40 (2), time until free in hours (3), backlog in hours (4), mean service time in
        hours (5), ETA of the deciding truck in hours (6; 0 when masked), spots / 4 (7), serviceable flag (8). Padding slots are all zero.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_env as hand
import p007_kit as kit
from pitstudio_pipeline.dispatch.env import EnvConfig, VectorEnv
from pitstudio_pipeline.haulage.errors import InvalidEnvConfig

H = 3600.0


def env_for(bundle=None, *, batch=1, seeds=None, dt=10.0, **kw):
    cfg = EnvConfig.from_bundle(bundle or hand.script_bundle(), dt_s=dt)
    return VectorEnv(cfg, batch=batch, seeds=seeds if seeds is not None else list(range(batch)), device="cpu", **kw)


def first_valid(obs):
    return obs["target_mask"].float().argmax(dim=1)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-43: hostile configurations, before any allocation
# ---------------------------------------------------------------------------------------------------------------------
def many_trucks(n):
    b = hand.script_bundle()
    b["fleet"] = [{"id": i + 1, "truck_class": "CAT_793F", "start_loader": 1 if i % 2 == 0 else 2} for i in range(n)]
    return b


def many_loaders(n):
    b = hand.script_bundle()
    nodes, segs = [{"id": 1000, "kind": "dump", "pos_m": [5000.0, 0.0, 1000.0]}], []
    b["loaders"], b["fleet"] = [], [{"id": 1, "truck_class": "CAT_793F", "start_loader": 1}]
    for k in range(1, n + 1):
        nodes.append({"id": k, "kind": "face", "pos_m": [0.0, 100.0 * k, 1000.0]})
        segs.append(
            kit.segment_entry(k, k, 1000, (0.0, 100.0 * k, 1000.0), (5000.0, 0.0, 1000.0), speed_limit_kmh=20.0)
        )
        b["loaders"].append({"node": k, "loader_class": "SHOVEL_45", "n_spots": 1, "destination_dump": 1000})
    b["network"] = {"nodes": nodes, "segments": segs, "zones": [], "junctions": []}
    b["dumps"] = [1000]
    return b


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize("batch", [0, -1, -64, 1.5, "8", None, True, float("nan")])
def test_a_batch_below_one_or_not_an_integer_raises_before_any_tensor_is_allocated(monkeypatch, batch):
    cfg = EnvConfig.from_bundle(hand.script_bundle())

    def boom(*a, **k):
        raise AssertionError("a tensor was allocated")

    for name in ("zeros", "ones", "empty", "full", "tensor", "arange", "zeros_like", "randn", "rand", "Generator"):
        monkeypatch.setattr(torch, name, boom)
    with pytest.raises(InvalidEnvConfig):
        VectorEnv(cfg, batch=batch, seeds=[0], device="cpu")


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize("dt", [0.0, -1.0, 10.001, 11.0, 1e9, float("nan"), float("inf"), "10", None])
def test_a_tick_outside_zero_to_ten_seconds_is_invalid(dt):
    with pytest.raises(InvalidEnvConfig):
        EnvConfig.from_bundle(hand.script_bundle(), dt_s=dt)


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize("dt", [0.001, 1.0, 7.0, 10.0])
def test_the_boundary_ticks_are_accepted(dt):
    assert EnvConfig.from_bundle(hand.script_bundle(), dt_s=dt) is not None


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize(
    ("make", "ok"),
    [
        (lambda: many_trucks(40), True),
        (lambda: many_trucks(41), False),
        (lambda: many_trucks(400), False),
        (lambda: many_loaders(16), True),
        (lambda: many_loaders(17), False),
        (lambda: many_loaders(40), False),
    ],
)
def test_more_than_40_trucks_or_16_targets_is_invalid(make, ok):
    if ok:
        assert EnvConfig.from_bundle(make()) is not None
    else:
        with pytest.raises(InvalidEnvConfig):
            EnvConfig.from_bundle(make())


def mutate(path, value):
    def f(b):
        node = b
        parts = path.split("/")
        for p in parts[:-1]:
            node = node[int(p)] if isinstance(node, list) else node[p]
        node[parts[-1]] = value
        return b

    return f


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize(
    "bad",
    [
        mutate("network/segments/0/length_m", float("nan")),
        mutate("network/segments/0/length_m", float("inf")),
        mutate("network/segments/0/length_m", -1500.0),
        mutate("network/segments/0/length_m", 0.0),
        mutate("network/segments/1/speed_limit_kmh", float("nan")),
        mutate("network/segments/1/speed_limit_kmh", 0.0),
        mutate("network/segments/1/speed_limit_kmh", -20.0),
        mutate("engine_constants/dump_mean_s", float("nan")),
        mutate("engine_constants/dump_mean_s", -55.0),
        mutate("engine_constants/dump_mean_s", float("inf")),
        mutate("equipment/loader_classes/0/pass_time_s", -38.0),
        mutate("equipment/loader_classes/0/spot_time_s", float("nan")),
    ],
)
def test_a_non_finite_or_negative_leg_or_service_time_is_invalid(bad):
    with pytest.raises(InvalidEnvConfig):
        EnvConfig.from_bundle(bad(hand.script_bundle()))


@pytest.mark.req("FR-007-43")
@pytest.mark.parametrize("dilation", [0.0, -2.0, float("nan"), float("inf")])
def test_a_bad_dilation_is_invalid(dilation):
    with pytest.raises(InvalidEnvConfig):
        EnvConfig.from_bundle(hand.script_bundle(), dilation=dilation)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-23: shapes, the hand-calculated tick script, rewards
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-23")
def test_observation_shapes_dtypes_and_padding():
    res = env_for(batch=3, seeds=[1, 2, 3]).reset()
    o = res.obs
    assert (o["truck"].shape, o["target"].shape, o["truck_mask"].shape, o["target_mask"].shape) == (
        (3, 40, 12),
        (3, 16, 9),
        (3, 40),
        (3, 16),
    )
    assert (
        o["truck"].dtype == torch.float32
        and o["target"].dtype == torch.float32
        and o["truck_mask"].dtype == torch.bool
        and o["target_mask"].dtype == torch.bool
    )
    assert (
        res.reward.shape == (3,)
        and res.reward.dtype == torch.float32
        and res.done.dtype == torch.bool
        and not bool(res.done.any())
    )
    assert o["truck_mask"][:, :2].all() and not o["truck_mask"][:, 2:].any()  # two trucks, padded to 40
    assert o["target_mask"][:, :2].all() and not o["target_mask"][:, 2:].any()  # two loaders, padded to 16
    assert (
        float(o["truck"][:, 2:].abs().sum()) == 0.0 and float(o["target"][:, 2:].abs().sum()) == 0.0
    )  # padding slots are zero
    assert (
        res.info["time_s"].dtype == torch.float64
        and res.info["deciding"].dtype == torch.int64
        and res.info["tonnes"].dtype == torch.float64
    )


@pytest.mark.req("FR-007-23")
def test_the_first_decision_is_truck_1_at_the_next_tick_after_its_dump_with_the_hand_calculated_features():
    res = env_for(dt=10.0).reset()
    assert float(res.info["time_s"][0]) == 590.0 and int(res.info["deciding"][0]) == 0  # 583 s rounded up to the tick
    assert float(res.info["tonnes"][0]) == pytest.approx(227.0)  # truck 1's dump completed at 583 s
    t, g = res.obs["target"][0], res.obs["truck"][0]
    for slot, eta in ((0, 270.0 / H), (1, 540.0 / H)):
        assert float(t[slot, 6]) == pytest.approx(eta, abs=1e-6)  # ETA of the deciding truck
        assert float(t[slot, 1]) == 0.0 and float(t[slot, 2]) == 0.0  # nobody queued, nobody inbound
        assert float(t[slot, 3]) == pytest.approx(0.0, abs=1e-9) and float(t[slot, 4]) == pytest.approx(
            0.0, abs=1e-9
        )  # both loaders are free
        assert (
            float(t[slot, 5]) == pytest.approx(258.0 / H, abs=1e-6)
            and float(t[slot, 7]) == pytest.approx(0.25)
            and float(t[slot, 8]) == 1.0
        )
    assert float(t[0, 0]) == float(t[1, 0])  # both targets are loaders
    assert float(g[0, 10]) == 1.0 and float(g[0, 11]) == 1.0  # truck 1 is deciding
    assert [float(x) for x in g[1, :7]] == [0, 0, 0, 1, 0, 0, 0]  # truck 2 travels loaded
    assert (
        float(g[1, 7]) == pytest.approx(1.0)
        and float(g[1, 8]) == pytest.approx(208.0 / H, abs=1e-6)
        and float(g[1, 9]) == pytest.approx(208.0 / H, abs=1e-6)
    )
    assert float(g[1, 10]) == 0.0 and float(g[1, 11]) == 1.0


@pytest.mark.req("FR-007-23")
@pytest.mark.parametrize("action", [0, 1])
def test_the_two_step_script_times_rewards_and_done(action):
    env = env_for(dt=10.0)
    env.reset()
    r1 = env.step(torch.tensor([action]))
    assert (
        float(r1.info["time_s"][0]) == 860.0 and int(r1.info["deciding"][0]) == 1 and not bool(r1.done[0])
    )  # truck 2 at ceil(853 / 10) x 10
    assert float(r1.reward[0]) == pytest.approx(0.227, abs=1e-6)  # its dump at 853 s lies in (590, 860]
    assert float(r1.info["tonnes"][0]) == pytest.approx(454.0)
    r2 = env.step(torch.tensor([action]))
    assert bool(r2.done[0]) and float(r2.reward[0]) == 0.0  # nothing completes in (860, 1200]
    assert float(r2.info["tonnes"][0]) == pytest.approx(454.0)


@pytest.mark.req("FR-007-23")
def test_a_coarser_tick_delays_the_decisions_to_the_next_multiple_of_dt():
    res = env_for(dt=7.0).reset()
    assert float(res.info["time_s"][0]) == 588.0  # 583 s -> 84 x 7
    assert float(env_for(dt=7.0).reset().obs["target"][0, 0, 6]) == pytest.approx(270.0 / H, abs=1e-6)
    r1 = env_for(dt=7.0)
    r1.reset()
    assert float(r1.step(torch.tensor([0])).info["time_s"][0]) == 854.0  # 853 s -> 122 x 7


@pytest.mark.req("FR-007-23")
@pytest.mark.parametrize("action", [0, 1])
def test_the_chosen_target_decides_where_the_truck_goes(action):
    # dt = 7 s: truck 1 is decided at 588 s and is still travelling (270 s to loader 1 -> 858 s, 540 s to loader 2 -> 1,128 s) when truck 2 is decided at 854 s
    env = env_for(dt=7.0)
    env.reset()
    res = env.step(torch.tensor([action]))
    assert float(res.info["time_s"][0]) == 854.0 and int(res.info["deciding"][0]) == 1
    t = res.obs["target"][0]
    chosen, other = action, 1 - action
    assert float(t[chosen, 2]) == pytest.approx(1.0 / 40.0, abs=1e-9) and float(t[other, 2]) == 0.0  # inbound / 40
    assert float(t[chosen, 4]) == pytest.approx(258.0 / H, abs=1e-6) and float(t[other, 4]) == pytest.approx(
        0.0, abs=1e-9
    )  # backlog = 0 + 1 x 258 s
    assert float(t[chosen, 3]) == pytest.approx(0.0, abs=1e-9)  # nobody is loading yet: both loaders are free
    g = res.obs["truck"][0, 0]
    assert float(g[10]) == 0.0 and float(g[9]) == pytest.approx(
        (858.0 if action == 0 else 1128.0) / H - 854.0 / H, abs=1e-6
    )  # truck 1: ETA to its target from now


@pytest.mark.req("FR-007-23")
def test_the_reward_is_tonnes_in_thousands_and_nothing_else():
    cfg = EnvConfig.from_bundle(hand.family_bundle(6, horizon_s=4 * H, profile="engine"), dt_s=5.0)
    env = VectorEnv(cfg, batch=4, seeds=[11, 12, 13, 14], device="cpu")
    res = env.reset()
    first = res.info["tonnes"].clone()
    total = torch.zeros(4, dtype=torch.float64)
    steps = 0
    while not bool(res.done.all()):
        res = env.step(first_valid(res.obs))
        total += res.reward.to(torch.float64)
        steps += 1
        assert steps < 50_000
    assert torch.allclose(
        total, (res.info["tonnes"] - first) / 1000.0, rtol=1e-5, atol=1e-6
    )  # tonnes after the first decision, no shaping term


@pytest.mark.req("FR-007-23")
def test_a_finished_copy_stays_finished_and_ignores_actions():
    env = env_for(batch=2, seeds=[1, 2])
    res = env.reset()
    for _ in range(2):
        res = env.step(torch.tensor([0, 0]))
    assert bool(res.done.all())
    again = env.step(torch.tensor([1, 1]))
    assert (
        bool(again.done.all())
        and float(again.reward.abs().sum()) == 0.0
        and torch.equal(again.info["tonnes"], res.info["tonnes"])
    )


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-24: masks
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-24")
def test_an_unreachable_loader_is_masked_and_choosing_it_raises():
    b = hand.script_bundle()
    b["network"]["segments"][1]["one_way"] = True  # road 2 -> 3 only: loader 2 cannot be reached from the dump
    env = env_for(bundle=b)
    res = env.reset()
    assert res.obs["target_mask"][0].tolist() == [True, False] + [False] * 14
    assert (
        float(res.obs["target"][0, 1, 6]) == 0.0 and float(res.obs["target"][0, 1, 8]) == 0.0
    )  # masked: ETA 0, not serviceable
    with pytest.raises(ValueError):  # noqa: PT011
        env.step(torch.tensor([1]))
    assert float(env.step(torch.tensor([0])).info["tonnes"][0]) > 0


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("action", [-1, 16, 17, 99])
def test_out_of_range_and_padding_actions_are_rejected(action):
    env = env_for()
    env.reset()
    with pytest.raises(ValueError):  # noqa: PT011
        env.step(torch.tensor([action]))


@pytest.mark.req("FR-007-24")
@pytest.mark.parametrize("bad", [torch.tensor([0, 0]), torch.tensor([[0]]), torch.tensor([0.0]), torch.tensor([True])])
def test_actions_of_the_wrong_shape_or_dtype_are_rejected(bad):
    env = env_for()
    env.reset()
    with pytest.raises((ValueError, TypeError)):
        env.step(bad)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-13
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("P-007-13")
def test_one_truck_dumps_the_hand_calculated_34_loads_in_8_hours():
    cfg = EnvConfig.from_bundle(hand.family_bundle(1), dt_s=1.0)  # integer leg and service times: no tick delay arises
    env = VectorEnv(cfg, batch=1, seeds=[0], device="cpu")
    res = env.reset()
    while not bool(res.done[0]):
        res = env.step(torch.tensor([0]))
    assert float(res.info["tonnes"][0]) == pytest.approx(
        34 * 227.0, rel=1e-12
    )  # dumps complete at 583 + 853 k s, the last one <= 28,800 s


@pytest.mark.req("P-007-13")
@pytest.mark.parametrize("n", [1, 2, 3, 5, 8, 16, 40])
def test_the_deterministic_environment_reproduces_the_closed_form_cycle_rate(n):
    cfg = EnvConfig.from_bundle(hand.family_bundle(n), dt_s=1.0)
    env = VectorEnv(cfg, batch=1, seeds=[0], device="cpu")
    res = env.reset()
    while not bool(res.done[0]):
        res = env.step(torch.tensor([0]))
    dumps = float(res.info["tonnes"][0]) / 227.0
    horizon = 8 * H
    rate = min(n / 853.0, 1 / 258.0, 1 / 55.0)
    assert abs(dumps - rate * horizon) <= 2 * n + 2, (
        n,
        dumps,
        rate * horizon,
    )  # P-007-09(b) up to the start-up transient of each truck


@pytest.mark.slow
@pytest.mark.req("P-007-13")
@pytest.mark.parametrize("n", [1, 4, 12])
def test_the_exponential_environment_reproduces_exact_mva(n):
    horizon = 100 * H
    cfg = EnvConfig.from_bundle(hand.family_bundle(n, horizon_s=horizon, profile="exponential"), dt_s=1.0)
    env = VectorEnv(cfg, batch=30, seeds=list(range(30)), device="cpu")
    res = env.reset()
    t_warm, tonnes_warm = 2 * H, torch.full((30,), math.nan, dtype=torch.float64)
    while not bool(res.done.all()):
        past = (res.info["time_s"] >= t_warm) & torch.isnan(tonnes_warm)
        tonnes_warm = torch.where(past, res.info["tonnes"], tonnes_warm)
        res = env.step(torch.zeros(30, dtype=torch.long))
    per_hour = (
        (res.info["tonnes"] - tonnes_warm) / 227.0 / ((horizon - t_warm) / H)
    )  # exponential profile: the payload is its mean, 227 t
    q, x = [0.0, 0.0], 0.0
    for k in range(1, n + 1):  # exact MVA, queues of 258 s and 55 s and a delay of 540 s
        r = [258.0 * (1 + q[0]), 55.0 * (1 + q[1])]
        x = k / (sum(r) + 540.0)
        q = [x * r[0], x * r[1]]
    expected = x * 3600.0
    mean, se = float(per_hour.mean()), float(per_hour.std(unbiased=True)) / math.sqrt(30)
    assert abs(mean - expected) <= max(3 * se, 0.01 * expected), (n, mean, expected, se)


@pytest.mark.req("P-007-13")
@pytest.mark.parametrize("profile", ["engine", "exponential"])
def test_the_trajectory_of_a_copy_is_the_same_for_batch_1_and_batch_64(profile):
    bundle = hand.family_bundle(5, horizon_s=2 * H, profile=profile)
    cfg = EnvConfig.from_bundle(bundle, dt_s=5.0)
    seeds = [1000 + 7 * i for i in range(64)]
    big = VectorEnv(cfg, batch=64, seeds=seeds, device="cpu")
    res = big.reset()
    big_log: list[list[tuple[float, int, float]]] = [[] for _ in range(64)]
    while not bool(res.done.all()):
        for b in range(64):
            if not bool(res.done[b]):
                big_log[b].append(
                    (float(res.info["time_s"][b]), int(res.info["deciding"][b]), float(res.info["tonnes"][b]))
                )
        res = big.step(first_valid(res.obs))
    for b in (0, 17, 63):
        one = VectorEnv(cfg, batch=1, seeds=[seeds[b]], device="cpu")
        r = one.reset()
        log = []
        while not bool(r.done[0]):
            log.append((float(r.info["time_s"][0]), int(r.info["deciding"][0]), float(r.info["tonnes"][0])))
            r = one.step(first_valid(r.obs))
        assert log == big_log[b], b  # identical, bit for bit
        assert float(r.info["tonnes"][0]) == float(res.info["tonnes"][b])


@pytest.mark.req("P-007-13")
@pytest.mark.parametrize("profile", ["engine", "deterministic"])
def test_a_strictly_increasing_relabelling_leaves_the_tonnes_series_unchanged(profile):
    b = hand.family_bundle(6, horizon_s=2 * H, profile=profile)
    twin = copy.deepcopy(b)
    for t in twin["fleet"]:
        t["id"] = 10 * t["id"] + 3
    a_env, b_env = (
        VectorEnv(EnvConfig.from_bundle(x, dt_s=5.0), batch=2, seeds=[5, 6], device="cpu") for x in (b, twin)
    )
    ra, rb = a_env.reset(), b_env.reset()
    while not bool(ra.done.all()):
        assert (
            torch.equal(ra.info["time_s"], rb.info["time_s"])
            and torch.equal(ra.info["tonnes"], rb.info["tonnes"])
            and torch.equal(ra.reward, rb.reward)
        )
        ra, rb = a_env.step(first_valid(ra.obs)), b_env.step(first_valid(rb.obs))
    assert bool(rb.done.all()) and torch.equal(ra.info["tonnes"], rb.info["tonnes"])


@pytest.mark.req("P-007-08")
def test_time_dilation_by_two_doubles_every_time_and_keeps_the_tonnes():
    base = hand.script_bundle(horizon_s=2400.0)
    dil = copy.deepcopy(base)
    for s in dil["network"]["segments"]:
        s["length_m"] *= 2
    dil["horizon_s"] *= 2
    dil["engine_constants"]["dump_mean_s"] *= 2
    a = VectorEnv(EnvConfig.from_bundle(base, dt_s=5.0), batch=1, seeds=[3], device="cpu")
    b = VectorEnv(EnvConfig.from_bundle(dil, dt_s=10.0, dilation=2.0), batch=1, seeds=[3], device="cpu")
    ra, rb = a.reset(), b.reset()
    n = 0
    while not bool(ra.done[0]):
        assert float(rb.info["time_s"][0]) == 2 * float(ra.info["time_s"][0]) and float(rb.info["tonnes"][0]) == float(
            ra.info["tonnes"][0]
        )
        assert int(rb.info["deciding"][0]) == int(ra.info["deciding"][0])
        ra, rb = a.step(torch.tensor([0])), b.step(torch.tensor([0]))
        assert float(rb.reward[0]) == float(ra.reward[0])
        n += 1
    assert bool(rb.done[0]) and n >= 2


@pytest.mark.gpu
@pytest.mark.req("FR-007-23")
def test_the_cuda_environment_follows_the_cpu_trajectory():
    cfg = EnvConfig.from_bundle(hand.family_bundle(5, horizon_s=2 * H, profile="engine"), dt_s=5.0)
    cpu = VectorEnv(cfg, batch=4, seeds=[1, 2, 3, 4], device="cpu")
    gpu = VectorEnv(cfg, batch=4, seeds=[1, 2, 3, 4], device="cuda")
    rc, rg = cpu.reset(), gpu.reset()
    while not bool(rc.done.all()):
        assert torch.allclose(rc.info["time_s"], rg.info["time_s"].cpu()) and torch.allclose(
            rc.reward, rg.reward.cpu(), atol=1e-6
        )
        rc, rg = cpu.step(first_valid(rc.obs)), gpu.step(first_valid(rg.obs).cpu().to("cuda"))
    assert torch.allclose(rc.info["tonnes"], rg.info["tonnes"].cpu())
