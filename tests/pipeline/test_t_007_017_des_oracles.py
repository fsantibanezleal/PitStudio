# ruff: noqa: E501, PT018
"""T-007-017: the exponential MVA oracle family (N_T = 1 ... 12, 30 seeds x 100 h); deterministic-profile monotonicity and closed-form cycle rate; the realistic-profile
gap is reported without a pass flag.

Requirements: FR-007-17, FR-007-18, P-007-09.

Spec: specs/007-haulage-dispatch/spec.md FR-007-17 (the exponential oracle family: one loader, one dump, one two-way route, fast mode, `fixed` dispatcher, `exponential` profile,
N_T = 1 ... 12; the DES fleet throughput (cycles/h), averaged over 30 seeds x 100 h with the first 2 h discarded, lies within max(3 standard errors, 1 %) of exact MVA; MVA treats the
loader and the dump as FCFS stations and the haul and return legs as one delay station whose time is hand-calculated from the segment lengths and speed limits), FR-007-18 (the DES-versus-MVA
throughput gap per N_T under the `engine` profile and traffic mode is reported as a result, never as a pass/fail check), P-007-09 (under the `deterministic` profile, fast mode, `fixed` and a
single route: (a) adding one truck never decreases the tonnes dumped by any time t <= horizon; (b) the fleet cycle rate over [W, H] equals min(N_T / T_c*, mu_L, mu_D) within N_T / (H - W);
T_c*, mu_L and mu_D are hand-calculated from the bundle; N_T = 1 ... 40, H = 8 h, W = 1 h) and section 7 (M1 worked examples).

Oracle: exact mean-value analysis written out in this file (Reiser and Lavenberg recursion: R_k(n) = S_k (1 + Q_k(n - 1)), X(n) = n / (sum R_k + Z), Q_k(n) = X(n) R_k(n)), checked against the
published worked examples of spec 007 section 7 (one queue mu = 15/h plus a 20 min delay: X = 2.50, 7.06, 10.727, 12.12, 13.95 per hour for N = 1, 3, 5, 6, 8); the hand-calculated route (a flat
1,500 m segment at 20 km/h: 1,500 / (20 / 3.6) = 270 s each way, so Z = 540 s), loading (ceil(227 / 45) = 6 passes x 38 s + 30 s = 258 s) and dumping (55 s) of the family; the pinned reference
engine run directly for the trip time of the flat route (`kit.reference_engine_run`).

Expected API (module `pitstudio_pipeline.haulage.oracles`):
    exact_mva(n_trucks: int, queue_service_s: Sequence[float], delay_s: float) -> float        cycles per second of the closed network of FCFS queue stations and one delay station
    exponential_family_bundle(n_trucks: int, *, profile="exponential", horizon_s=360000.0, warmup_s=7200.0) -> dict
        a bundle valid for `validate_bundle`: nodes 1 (face) and 2 (dump), ONE two-way flat segment of 1,500 m (grade 0 %) with speed limit 20 km/h, one SHOVEL_45 loader (1 spot) at node 1,
        dump node 2, `n_trucks` CAT_793F trucks starting at the loader, mode `fast`, dispatcher `fixed`, `kpi_window.warmup_s` = warmup_s, the given horizon; the profile `exponential` carries the exponential
        quantile table, `deterministic` carries none, `engine` carries the normal and lognormal tables (mode `traffic` for `engine`)
    family_delay_s(bundle: dict) -> float                       the delay-station time: sum over the route's segments of length / speed limit, loaded leg plus empty leg (540.0 for the family)
    run_family(n_trucks, seeds, *, workdir, horizon_s=360000.0, warmup_s=7200.0) -> FamilyResult(samples: list[float], mva_cycles_per_h: float)
        runs the family through the adapter once per seed (bundle files under `workdir`); `samples[i]` is the fleet cycles/h of seed i over [warmup, horizon]; `mva_cycles_per_h` is exact_mva with
        the hand-calculated services (258 s, 55 s) and delay, in cycles per hour
    gap_table(n_values, seeds, *, workdir, horizon_s, warmup_s) -> list[dict]
        for each N_T under the `engine` profile and traffic mode: {"n_trucks", "seeds", "des_cycles_per_h" (mean over seeds), "mva_cycles_per_h", "gap_cycles_per_h" = des - mva,
        "gap_pct" = 100 x gap / mva}; no other key, in particular no pass, fail or verdict flag.
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
from pitstudio_pipeline.haulage.adapter import run_shift
from pitstudio_pipeline.haulage.oracles import (
    exact_mva,
    exponential_family_bundle,
    family_delay_s,
    gap_table,
    run_family,
)
from pitstudio_pipeline.haulage.scenario import validate_bundle

LOAD_S, DUMP_S, DELAY_S = 258.0, 55.0, 540.0  # hand calculation (see the module docstring)


def mva(n: int, queues: list[float], z: float) -> float:
    q = [0.0] * len(queues)
    x = 0.0
    for k in range(1, n + 1):
        r = [s * (1 + qi) for s, qi in zip(queues, q, strict=True)]
        x = k / (sum(r) + z)
        q = [x * ri for ri in r]
    return x


# ---------------------------------------------------------------------------------------------------------------------
# the oracle itself
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-17")
@pytest.mark.parametrize(("n", "per_hour"), [(1, 2.50), (3, 7.06), (5, 10.727), (6, 12.12), (8, 13.95)])
def test_exact_mva_reproduces_the_published_worked_examples(n, per_hour):
    # one queue with mu = 15 per hour (240 s) and a 20 min delay (spec 007 section 7)
    assert exact_mva(n, [240.0], 1200.0) * 3600 == pytest.approx(per_hour, abs=0.005)


@pytest.mark.req("FR-007-17")
@pytest.mark.parametrize("n", [1, 2, 5, 12, 40])
def test_exact_mva_equals_the_recursion_written_in_the_test(n):
    assert exact_mva(n, [LOAD_S, DUMP_S], DELAY_S) == pytest.approx(mva(n, [LOAD_S, DUMP_S], DELAY_S), rel=1e-12)


@pytest.mark.req("FR-007-17")
def test_the_family_numbers_by_hand():
    assert exact_mva(1, [LOAD_S, DUMP_S], DELAY_S) * 3600 == pytest.approx(
        3600 / (258 + 55 + 540), rel=1e-12
    )  # a lone truck never waits: 1 / 853 s
    assert exact_mva(2, [LOAD_S, DUMP_S], DELAY_S) * 3600 == pytest.approx(
        7.70398, rel=1e-5
    )  # R_L = 258 (1 + 258/853), R_D = 55 (1 + 55/853), X = 2 / (R_L + R_D + 540)
    assert exact_mva(500, [LOAD_S, DUMP_S], DELAY_S) == pytest.approx(
        1 / LOAD_S, rel=1e-3
    )  # saturation at the slower station


@pytest.mark.req("FR-007-17")
@pytest.mark.parametrize(
    "bad",
    [
        (0, [1.0], 1.0),
        (-1, [1.0], 1.0),
        (2, [], 1.0),
        (2, [0.0], 1.0),
        (2, [-1.0], 1.0),
        (2, [1.0], -1.0),
        (2, [float("nan")], 1.0),
        (2, [1.0], float("inf")),
        (2.5, [1.0], 1.0),
    ],
)
def test_exact_mva_rejects_degenerate_inputs(bad):
    with pytest.raises(ValueError):  # noqa: PT011
        exact_mva(*bad)


# ---------------------------------------------------------------------------------------------------------------------
# the family bundle and the hand-calculated delay
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-17")
@pytest.mark.parametrize("n", [1, 7, 12])
def test_the_family_bundle_is_one_loader_one_dump_one_two_way_route(n):
    b = exponential_family_bundle(n)
    validate_bundle(b)
    assert len(b["network"]["nodes"]) == 2 and len(b["network"]["segments"]) == 1
    s = b["network"]["segments"][0]
    assert (s["one_way"], s["grade_pct"], s["speed_limit_kmh"], s["length_m"]) == (False, 0.0, 20.0, 1500.0)
    assert (
        len(b["loaders"]) == 1
        and b["loaders"][0]["loader_class"] == "SHOVEL_45"
        and b["loaders"][0]["n_spots"] == 1
        and len(b["dumps"]) == 1
    )
    assert (
        len(b["fleet"]) == n
        and {t["truck_class"] for t in b["fleet"]} == {"CAT_793F"}
        and {t["start_loader"] for t in b["fleet"]} == {b["loaders"][0]["node"]}
    )
    assert (b["mode"], b["dispatcher"], b["variate_profile"], b["horizon_s"], b["kpi_window"]) == (
        "fast",
        {"id": "fixed"},
        "exponential",
        360000.0,
        {"warmup_s": 7200.0},
    )
    assert [t["family"] for t in b["quantile_tables"]] == ["exponential"]
    assert family_delay_s(b) == pytest.approx(540.0, rel=1e-12)  # 2 x 1500 m / (20 km/h)


@pytest.mark.req("FR-007-17")
def test_the_family_delay_follows_lengths_and_speed_limits():
    b = exponential_family_bundle(2)
    b["network"]["segments"][0]["length_m"] = 3000.0
    b["network"]["segments"][0]["speed_limit_kmh"] = 36.0
    assert family_delay_s(b) == pytest.approx(2 * 3000.0 / 10.0, rel=1e-12)  # 36 km/h = 10 m/s


@pytest.mark.req("FR-007-17")
def test_the_profiles_carry_the_tables_they_need():
    assert exponential_family_bundle(2, profile="deterministic")["quantile_tables"] == []
    eng = exponential_family_bundle(2, profile="engine")
    assert eng["variate_profile"] == "engine" and eng["mode"] == "traffic"
    assert {t["family"] for t in eng["quantile_tables"]} == {"normal", "lognormal-unit-mean"}


@pytest.mark.req("FR-007-17")
def test_the_reference_engine_trip_time_on_the_flat_route_is_length_over_the_limit(tmp_path):
    b = exponential_family_bundle(1, profile="deterministic", horizon_s=3600.0, warmup_s=0.0)
    ref = kit.reference_engine_run(b)
    rows = {r["event"]: r["t"] for r in ref.events[:4]}
    assert rows["load"] == pytest.approx(30.0) and rows["haul"] == pytest.approx(
        30.0 + 258.0
    )  # stagger midpoint, 6 passes x 38 s + 30 s
    assert rows["dump"] - rows["haul"] == pytest.approx(270.0, abs=1e-6)  # 1,500 m at 20 km/h: the hand-calculated leg
    assert rows["return"] - rows["dump"] == pytest.approx(55.0, abs=1e-6)


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-17: the DES against exact MVA
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.req("FR-007-17")
@pytest.mark.parametrize("n", range(1, 13))
def test_the_des_throughput_is_within_three_standard_errors_or_one_percent_of_exact_mva(tmp_path, n):
    fam = run_family(n, range(30), workdir=tmp_path)  # 30 seeds x 100 h, first 2 h discarded
    xs = fam.samples
    mean, se = statistics.fmean(xs), statistics.stdev(xs) / math.sqrt(len(xs))
    expected = mva(n, [LOAD_S, DUMP_S], DELAY_S) * 3600
    assert fam.mva_cycles_per_h == pytest.approx(expected, rel=1e-9)
    assert len(xs) == 30 and all(x > 0 for x in xs)
    assert abs(mean - expected) <= max(3 * se, 0.01 * expected), (n, mean, expected, se)


# ---------------------------------------------------------------------------------------------------------------------
# P-007-09: deterministic profile
# ---------------------------------------------------------------------------------------------------------------------
H, W = 8 * 3600.0, 3600.0


def det_run(tmp_path, n):
    b = exponential_family_bundle(n, profile="deterministic", horizon_s=H, warmup_s=W)
    return run_shift(kit.write_bundle(tmp_path, b, f"det{n}.json"), seed=0)


def cumulative_tonnes(res):
    tot, out = 0.0, []
    pending = {}
    for r in res.cyclelog:
        if r["event"] == "dump":
            pending[r["truck"]] = r["payload_t"]
        elif r["event"] == "return":
            tot += pending.pop(r["truck"], 0.0)
            out.append((r["t_s"], tot))
    return out


def at(curve, t):
    last = 0.0
    for tt, v in curve:
        if tt <= t:
            last = v
        else:
            break
    return last


@pytest.mark.req("P-007-09")
def test_adding_one_truck_never_decreases_the_tonnes_dumped_by_any_time(tmp_path):
    prev = cumulative_tonnes(det_run(tmp_path, 1))
    for n in range(2, 41):
        cur = cumulative_tonnes(det_run(tmp_path, n))
        for t in sorted({t for t, _ in prev} | {t for t, _ in cur}):
            assert at(cur, t) >= at(prev, t) - 1e-9, (n, t)
        prev = cur


@pytest.mark.req("P-007-09")
@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, 16, 40])
def test_the_deterministic_cycle_rate_is_min_of_the_three_closed_form_rates(tmp_path, n):
    cycle_free = LOAD_S + 270.0 + DUMP_S + 270.0  # T_c* = 853 s (hand calculation)
    rate = min(
        n / cycle_free, 1 / LOAD_S, 1 / DUMP_S
    )  # cycles per second: the truck-limited, loader-limited and dump-limited rates
    res = det_run(tmp_path, n)
    count = sum(1 for r in res.cyclelog if r["event"] == "return" and W <= r["t_s"] <= H)
    assert abs(count - rate * (H - W)) <= n, (n, count, rate * (H - W))


@pytest.mark.req("P-007-09")
def test_the_kpi_throughput_agrees_with_the_cycle_count(tmp_path):
    res = det_run(tmp_path, 3)
    count = sum(1 for r in res.cyclelog if r["event"] == "return" and W <= r["t_s"] <= H)
    assert res.kpis["fleet"]["cycles"] == count and res.kpis["fleet"]["cycles_per_h"] == pytest.approx(
        count / ((H - W) / 3600.0), rel=1e-12
    )


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-18: the gap is a result
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-18")
def test_the_gap_table_reports_numbers_and_never_a_pass_flag(tmp_path):
    rows = gap_table([1, 3], range(3), workdir=tmp_path, horizon_s=20 * 3600.0, warmup_s=3600.0)
    assert [r["n_trucks"] for r in rows] == [1, 3]
    for r in rows:
        assert set(r) == {
            "n_trucks",
            "seeds",
            "des_cycles_per_h",
            "mva_cycles_per_h",
            "gap_cycles_per_h",
            "gap_pct",
        }  # no pass, fail, verdict or tolerance key
        assert r["seeds"] == 3 and r["des_cycles_per_h"] > 0
        assert r["mva_cycles_per_h"] == pytest.approx(mva(r["n_trucks"], [LOAD_S, DUMP_S], DELAY_S) * 3600, rel=1e-9)
        assert r["gap_cycles_per_h"] == pytest.approx(
            r["des_cycles_per_h"] - r["mva_cycles_per_h"], rel=1e-12, abs=1e-12
        )
        assert r["gap_pct"] == pytest.approx(100 * r["gap_cycles_per_h"] / r["mva_cycles_per_h"], rel=1e-12, abs=1e-12)
        assert not any(isinstance(v, bool) for v in r.values())
