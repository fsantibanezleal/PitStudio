# ruff: noqa: E501, PT018
"""T-007-054: the environment fidelity gate against the reference DES in fast mode (<= 3 % for fixed, nearest, SPTF and SQ over 30 seeds); the traffic-mode gap is reported.

Requirements: SC-007-04.

Spec: specs/007-haulage-dispatch/spec.md SC-007-04 (fidelity of the training environment before training is accepted: for `fixed`, `nearest`, `sptf` and `sq`, |mean t/h (environment) - mean t/h (reference DES, fast mode)| <= 3 % of the DES value over
30 seeds; the traffic-mode gap is reported; evidence: the `s30_train` pre-check report) and section 8 item 9 (the vectorised environment has no traffic layer, so its gate is checked against the reference DES in fast mode and the traffic-mode gap is reported).

Oracle: the pinned reference engine `minehaulsim` driven directly by this test (`p007_kit.reference_engine_run`) with a test-side numpy random source (not the project's counter-based source) for the stochastic runs and the engine's `deterministic` stand-in for the
exact ones; throughput = tonnes of completed dumps (the payload recorded at the `dump` event of every truck whose `return` event is at or before the horizon) per hour. Gate logic is exercised with an injected DES runner whose results are scaled
copies of the environment's own result, so the expected relative gap is known by construction (0.0299 passes, 0.0301 fails, 0 passes).

Expected API (module `pitstudio_pipeline.dispatch.fidelity`):
    run_env_baseline(bundle: dict, name: str, seeds: Sequence[int], *, dt_s: float = 10.0, device: str = "cpu") -> list[float]
        t/h of one environment copy per seed (one batch of len(seeds) copies) under the classical rule `name` in {"fixed", "nearest", "sptf", "sq"} (the rules of FR-007-15 written over the environment's state, loaders return to
        the declared destination); t/h = tonnes dumped by the horizon / (horizon_s / 3600). Any other name raises ValueError.
    fidelity_report(bundle: dict, *, seeds: Sequence[int], dispatchers: Sequence[str] = ("fixed", "nearest", "sptf", "sq"), tolerance: float = 0.03, des_runner=None, dt_s: float = 10.0) -> dict
        `des_runner(bundle, dispatcher, mode, seed) -> float` (t/h of one reference-DES run; default: the pinned reference engine through the adapter, `engine` profile or the bundle's own); fewer than 30 seeds, duplicate seeds, a tolerance
        outside (0, 1) or an unknown dispatcher raise ValueError before any run. The report is a JSON-serialisable dict:
            {"n_seeds": int, "tolerance": float, "accepted": bool,
             "fast": {name: {"des_mean_th": float, "env_mean_th": float, "rel_gap": |env - des| / des, "passed": bool}},
             "traffic": {name: {"des_mean_th": float, "env_mean_th": float, "rel_gap": float}}}      (reported only: no pass flag)
        `accepted` is True when every dispatcher passes in fast mode.
    EnvFidelityError(HaulError): `require_fidelity(report) -> None` raises it, naming every failing dispatcher with its gap, when the report is not accepted (s30_train calls it before training).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_busy as busy
import p007_kit as kit
from pitstudio_pipeline.dispatch import fidelity
from pitstudio_pipeline.dispatch.fidelity import EnvFidelityError, fidelity_report, require_fidelity, run_env_baseline

NAMES = ("fixed", "nearest", "sptf", "sq")
H = 4 * 3600.0


class NumpyRng:
    """A test-side random source for the reference engine: one numpy Generator per purpose, seeded from (seed, purpose)."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._streams: dict[str, np.random.Generator] = {}

    def stream(self, purpose: str):
        if purpose not in self._streams:
            self._streams[purpose] = np.random.default_rng([self.seed, *purpose.encode()])
        return self._streams[purpose]

    fresh = stream


def des_th(bundle: dict, rng) -> float:
    """t/h of one reference-engine run: payload of every dump that has returned by the horizon."""
    res = kit.reference_engine_run(bundle, rng)
    horizon = bundle["horizon_s"]
    pending, tonnes = {}, 0.0
    for e in res.events:
        if e["event"] == "dump":
            pending[e["truck_id"]] = e["payload_t"]
        elif e["event"] == "return" and e["t"] <= horizon:
            tonnes += pending.pop(e["truck_id"], 0.0)
    return tonnes / (horizon / 3600.0)


def stochastic_des(bundle, dispatcher, mode, seed):
    b = busy.busy_bundle(dispatcher, mode, n_trucks=5, horizon=H, profile="engine")
    return des_th(b, lambda _s, seed=seed: NumpyRng(seed))


SEEDS = list(range(1000, 1030))


# ---------------------------------------------------------------------------------------------------------------------
# environment against the engine: exact under the deterministic profile (independent oracle)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize("name", NAMES)
def test_under_the_deterministic_profile_the_environment_matches_the_engine_within_three_percent(name):
    b = busy.busy_bundle(name, "fast", n_trucks=6, horizon=H)
    des = des_th(b, kit.DeterministicRng)
    assert des > 100  # a real production figure for six trucks, not an empty run
    got = run_env_baseline(b, name, [1, 2, 3], dt_s=10.0)
    assert len(got) == 3
    for x in got:
        assert abs(x - des) / des <= 0.03, (name, x, des)
    assert len({round(x, 6) for x in got}) == 1  # nothing is random under this profile: the copies agree exactly


@pytest.mark.req("SC-007-04")
@pytest.mark.slow
@pytest.mark.parametrize("name", NAMES)
def test_over_30_seeds_the_mean_throughput_is_within_three_percent_of_the_stochastic_engine(name):
    b = busy.busy_bundle(name, "fast", n_trucks=5, horizon=H, profile="engine")
    des = np.mean([stochastic_des(b, name, "fast", s) for s in SEEDS])
    env = np.mean(run_env_baseline(b, name, SEEDS, dt_s=10.0))
    assert abs(env - des) / des <= 0.03, (name, env, des)


@pytest.mark.req("SC-007-04")
def test_the_environment_baselines_are_deterministic_per_seed_and_independent_of_the_batch():
    b = busy.busy_bundle("fixed", "fast", n_trucks=6, horizon=H, profile="engine")
    a = run_env_baseline(b, "sptf", [7, 8, 9])
    assert a == run_env_baseline(b, "sptf", [7, 8, 9])
    assert (
        run_env_baseline(b, "sptf", [8])[0] == a[1]
    )  # copy independence: the same seed gives the same result in a batch of one
    assert all(x > 0 for x in a)


@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize("bad", ["lp", "ppo", "", "SPTF", None, 3])
def test_unknown_baseline_names_are_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        run_env_baseline(busy.busy_bundle(), bad, [1])


# ---------------------------------------------------------------------------------------------------------------------
# the gate: thresholds, seeds, reporting
# ---------------------------------------------------------------------------------------------------------------------
def scaled_runner(factor_for):
    """A fake DES runner whose t/h is `env_th / factor` for a per-(dispatcher, mode) factor computed from the environment itself (so the relative gap is known)."""
    cache: dict[tuple, float] = {}

    def run(bundle, dispatcher, mode, seed):
        key = (dispatcher, seed)
        if key not in cache:
            cache[key] = run_env_baseline(bundle, dispatcher, [seed])[0]
        return cache[key] / factor_for(dispatcher, mode)

    return run


def bundle():
    return busy.busy_bundle("fixed", "fast", n_trucks=4, horizon=3600.0, profile="engine")


SMALL_SEEDS = list(range(500, 530))


@pytest.mark.req("SC-007-04")
def test_the_report_has_the_documented_shape_and_is_json_serialisable():
    r = fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=scaled_runner(lambda d, m: 1.0))
    json.dumps(r)
    assert r["n_seeds"] == 30 and r["tolerance"] == 0.03 and r["accepted"] is True
    assert set(r["fast"]) == set(NAMES) and set(r["traffic"]) == set(NAMES)
    for name in NAMES:
        f = r["fast"][name]
        assert set(f) == {"des_mean_th", "env_mean_th", "rel_gap", "passed"} and f["passed"] is True
        assert f["rel_gap"] == pytest.approx(0.0, abs=1e-12) and f["env_mean_th"] == pytest.approx(f["des_mean_th"])
        t = r["traffic"][name]
        assert set(t) == {"des_mean_th", "env_mean_th", "rel_gap"}  # reported, never gated


@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize(("gap", "ok"), [(0.0299, True), (0.0301, False), (0.0, True), (0.10, False)])
def test_the_three_percent_threshold_decides_per_dispatcher_and_for_the_whole_run(gap, ok):
    # des = env / (1 - gap) gives |env - des| / des = ... use des = env / (1 + gap): |env - des| / des = gap exactly
    runner = scaled_runner(lambda d, m: 1.0 + gap if (d == "sptf" and m == "fast") else 1.0)
    r = fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=runner)
    assert r["fast"]["sptf"]["passed"] is ok
    assert r["fast"]["sptf"]["rel_gap"] == pytest.approx(gap, abs=1e-9)
    assert all(r["fast"][n]["passed"] for n in ("fixed", "nearest", "sq"))
    assert r["accepted"] is ok


@pytest.mark.req("SC-007-04")
def test_the_traffic_gap_is_reported_but_never_fails_the_gate():
    runner = scaled_runner(lambda d, m: 1.2 if m == "traffic" else 1.0)  # a 20 % traffic-mode gap
    r = fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=runner)
    assert r["accepted"] is True
    for name in NAMES:
        assert r["traffic"][name]["rel_gap"] == pytest.approx(0.2, abs=1e-9)  # |env - des| / des with des = env / 1.2


@pytest.mark.req("SC-007-04")
def test_the_runner_is_called_for_every_dispatcher_mode_and_seed():
    calls = []

    def runner(b, d, m, s):
        calls.append((d, m, s))
        return 1000.0

    fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=runner)
    assert len(calls) == len(set(calls)) == 4 * 2 * 30
    assert {c[1] for c in calls} == {"fast", "traffic"} and {c[2] for c in calls} == set(SMALL_SEEDS)


@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize("n", [0, 1, 29])
def test_fewer_than_30_seeds_are_rejected_before_any_run(n):
    calls = []
    with pytest.raises(ValueError, match="30"):
        fidelity_report(bundle(), seeds=SMALL_SEEDS[:n], des_runner=lambda *a: calls.append(a) or 1.0)
    assert calls == []


@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize(
    "kw",
    [
        {"seeds": [*range(29), 0]},  # duplicate seed: 30 entries, 29 distinct
        {"tolerance": 0.0},
        {"tolerance": 1.0},
        {"tolerance": -0.03},
        {"tolerance": float("nan")},
        {"dispatchers": ("fixed", "lp")},
        {"dispatchers": ()},
        {"dispatchers": ("fixed", "fixed")},
    ],
)
def test_hostile_gate_arguments_are_rejected_before_any_run(kw):
    calls = []
    args = {"seeds": SMALL_SEEDS, "des_runner": lambda *a: calls.append(a) or 1.0, **kw}
    with pytest.raises(ValueError):  # noqa: PT011
        fidelity_report(bundle(), **args)
    assert calls == []


@pytest.mark.req("SC-007-04")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -5.0])
def test_a_non_finite_or_non_positive_des_throughput_is_an_error_not_a_pass(bad):
    with pytest.raises((ValueError, ZeroDivisionError)):
        fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=lambda *a: bad)


@pytest.mark.req("SC-007-04")
def test_require_fidelity_passes_an_accepted_report_and_names_every_failing_dispatcher():
    ok = fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=scaled_runner(lambda d, m: 1.0))
    require_fidelity(ok)  # no exception
    runner = scaled_runner(lambda d, m: 1.2 if (m == "fast" and d in {"nearest", "sq"}) else 1.0)
    bad = fidelity_report(bundle(), seeds=SMALL_SEEDS, des_runner=runner)
    with pytest.raises(EnvFidelityError) as ei:
        require_fidelity(bad)
    msg = str(ei.value)
    assert "nearest" in msg and "sq" in msg and "fixed" not in msg and "sptf" not in msg
    assert "0.2" in msg or "20" in msg  # the gap is quoted


@pytest.mark.req("SC-007-04")
def test_require_fidelity_rejects_malformed_reports():
    for bad in [{}, {"accepted": "yes"}, None, [], {"accepted": False, "fast": {}}]:
        with pytest.raises((EnvFidelityError, ValueError, TypeError, KeyError)):
            require_fidelity(bad)


@pytest.mark.req("SC-007-04")
def test_the_default_des_is_the_pinned_reference_engine_through_the_adapter():
    """No injected runner: the module drives the reference engine itself; under the deterministic profile its DES throughput equals the engine run made here (a one-dump edge definition may differ by under 1 %)."""
    b = busy.busy_bundle("fixed", "fast", n_trucks=6, horizon=H)
    r = fidelity_report(b, seeds=SMALL_SEEDS, dt_s=10.0)
    for n in NAMES:
        oracle = des_th(busy.busy_bundle(n, "fast", n_trucks=6, horizon=H), kit.DeterministicRng)
        f = r["fast"][n]
        assert f["des_mean_th"] == pytest.approx(oracle, rel=0.01), n
        assert f["rel_gap"] == pytest.approx(abs(f["env_mean_th"] - f["des_mean_th"]) / f["des_mean_th"], abs=1e-12)
        oracle_t = des_th(busy.busy_bundle(n, "traffic", n_trucks=6, horizon=H), kit.DeterministicRng)
        assert r["traffic"][n]["des_mean_th"] == pytest.approx(oracle_t, rel=0.01), n
    assert hasattr(fidelity, "run_env_baseline")
