# ruff: noqa: E501
"""Analytical oracles of the haulage reference engine (FR-007-17, FR-007-18, P-007-09).

The exponential family is one loader, one dump, one two-way flat route, fast mode, `fixed` dispatch and the `exponential`
variate profile: loading and dumping are exponential FCFS stations and the haul and return legs are one delay station, so the
closed network is exactly solvable by mean-value analysis (Reiser and Lavenberg). `gap_table` reports how far the same fleet
under the `engine` profile and traffic mode sits from that product-form answer; it is a result, never a pass or fail check.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .adapter import run_shift
from .scenario import _catalog_loader, _catalog_truck
from .variates import build_table, encode_table

FAMILY_LENGTH_M = 1500.0
FAMILY_LIMIT_KMH = 20.0
TRUCK, LOADER = "CAT_793F", "SHOVEL_45"
ENGINE_CONSTANTS = {
    "stagger_window_s": 60.0,
    "dump_mean_s": 55.0,
    "dump_cv": 0.15,
    "closure_retry_s": 300.0,
    "headway_m": 80.0,
    "headway_s": 8.0,
    "payload_min_frac_of_mean": 0.5,
    "payload_max_t": 400.0,
}


def exact_mva(n_trucks: int, queue_service_s: Sequence[float], delay_s: float) -> float:
    """Cycles per second of the closed network of FCFS queue stations plus one delay station (exact MVA)."""
    if isinstance(n_trucks, bool) or not isinstance(n_trucks, int) or n_trucks < 1:
        raise ValueError(f"n_trucks must be a positive integer: {n_trucks!r}")
    if not len(queue_service_s) or any(not math.isfinite(s) or s <= 0.0 for s in queue_service_s):
        raise ValueError("queue service times must be a non-empty list of finite times > 0")
    if not math.isfinite(delay_s) or delay_s < 0.0:
        raise ValueError(f"delay must be finite and >= 0: {delay_s!r}")
    q = [0.0] * len(queue_service_s)
    x = 0.0
    for k in range(1, n_trucks + 1):
        r = [s * (1.0 + qi) for s, qi in zip(queue_service_s, q, strict=True)]
        x = k / (sum(r) + delay_s)
        q = [x * ri for ri in r]
    return x


def _tables(profile: str) -> list[dict]:
    if profile == "deterministic":
        return []
    if profile == "exponential":
        return [encode_table(build_table("exponential"), "exponential")]
    return [  # engine: the payload normal and the unit-mean lognormals of the shovel (0.18) and the dump (0.15)
        encode_table(build_table("normal"), "normal"),
        encode_table(build_table("lognormal-unit-mean", 0.18), "lognormal-unit-mean", 0.18),
        encode_table(build_table("lognormal-unit-mean", 0.15), "lognormal-unit-mean", 0.15),
    ]


def exponential_family_bundle(
    n_trucks: int, *, profile: str = "exponential", horizon_s: float = 360000.0, warmup_s: float = 7200.0
) -> dict:
    """A scenario bundle of the oracle family with `n_trucks` trucks (the `engine` profile runs in traffic mode)."""
    return {
        "schema_version": "1.0",
        "id": f"mva-family-{profile}-n{n_trucks}",
        "description": "Oracle family: one loader, one dump, one two-way flat route, fixed dispatch.",
        "live": n_trucks <= 40,
        "mode": "traffic" if profile == "engine" else "fast",
        "horizon_s": horizon_s,
        "kpi_window": {"warmup_s": warmup_s},
        "network": {
            "nodes": [
                {"id": 1, "kind": "face", "pos_m": [0.0, 0.0, 1500.0]},
                {"id": 2, "kind": "dump", "pos_m": [FAMILY_LENGTH_M, 0.0, 1500.0]},
            ],
            "segments": [
                {
                    "id": 1,
                    "a": 1,
                    "b": 2,
                    "polyline_m": [[0.0, 0.0, 1500.0], [FAMILY_LENGTH_M, 0.0, 1500.0]],
                    "length_m": FAMILY_LENGTH_M,
                    "grade_pct": 0.0,
                    "width_class": 2,
                    "one_way": False,
                    "speed_limit_kmh": FAMILY_LIMIT_KMH,
                    "rolling_resistance_pct": 2.0,
                    "zone_id": None,
                    "single_lane_op": False,
                }
            ],
            "zones": [],
            "junctions": [],
        },
        "equipment": {"truck_classes": [_catalog_truck(TRUCK)], "loader_classes": [_catalog_loader(LOADER)]},
        "fleet": [{"id": i + 1, "truck_class": TRUCK, "start_loader": 1} for i in range(n_trucks)],
        "loaders": [{"node": 1, "loader_class": LOADER, "n_spots": 1, "destination_dump": 2}],
        "dumps": [2],
        "dispatcher": {"id": "fixed"},
        "variate_profile": profile,
        "quantile_tables": _tables(profile),
        "engine_constants": dict(ENGINE_CONSTANTS),
        "failures": None,
    }


def family_delay_s(bundle: dict) -> float:
    """The delay-station time: loaded leg plus empty leg over the route's segments, length / speed limit each."""
    return float(sum(2.0 * s["length_m"] / (s["speed_limit_kmh"] / 3.6) for s in bundle["network"]["segments"]))


def family_services_s(bundle: dict) -> tuple[float, float]:
    """(loading, dumping) mean service times of the family, by hand from the catalog: passes x pass time + spot, and the dump mean."""
    from minehaulsim.equipment.catalog import LOADERS, TRUCKS

    lc, tc = LOADERS[bundle["loaders"][0]["loader_class"]], TRUCKS[bundle["fleet"][0]["truck_class"]]
    return math.ceil(tc.payload_mean_t / lc.pass_t) * lc.pass_time_s + lc.spot_time_s, bundle["engine_constants"][
        "dump_mean_s"
    ]


@dataclass(frozen=True)
class FamilyResult:
    samples: list[float]
    mva_cycles_per_h: float


def _write(workdir: Path, bundle: dict, name: str) -> Path:
    import json

    p = Path(workdir) / name
    p.write_text(json.dumps(bundle, indent=1), encoding="utf-8", newline="\n")
    return p


def run_family(
    n_trucks: int, seeds: Iterable[int], *, workdir: Path, horizon_s: float = 360000.0, warmup_s: float = 7200.0
) -> FamilyResult:
    """The exponential family through the adapter, once per seed; samples are the fleet cycles/h over [warm-up, horizon]."""
    bundle = exponential_family_bundle(n_trucks, horizon_s=horizon_s, warmup_s=warmup_s)
    path = _write(workdir, bundle, f"family-exponential-n{n_trucks}.json")
    samples = [run_shift(path, seed=s).kpis["fleet"]["cycles_per_h"] for s in seeds]
    load_s, dump_s = family_services_s(bundle)
    return FamilyResult(samples, exact_mva(n_trucks, [load_s, dump_s], family_delay_s(bundle)) * 3600.0)


def gap_table(
    n_values: Iterable[int], seeds: Iterable[int], *, workdir: Path, horizon_s: float, warmup_s: float
) -> list[dict]:
    """Per N_T under the `engine` profile and traffic mode: the DES mean throughput against exact MVA, as numbers only."""
    seeds = list(seeds)
    rows = []
    for n in n_values:
        bundle = exponential_family_bundle(n, profile="engine", horizon_s=horizon_s, warmup_s=warmup_s)
        path = _write(workdir, bundle, f"family-engine-n{n}.json")
        des = statistics.fmean(run_shift(path, seed=s).kpis["fleet"]["cycles_per_h"] for s in seeds)
        load_s, dump_s = family_services_s(bundle)
        mva = exact_mva(n, [load_s, dump_s], family_delay_s(bundle)) * 3600.0
        gap = des - mva
        rows.append(
            {
                "n_trucks": n,
                "seeds": len(seeds),
                "des_cycles_per_h": des,
                "mva_cycles_per_h": mva,
                "gap_cycles_per_h": gap,
                "gap_pct": 100.0 * gap / mva,
            }
        )
    return rows
