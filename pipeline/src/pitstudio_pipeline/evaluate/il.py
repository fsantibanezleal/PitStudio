# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""s50_evaluate for the IL policies (FR-014-32 to FR-014-39, FR-014-24, FR-014-48, SC-014-01 to SC-014-09).

Episode tables are documents ``{"meta": <il-episodes sidecar>, "rows": [<episode rows>]}`` (``contracts/il-episodes.schema.json``).
Every statistic here is computed from the rows and nothing else; the decision rules are fixed by the specification:

* rates carry a Wilson 95 % interval, continuous paired differences a Student-t interval of the mean difference;
* a binary comparison is decided on the discordant episodes only, by the exact Clopper-Pearson interval of b / (b + c)
  ("better" needs its lower bound above 0.5);
* the sim-to-sim gaps are differences with their paired intervals and are never tested for superiority;
* a table that fails a check (``check_pair``) gives "incomplete evaluation" naming the check, never a verdict;
* a fixture input marks every report ``fixture: true`` and withholds the sim-to-sim gaps.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator

from pitstudio.robots.fixture import is_publishable
from pitstudio.robots.stall import is_stalled
from pitstudio_pipeline._contracts import _registry, schema_path

__all__ = [
    "ACCEPTANCE_THRESHOLDS",
    "PairedInterval",
    "acceptance_table_il1",
    "acceptance_table_il2",
    "check_pair",
    "check_table",
    "dig_episode_metrics",
    "evaluate_il1",
    "evaluate_il2",
    "evaluate_il3",
    "fee_mpm_gap",
    "il1_summary",
    "il2_summary",
    "is_publishable",
    "load_table",
    "paired_t_interval",
    "sim_to_sim_gap_il1",
    "verdicts_il1",
    "verdicts_il2",
    "wilson_interval",
]

TTC_CLIP = 30.0
TTC_SAFE = 3.0
KF_FILLED = 0.8
LIFT_OFF_M = 0.5
TIME_LIMIT_S = 30.0
MIN_EPISODES = 100
MIN_MPM = 16
LABEL = "sim-to-sim gap"
INCOMPLETE = "incomplete evaluation"
ACCEPTANCE_THRESHOLDS = {"SC-014-01": 0.95, "SC-014-02": 0.5, "SC-014-03": 0.99, "SC-014-06": 0.80, "SC-014-07": 0.05}

_IL1_FLOATS = (
    "sum_sq_lateral_error_m2", "rms_lateral_error_m", "max_lateral_error_m", "min_ttc_s", "energy_kwh_per_t_km",
    "frac_within_v_lim",
)  # fmt: skip
_DIG_FLOATS = ("fill_factor", "cycle_time_s", "productivity_per_s")
_ROW_DEF = {"il1-episode": "il1_episode", "dig-episode": "dig_episode"}


# ------------------------------------------------------------------------------------------------- statistics
def _is_int(value: Any) -> bool:
    return isinstance(value, int | np.integer) and not isinstance(value, bool)


def _confidence(confidence: float) -> float:
    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be a number in (0, 1), got {confidence!r}")
    return float(confidence)


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval of k successes in n trials."""
    from scipy.stats import norm

    if not _is_int(n) or n < 1:
        raise ValueError(f"n must be an integer >= 1, got {n!r}")
    if not _is_int(k) or not 0 <= k <= n:
        raise ValueError(f"k must be an integer in [0, n], got {k!r}")
    z = float(norm.ppf(0.5 + _confidence(confidence) / 2.0))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    lo = 0.0 if k == 0 else min(max(0.0, centre - half), p)
    hi = 1.0 if k == n else max(min(1.0, centre + half), p)
    return lo, hi


@dataclass(frozen=True)
class PairedInterval:
    mean: float
    lo: float
    hi: float
    n: int


def _finite_vector(name: str, values: Sequence[float]) -> np.ndarray:
    try:
        arr = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if arr.ndim != 1 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be a 1-D array of finite values")
    return arr


def paired_t_interval(a: Sequence[float], b: Sequence[float], confidence: float = 0.95) -> PairedInterval:
    """Student-t interval of the mean of (a - b) over n - 1 degrees of freedom."""
    from scipy.stats import t

    xa, xb = _finite_vector("a", a), _finite_vector("b", b)
    if xa.shape != xb.shape:
        raise ValueError(f"b has {xb.shape[0]} values, a has {xa.shape[0]}: the pairs must match")
    n = int(xa.shape[0])
    if n < 2:
        raise ValueError(f"a holds {n} pairs, an interval needs at least 2")
    d = xa - xb
    mean = float(np.mean(d))
    half = float(t.ppf(0.5 + _confidence(confidence) / 2.0, n - 1)) * float(np.std(d, ddof=1)) / math.sqrt(n)
    return PairedInterval(mean, mean - half, mean + half, n)


def _clopper_pearson(b: int, c: int, confidence: float) -> tuple[float, float]:
    from scipy.stats import binomtest

    ci = binomtest(b, b + c).proportion_ci(confidence_level=confidence, method="exact")
    return float(ci.low), float(ci.high)


# ------------------------------------------------------------------------------------------------- table checks
def _fixture_mark(*docs: Mapping[str, Any] | None) -> bool:
    return any(isinstance(d, Mapping) and d.get("fixture") is True for d in docs)


def _validator(definition: str | None) -> Draft202012Validator:
    schema = json.loads(schema_path("il-episodes.schema.json").read_text(encoding="utf-8"))
    ref = schema["$id"] + (f"#/$defs/{definition}" if definition else "")
    return Draft202012Validator({"$ref": ref}, registry=_registry())


def _schema_failure(table: Mapping[str, Any]) -> bool:
    meta, rows = table.get("meta"), table.get("rows")
    if not isinstance(meta, Mapping) or not isinstance(rows, list):
        return True
    if next(iter(_validator(None).iter_errors(dict(meta))), None) is not None:
        return True
    definition = _ROW_DEF.get(meta.get("column_set"))
    if definition is None or meta["table"]["rows"] != len(rows):
        return True
    row_validator = _validator(definition)
    return any(not isinstance(r, Mapping) or next(row_validator.iter_errors(dict(r)), None) is not None for r in rows)


def _seed_digest(seeds: Sequence[int]) -> str:
    return hashlib.sha256(json.dumps(sorted(seeds), separators=(",", ":")).encode("utf-8")).hexdigest()


def _seeds(table: Mapping[str, Any]) -> list[int]:
    return [int(r["seed"]) for r in table["rows"]]


def _has_nan(table: Mapping[str, Any]) -> bool:
    columns = _IL1_FLOATS if table["meta"]["column_set"] == "il1-episode" else _DIG_FLOATS
    return any(math.isnan(float(r[c])) for r in table["rows"] for c in columns)


def check_table(table: Mapping[str, Any], *, acceptance: bool = True) -> str | None:
    """The first failing single-table check: schema, seed_set_sha256, duplicate_seed, nan_metric, fewer_than_100."""
    if _schema_failure(table):
        return "schema"
    seeds = _seeds(table)
    if table["meta"]["seed_set_sha256"] != _seed_digest(seeds):
        return "seed_set_sha256"
    if len(set(seeds)) != len(seeds):
        return "duplicate_seed"
    if _has_nan(table):
        return "nan_metric"
    if acceptance and len(seeds) < MIN_EPISODES:
        return "fewer_than_100"
    return None


def _range(block: Mapping[str, Any] | None) -> set[int] | None:
    if not isinstance(block, Mapping):
        return None
    return set(range(int(block["start"]), int(block["start"]) + int(block["count"])))


def check_pair(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    seeds: Mapping[str, Any] | None = None,
    acceptance: bool = True,
) -> str | None:
    """The first failing check of a paired comparison (the order of this list), or None."""
    tables = (policy, baseline)
    failures = {check_table(table, acceptance=False) for table in tables} - {None}
    for name in ("schema", "seed_set_sha256", "duplicate_seed", "nan_metric"):
        if name in failures:
            return name
    if acceptance and any(len(t["rows"]) < MIN_EPISODES for t in tables):
        return "fewer_than_100"
    if set(_seeds(policy)) != set(_seeds(baseline)):
        return "seed_sets_differ"
    if seeds is not None:
        used = set(_seeds(policy))
        reserved = set()
        for key in ("train", "tune"):
            reserved |= _range(seeds.get(key)) or set()
        if used & reserved:
            return "seeds_overlap_training"
        if _range(seeds.get("eval")) != used:
            return "seeds_not_evaluation_range"
    return None


def _by_seed(table: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return sorted(table["rows"], key=lambda r: r["seed"])


def _column(table: Mapping[str, Any], name: str, *, clip: float | None = None) -> np.ndarray:
    values = np.array([float(r[name]) for r in _by_seed(table)])
    return np.minimum(values, clip) if clip is not None else values


def _flags(table: Mapping[str, Any], name: str) -> np.ndarray:
    return np.array([bool(r[name]) for r in _by_seed(table)])


# ------------------------------------------------------------------------------------------------- summaries
def il1_summary(table: Mapping[str, Any]) -> dict[str, Any]:
    rows = table["rows"]
    n = len(rows)
    k = sum(bool(r["success"]) for r in rows)
    steps = sum(int(r["steps"]) for r in rows)
    sum_sq = sum(float(r["sum_sq_lateral_error_m2"]) for r in rows)
    ttc = np.array([float(r["min_ttc_s"]) for r in rows])
    return {
        "n": n,
        "success_rate": k / n,
        "success_wilson": wilson_interval(k, n),
        "collision_rate": sum(bool(r["collision"]) for r in rows) / n,
        "pooled_rms_lateral_error_m": math.sqrt(sum_sq / steps),
        "fraction_min_ttc_ge_3s": float(np.mean(ttc >= TTC_SAFE)),
        "min_ttc_mean_clipped_s": float(np.mean(np.minimum(ttc, TTC_CLIP))),
        "energy_mean_kwh_per_t_km": float(np.mean([float(r["energy_kwh_per_t_km"]) for r in rows])),
        "frac_within_v_lim_mean": float(np.mean([float(r["frac_within_v_lim"]) for r in rows])),
    }


def il2_summary(table: Mapping[str, Any]) -> dict[str, Any]:
    rows = table["rows"]
    n = len(rows)
    filled = sum(float(r["fill_factor"]) >= KF_FILLED for r in rows)
    stalled = sum(bool(r["stalled"]) for r in rows)
    return {
        "n": n,
        "kf_mean": float(np.mean([float(r["fill_factor"]) for r in rows])),
        "cycle_time_mean_s": float(np.mean([float(r["cycle_time_s"]) for r in rows])),
        "productivity_mean_per_s": float(np.mean([float(r["productivity_per_s"]) for r in rows])),
        "lift_off_rate": sum(bool(r["lift_off"]) for r in rows) / n,
        "fraction_kf_ge_0_8": filled / n,
        "fraction_kf_ge_0_8_wilson": wilson_interval(filled, n),
        "fraction_stalled": stalled / n,
        "fraction_stalled_wilson": wilson_interval(stalled, n),
    }


def dig_episode_metrics(
    *,
    dt: float,
    fill: Sequence[float],
    lift_height: Sequence[float],
    cutting: Sequence[bool],
    torque: Any,
    tau_max: Sequence[float],
    time_limit: float = TIME_LIMIT_S,
) -> dict[str, Any]:
    """Per-episode dig metrics from a trace; sample k is the state after step k, at time (k + 1) dt."""
    if isinstance(dt, bool) or not isinstance(dt, int | float) or not math.isfinite(dt) or dt <= 0:
        raise ValueError(f"dt must be a finite number > 0, got {dt!r}")
    kf = _finite_vector("fill", fill)
    lift = _finite_vector("lift_height", lift_height)
    cut = np.asarray(cutting, dtype=bool)
    if lift.shape != kf.shape:
        raise ValueError("fill and lift_height must have the same length")
    if cut.shape != kf.shape:
        raise ValueError("cutting and fill must have the same length")
    tau = np.asarray(torque, dtype=np.float64)
    limit = np.asarray(tau_max, dtype=np.float64)
    if tau.ndim != 2 or tau.shape[0] != kf.shape[0]:
        raise ValueError("torque must be a (T, J) array with T matching fill")
    if limit.ndim != 1 or limit.shape[0] != tau.shape[1]:
        raise ValueError("torque and tau_max must agree on the number of joints")
    if not np.all(np.isfinite(tau)):
        raise ValueError("torque holds a non-finite value")
    if not np.all(np.isfinite(limit)) or np.any(limit <= 0):
        raise ValueError("tau_max must be finite and > 0")
    first_cut = int(np.argmax(cut)) if cut.any() else None
    done = None
    if first_cut is not None:
        after = np.flatnonzero(lift[first_cut + 1 :] >= LIFT_OFF_M)
        done = first_cut + 1 + int(after[0]) if after.size else None
    if done is None:
        last = kf.shape[0] - 1
        cycle, fill_at, termination = float(time_limit), float(kf[last]), "time_limit"
        window = tau
    else:
        cycle, fill_at, termination = (done + 1) * dt, float(kf[done]), "completed"
        window = tau[: done + 1]
    return {
        "termination": termination,
        "fill_factor": fill_at,
        "cycle_time_s": cycle,
        "productivity_per_s": fill_at / cycle,
        "stalled": bool(is_stalled(window, limit, dt)),
        "lift_off": done is not None,
    }


# ------------------------------------------------------------------------------------------------- verdicts
def _verdict(lo: float | None, hi: float | None, boundary: float) -> str:
    if lo is not None and hi is not None:
        if lo > boundary:
            return "better"
        if hi < boundary:
            return "worse"
    return "no significant difference"


def _continuous(diff_a: np.ndarray, diff_b: np.ndarray, confidence: float) -> dict[str, Any]:
    r = paired_t_interval(diff_a, diff_b, confidence)
    return {
        "kind": "continuous", "verdict": _verdict(r.lo, r.hi, 0.0), "mean_difference": r.mean, "ci": (r.lo, r.hi), "n": r.n,
    }  # fmt: skip


def _binary(policy_ok: np.ndarray, baseline_ok: np.ndarray, confidence: float) -> dict[str, Any]:
    b = int(np.sum(policy_ok & ~baseline_ok))
    c = int(np.sum(~policy_ok & baseline_ok))
    ci = _clopper_pearson(b, c, confidence) if b + c > 0 else None
    verdict = _verdict(ci[0], ci[1], 0.5) if ci else "no significant difference"
    return {"kind": "binary", "verdict": verdict, "b": b, "c": c, "ci": ci}


def _require_pair(policy: Mapping[str, Any], baseline: Mapping[str, Any], column_set: str) -> None:
    failed = check_pair(policy, baseline)
    if failed is not None:
        raise ValueError(f"the pair fails the check {failed}: no verdict (fewer_than_100 means under 100 episodes)")
    for name, table in (("policy", policy), ("baseline", baseline)):
        if table["meta"]["column_set"] != column_set:
            raise ValueError(f"{name} must be a {column_set} table")


def verdicts_il1(policy: Mapping[str, Any], baseline: Mapping[str, Any], *, confidence: float = 0.95) -> dict[str, Any]:
    """Per-metric verdicts of the IL-1 policy against its baseline; differences are oriented policy-better positive."""
    conf = _confidence(confidence)
    _require_pair(policy, baseline, "il1-episode")
    return {
        "rms_lateral_error": _continuous(
            _column(baseline, "rms_lateral_error_m"), _column(policy, "rms_lateral_error_m"), conf
        ),
        "min_ttc": _continuous(
            _column(policy, "min_ttc_s", clip=TTC_CLIP), _column(baseline, "min_ttc_s", clip=TTC_CLIP), conf
        ),
        "energy": _continuous(_column(baseline, "energy_kwh_per_t_km"), _column(policy, "energy_kwh_per_t_km"), conf),
        "success": _binary(_flags(policy, "success"), _flags(baseline, "success"), conf),
    }


def verdicts_il2(policy: Mapping[str, Any], baseline: Mapping[str, Any], *, confidence: float = 0.95) -> dict[str, Any]:
    """Per-metric verdicts of an IL-2 or IL-3 policy: productivity P = k_f / t_c and the k_f >= 0.8 rate."""
    conf = _confidence(confidence)
    _require_pair(policy, baseline, "dig-episode")
    return {
        "productivity": _continuous(
            _column(policy, "productivity_per_s"), _column(baseline, "productivity_per_s"), conf
        ),
        "fill_ge_0_8": _binary(
            _column(policy, "fill_factor") >= KF_FILLED, _column(baseline, "fill_factor") >= KF_FILLED, conf
        ),
    }


# ------------------------------------------------------------------------------------------------- gaps
def _gap_stub(status: str, **extra: Any) -> dict[str, Any]:
    return {"label": LABEL, "status": status, **extra}


def sim_to_sim_gap_il1(policy: Mapping[str, Any], twin: Mapping[str, Any]) -> dict[str, Any]:
    """Delta = twin - Isaac Lab per episode for success, RMS lateral error and clipped minimum TTC; never tested."""
    failed = check_pair(policy, twin, acceptance=False)
    if failed is None and len(policy["rows"]) < 2:
        failed = "fewer_than_2"
    if failed is not None:
        return _gap_stub(INCOMPLETE, failed_check=failed)
    if _fixture_mark(policy, twin):
        return _gap_stub("fixture", reason="a contract fixture was an input: no sim-to-sim gap is published from it")

    def gap(column: str, *, clip: float | None = None, as_flag: bool = False) -> dict[str, Any]:
        if as_flag:
            a, b = _flags(twin, column).astype(float), _flags(policy, column).astype(float)
        else:
            a, b = _column(twin, column, clip=clip), _column(policy, column, clip=clip)
        r = paired_t_interval(a, b)
        return {"mean_difference": r.mean, "ci": (r.lo, r.hi)}

    return _gap_stub(
        "complete",
        n=len(policy["rows"]),
        success=gap("success", as_flag=True),
        rms_lateral_error=gap("rms_lateral_error_m"),
        min_ttc=gap("min_ttc_s", clip=TTC_CLIP),
    )


def fee_mpm_gap(fee: Mapping[str, Any], mpm: Mapping[str, Any] | None) -> dict[str, Any]:
    """Mean of k_f,MPM - k_f,FEE over the n paired MPM episodes (16 to 64) with the interval mean +- t s / sqrt(n)."""
    if mpm is None:
        return _gap_stub("not run", reason="no MPM episode table: IL-2b was not run")
    if len(mpm.get("rows", [])) < MIN_MPM:
        return _gap_stub("not run", reason=f"fewer than {MIN_MPM} MPM episodes completed ({len(mpm.get('rows', []))})")
    for table in (fee, mpm):
        failed = check_table(table, acceptance=False)
        if failed is not None:
            return _gap_stub(INCOMPLETE, failed_check=failed)
    fee_seeds = sorted(_seeds(fee))
    mpm_seeds = sorted(_seeds(mpm))
    if fee_seeds[: len(mpm_seeds)] != mpm_seeds:
        return _gap_stub(INCOMPLETE, failed_check="mpm_seeds_not_first_n")
    if _fixture_mark(fee, mpm):
        return _gap_stub("fixture", reason="a contract fixture was an input: no sim-to-sim gap is published from it")
    fee_kf = {int(r["seed"]): float(r["fill_factor"]) for r in fee["rows"]}
    delta = np.array([float(r["fill_factor"]) - fee_kf[int(r["seed"])] for r in _by_seed(mpm)])
    r = paired_t_interval(delta, np.zeros_like(delta))
    return _gap_stub("complete", n=r.n, mean_difference=r.mean, ci=(r.lo, r.hi))


# ------------------------------------------------------------------------------------------------- reports
def _incomplete(failed: str, fixture: bool) -> dict[str, Any]:
    return {"status": INCOMPLETE, "failed_check": failed, "fixture": fixture}


def _policy_of(table: Mapping[str, Any]) -> str:
    return str(table["meta"]["policy"]) if isinstance(table.get("meta"), Mapping) else ""


def evaluate_il1(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    seeds: Mapping[str, Any],
    twin: Mapping[str, Any] | None = None,
    fixture: bool | None = None,
) -> dict[str, Any]:
    """The IL-1 report: both summaries, the per-metric verdicts and (real input only) the sim-to-sim gap."""
    is_fixture = fixture is True or _fixture_mark(policy, baseline, twin)
    failed = check_pair(policy, baseline, seeds=seeds)
    if failed is not None:
        return _incomplete(failed, is_fixture)
    if _policy_of(policy) != "IL-1":
        raise ValueError("policy must be an IL-1 table")
    report: dict[str, Any] = {
        "status": "complete", "failed_check": None, "fixture": is_fixture,
        "policy": il1_summary(policy), "baseline": il1_summary(baseline), "verdicts": verdicts_il1(policy, baseline),
    }  # fmt: skip
    if twin is not None and not is_fixture:
        report["sim_to_sim"] = sim_to_sim_gap_il1(policy, twin)
    return report


def evaluate_il2(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    seeds: Mapping[str, Any],
    mpm: Mapping[str, Any] | None = None,
    il3: Any = None,
    fixture: bool | None = None,
) -> dict[str, Any]:
    """The IL-2 (and, with IL-3 tables, IL-3) report: summaries, verdicts and (real input only) the FEE to MPM gap."""
    is_fixture = fixture is True or _fixture_mark(policy, baseline, mpm)
    failed = check_pair(policy, baseline, seeds=seeds)
    if failed is not None:
        return _incomplete(failed, is_fixture)
    if _policy_of(policy) not in ("IL-2", "IL-3"):
        raise ValueError("policy must be an IL-2 or IL-3 table")
    report: dict[str, Any] = {
        "status": "complete", "failed_check": None, "fixture": is_fixture,
        "policy": il2_summary(policy), "baseline": il2_summary(baseline), "verdicts": verdicts_il2(policy, baseline),
    }  # fmt: skip
    if mpm is not None and not is_fixture:
        report["fee_mpm_gap"] = fee_mpm_gap(policy, mpm)
    if il3 is not None:
        report["il3"] = il3
    return report


def evaluate_il3(
    policy: Mapping[str, Any] | None,
    baseline: Mapping[str, Any] | None,
    *,
    seeds: Mapping[str, Any],
    mpm: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The optional loader: the IL-2 protocol on IL-3 tables, or "not run" when it was not trained."""
    if mpm is not None:
        raise ValueError("mpm must be None: IL-3 has no MPM tier")
    if policy is None and baseline is None:
        return {"status": "not run", "policy_id": "IL-3", "reason": "IL-3 was not trained (optional loader policy)"}
    if policy is None:
        raise ValueError("policy is missing while baseline is given")
    if baseline is None:
        raise ValueError("baseline is missing while policy is given")
    for name, table in (("policy", policy), ("baseline", baseline)):
        if _policy_of(table) != "IL-3":
            raise ValueError(f"{name} must be an IL-3 table, got {_policy_of(table) or 'no policy'}")
    report = evaluate_il2(policy, baseline, seeds=seeds)
    report["policy_id"] = "IL-3"
    return report


# ------------------------------------------------------------------------------------------------- acceptance
def _rate_row(rid: str, metric: str, k: int, n: int, comparison: str) -> dict[str, Any]:
    observed = k / n
    threshold = ACCEPTANCE_THRESHOLDS[rid]
    met = observed >= threshold if comparison == ">=" else observed <= threshold
    return {
        "id": rid, "metric": metric, "observed": observed, "threshold": threshold, "comparison": comparison,
        "met": bool(met), "interval": wilson_interval(k, n),
    }  # fmt: skip


def _gap_row(rid: str, metric: str, gap: Mapping[str, Any] | None, interval: Any) -> dict[str, Any]:
    state = "missing" if gap is None else str(gap["status"])
    reported = gap is not None and gap["status"] == "complete"
    return {
        "id": rid,
        "metric": metric,
        "reported": reported,
        "state": state,
        "interval": interval if reported else None,
    }


def _require_policy(table: Mapping[str, Any], allowed: tuple[str, ...]) -> None:
    if _policy_of(table) not in allowed:
        raise ValueError(f"the table policy must be one of {allowed}, got {_policy_of(table) or 'none'} (column_set)")


def acceptance_table_il1(table: Mapping[str, Any], *, gap: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Observed rates against the pre-registered thresholds (intervals alongside, never used to decide)."""
    _require_policy(table, ("IL-1",))
    marked = _fixture_mark(table)
    failed = check_table(table)
    if failed is not None:
        return _incomplete(failed, marked)
    s = il1_summary(table)
    n = s["n"]
    successes = sum(bool(r["success"]) for r in table["rows"])
    safe = sum(float(r["min_ttc_s"]) >= TTC_SAFE for r in table["rows"])
    rms = s["pooled_rms_lateral_error_m"]
    rms_row = {
        "id": "SC-014-02", "metric": "pooled RMS lateral error (m)", "observed": rms,
        "threshold": ACCEPTANCE_THRESHOLDS["SC-014-02"], "comparison": "<=",
        "met": bool(rms <= ACCEPTANCE_THRESHOLDS["SC-014-02"]), "interval": None,
    }  # fmt: skip
    interval = gap["rms_lateral_error"]["ci"] if gap is not None and gap.get("status") == "complete" else None
    rows = [
        _rate_row("SC-014-01", "route success rate", successes, n, ">="),
        rms_row,
        _rate_row("SC-014-03", "episodes with minimum TTC >= 3 s", safe, n, ">="),
        _gap_row("SC-014-05", "IL-1 sim-to-sim gap (RMS lateral error)", gap, interval),
    ]
    return {"status": "complete", "failed_check": None, "fixture": marked, "rows": rows}


def acceptance_table_il2(table: Mapping[str, Any], *, mpm_gap: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """SC-014-06, SC-014-07 and the FEE to MPM row of an IL-2 or IL-3 table."""
    _require_policy(table, ("IL-2", "IL-3"))
    marked = _fixture_mark(table)
    failed = check_table(table)
    if failed is not None:
        return _incomplete(failed, marked)
    n = len(table["rows"])
    filled = sum(float(r["fill_factor"]) >= KF_FILLED for r in table["rows"])
    stalled = sum(bool(r["stalled"]) for r in table["rows"])
    interval = mpm_gap.get("ci") if mpm_gap is not None else None
    rows = [
        _rate_row("SC-014-06", "episodes with fill factor >= 0.8", filled, n, ">="),
        _rate_row("SC-014-07", "stalled episodes", stalled, n, "<="),
        _gap_row("SC-014-08", "FEE to MPM fill gap", mpm_gap, interval),
    ]
    return {"status": "complete", "failed_check": None, "fixture": marked, "rows": rows}


# ------------------------------------------------------------------------------------------------- tables on disk
def load_table(sidecar_path: Path | str, root: Path | str) -> dict[str, Any]:
    """Read a sidecar and its Parquet table; checks the digest, the row count and the required columns."""
    import pyarrow.parquet as pq

    sidecar = Path(sidecar_path)
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"sidecar file {sidecar.name} was not found") from exc
    except (OSError, ValueError) as exc:
        raise ValueError(f"sidecar {sidecar.name} is not readable JSON") from exc
    errors = list(_validator(None).iter_errors(meta)) if isinstance(meta, dict) else None
    if errors is None or errors:
        pointer = "".join(f"/{p}" for p in errors[0].absolute_path) if errors else "/"
        raise ValueError(
            f"sidecar {sidecar.name} is not a valid episode sidecar at {pointer or '/'} (table path or schema)"
        )
    spec = meta["table"]
    base = Path(root).resolve()
    path = (base / PurePosixPath(spec["path"])).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError(f"table path {spec['path']} is missing or outside the run folder")
    if hashlib.sha256(path.read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError(f"table {spec['path']} does not match its sha256")
    table = pq.read_table(path)
    if table.num_rows != spec["rows"]:
        raise ValueError(f"table {spec['path']} has {table.num_rows} rows, the sidecar says {spec['rows']} (rows)")
    schema = json.loads(schema_path("il-episodes.schema.json").read_text(encoding="utf-8"))
    for column in schema["$defs"][_ROW_DEF[meta["column_set"]]]["required"]:
        if column not in table.column_names:
            raise ValueError(f"table {spec['path']} lacks the column {column}")
    return {"meta": meta, "rows": table.to_pylist()}
