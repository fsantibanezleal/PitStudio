# ruff: noqa: E501, PERF401
"""Write tests/fixtures/haulage/m1_goldens.json: golden vectors of the M1 analytical models from `minephys.haulage` (T-007-030).

The numbers are the library's (the match factor, M/M/1//N, open M/M/c and exact mean-value analysis); the tests check them against
closed forms written out independently (tests/parity/test_t_007_030_m1_goldens.py) and the TypeScript port against the file
(web/src/engines/haulage/queueing.test.ts). The hostile vectors are written with their expected typed result by construction
(FR-007-16). Times are in seconds, rates in 1 / s. Non-finite numbers are the strings "NaN", "Infinity" and "-Infinity".

Usage: python tools/make_m1_goldens.py [--check]     (run in the root environment; --check exits 1 when the file is stale)
Deterministic: no random input; the same minephys gives the same bytes.
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from pathlib import Path

from minephys import haulage as mp

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "haulage" / "m1_goldens.json"
SPEC = "spec-007-worked-example"
HOUR = 3600.0


def f(x) -> float:
    return float(x)


def match_factor_vectors() -> list[dict]:
    cases = [
        (1, 1, 60.0, 600.0), (2, 1, 258.0, 853.0), (3, 2, 300.0, 1560.0), (5, 2, 258.0, 900.0), (8, 3, 258.0, 1200.0),
        (12, 4, 120.0, 1500.0), (20, 5, 258.0, 2000.0), (40, 8, 200.0, 2400.0), (7, 2, 90.0, 1800.0), (15, 3, 258.0, 1700.0),
        (30, 6, 150.0, 3000.0), (100, 10, 258.0, 2500.0), (400, 40, 258.0, 2600.0), (4, 1, 45.0, 1400.0), (6, 4, 258.0, 1000.0),
        (9, 3, 33.3, 77.7), (25, 5, 1.0, 1000.0), (2, 2, 599.0, 600.0),
    ]  # fmt: skip
    out = [
        {
            "input": {"n_trucks": n, "n_loaders": loaders, "load_time": lt, "cycle_time": ct},
            "expected": f(mp.match_factor(n, loaders, lt, ct)),
        }
        for n, loaders, lt, ct in cases
    ]
    out[1]["source"] = "spec-007-smoke-family"
    return out


def finite_source_vectors() -> list[dict]:
    specs: list[tuple[int, float, float, str | None]] = [
        (8, 20.0 / HOUR / 7.0, 20.0 / HOUR, SPEC),  # N = 8, lambda/mu = 1/7, mu = 20 per hour
        (5, 0.2 * 15.0 / HOUR, 15.0 / HOUR, SPEC),  # N = 5, lambda/mu = 0.2, mu = 15 per hour
    ]
    ratios = {1: 0.5, 7: 0.15, 9: 0.35, 18: 0.12, 35: 0.08, 2: 1.0, 3: 0.25, 4: 2.0, 6: 0.1, 10: 0.5, 12: 0.2, 15: 1.0, 20: 0.05, 25: 0.3, 30: 0.1, 40: 0.5, 50: 0.02, 60: 0.2,
              80: 0.1, 100: 0.05, 120: 0.04, 150: 0.02, 200: 0.01, 300: 0.005, 400: 0.002}  # fmt: skip
    for n, a in ratios.items():
        # keep N! a^N below 1e280 so the unnormalised sum stays inside a double
        cap = 10.0 ** ((280.0 - math.lgamma(n + 1) / math.log(10.0)) / n)
        a = min(a, cap)
        mu = 18.0 / HOUR
        specs.append((n, a * mu, mu, None))
    out = []
    for n, lam, mu, source in specs:
        r = mp.finite_source_queue(n, lam, mu)
        row = {
            "input": {"n_trucks": n, "travel_rate": lam, "service_rate": mu},
            "expected": {
                "idle_probability": f(r.idle_probability),
                "utilisation": f(r.utilisation),
                "throughput": f(r.throughput),
                "mean_at_loader": f(r.mean_at_loader),
                "mean_time_at_loader": f(r.mean_time_at_loader),
            },
        }
        if source:
            row["source"] = source
        out.append(row)
    return out


def mmc_vectors() -> list[dict]:
    rows = []
    for c in (1, 2, 3, 4, 5, 8, 12, 20, 30, 50, 64):
        for rho in (0.05, 0.5, 0.9, 0.98):
            if c in (1, 3, 8, 30) or rho in (0.05, 0.98):
                rows.append((c, rho))
    out = []
    for c, rho in rows:
        mu = 12.0 / HOUR
        lam = rho * c * mu
        r = mp.mmc_queue(lam, mu, c)
        out.append(
            {
                "input": {"arrival_rate": lam, "service_rate": mu, "servers": c},
                "expected": {
                    "utilisation": f(r.utilisation),
                    "erlang_c": f(r.erlang_c),
                    "mean_wait": f(r.mean_wait),
                    "mean_queue_length": f(r.mean_queue_length),
                    "mean_time_in_system": f(r.mean_time_in_system),
                    "mean_in_system": f(r.mean_in_system),
                },
            }
        )
    return out


def mva_vectors() -> list[dict]:
    cases: list[tuple[int, list[float], list[float], list[str], str | None]] = [
        (n, [240.0, 1200.0], [1.0, 1.0], ["queue", "delay"], SPEC) for n in (1, 3, 5, 6, 8)
    ]
    cases += [
        (10, [258.0, 55.0], [1.0, 1.0], ["queue", "queue"], None),
        (30, [258.0, 55.0, 540.0], [1.0, 1.0, 1.0], ["queue", "queue", "delay"], None),
        (60, [300.0, 120.0, 80.0], [1.0, 0.5, 0.25], ["queue", "queue", "queue"], None),
        (120, [258.0, 55.0, 90.0, 30.0], [1.0, 1.0, 0.8, 0.4], ["queue", "queue", "queue", "delay"], None),
        (200, [258.0, 55.0, 90.0, 30.0, 700.0], [1.0, 1.0, 0.8, 0.4, 1.0], ["queue", "queue", "queue", "queue", "delay"], None),
        (250, [310.0, 200.0, 150.0, 100.0, 60.0, 900.0], [1.0, 1.0, 0.5, 0.5, 0.25, 1.0], ["queue", "queue", "queue", "queue", "queue", "delay"], None),
        (400, [40.0, 35.0, 30.0, 25.0, 20.0], [1.0, 1.0, 1.0, 1.0, 1.0], ["queue", "queue", "queue", "queue", "queue"], None),
    ]  # fmt: skip
    out = []
    for n, s, v, kinds, source in cases:
        r = mp.mean_value_analysis(n, s, v, kinds)
        row = {
            "input": {"population": n, "service_time": s, "visit_ratio": v, "station_type": kinds},
            "expected": {
                "throughput": [f(x) for x in r.throughput],
                "residence_time": [f(x) for x in r.residence_time],
                "queue_length": [f(x) for x in r.queue_length],
                "utilisation": [f(x) for x in r.utilisation],
            },
        }
        if source:
            row["source"] = source
        out.append(row)
    return out


NAN, INF, NINF = "NaN", "Infinity", "-Infinity"


def hostile_vectors() -> list[dict]:
    def bad(fn: str, field: str, **inp) -> dict:
        return {"fn": fn, "input": inp, "expected": {"kind": "InvalidInput", "field": field}}

    mf = {"n_trucks": 4, "n_loaders": 2, "load_time": 258.0, "cycle_time": 900.0}
    fs = {"n_trucks": 4, "travel_rate": 0.001, "service_rate": 0.005}
    mm = {"arrival_rate": 0.002, "service_rate": 0.005, "servers": 2}
    mv = {
        "population": 5,
        "service_time": [240.0, 1200.0],
        "visit_ratio": [1.0, 1.0],
        "station_type": ["queue", "delay"],
    }
    out: list[dict] = []
    for field, values in (
        ("n_trucks", [0, -3, 1.5, NAN, INF, NINF, 401, 1000, 10**6]),
        ("n_loaders", [0, -1, 2.5, NAN, INF]),
        ("load_time", [0.0, -1.0, NAN, INF, NINF]),
        ("cycle_time", [0.0, -600.0, NAN, INF]),
    ):
        out += [bad("match_factor", field, **{**mf, field: v}) for v in values]
    for field, values in (
        ("n_trucks", [0, 2.5, NAN, INF, 401, 1000, -1]),
        ("travel_rate", [0.0, -0.001, NAN, INF]),
        ("service_rate", [0.0, -0.005, NAN, NINF]),
    ):
        out += [bad("finite_source", field, **{**fs, field: v}) for v in values]
    for field, values in (
        ("arrival_rate", [0.0, -0.002, NAN, INF]),
        ("service_rate", [0.0, -1.0, NAN, INF]),
        ("servers", [0, -1, 2.5, NAN, INF]),
    ):
        out += [bad("mmc", field, **{**mm, field: v}) for v in values]
    out += [
        {
            "fn": "mmc",
            "input": {"arrival_rate": 0.004, "service_rate": 0.002, "servers": 2},
            "expected": {"kind": "Unstable"},
        },  # rho = 1 exactly
        {
            "fn": "mmc",
            "input": {"arrival_rate": 0.005, "service_rate": 0.002, "servers": 2},
            "expected": {"kind": "Unstable"},
        },  # rho > 1
        {
            "fn": "mmc",
            "input": {"arrival_rate": 1.0, "service_rate": 0.25, "servers": 4},
            "expected": {"kind": "Unstable"},
        },
        {
            "fn": "mmc",
            "input": {"arrival_rate": 3.0, "service_rate": 1.0, "servers": 1},
            "expected": {"kind": "Unstable"},
        },
    ]
    for field, values in (
        ("population", [0, -2, 2.5, NAN, 401, 1000]),
        ("service_time", [[], [0.0, 1200.0], [240.0, NAN], [-1.0, 5.0]]),
        ("visit_ratio", [[], [1.0, 0.0], [NAN, 1.0]]),
    ):
        out += [bad("mva", field, **{**mv, field: v}) for v in values]
    return out


def document() -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {
            "_note": "Golden vectors of the M1 analytical models from minephys.haulage (tools/make_m1_goldens.py); spec 007 FR-007-15, FR-007-16.",
            "match_factor": match_factor_vectors(),
            "finite_source": finite_source_vectors(),
            "mmc": mmc_vectors(),
            "mva": mva_vectors(),
            "hostile": hostile_vectors(),
        }


def render() -> str:
    return json.dumps(document(), indent=1, allow_nan=False) + "\n"


def main(argv: list[str]) -> int:
    text = render()
    if argv == ["--check"]:
        have = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        if have.replace("\r\n", "\n") != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run python tools/make_m1_goldens.py")
            return 1
        print(f"{OUT.relative_to(ROOT)} is current")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
