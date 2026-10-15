# ruff: noqa: E501
"""Shared episode-table builders of the spec 014 evaluation tests (pipeline environment; standard library and numpy only).

This module holds no test. It is imported by `tests/pipeline/test_t_014_04*.py`, `test_t_014_092_*` and is locked with the first of them. Nothing here
calls the code under test.

A table document is a plain dict {"meta": <il-episodes sidecar>, "rows": [<episode row dicts>]}; the sidecar follows `contracts/il-episodes.schema.json`
(DC-014-04) and the rows follow `$defs/il1_episode` or `$defs/dig_episode`. The seed-set digest is defined here as the SHA-256 of the compact JSON text of the
sorted seed list, `json.dumps(sorted(seeds), separators=(",", ":"))` (the spec says only "SHA-256 of the sorted seed list").
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

EVAL_START = 1_000_000
RUN = "20261012T100000Z-test-run"
ZERO = "0" * 64

IL1_SEEDS_BLOCK = {
    "train": {"start": 0, "count": 4096},
    "eval": {"start": EVAL_START, "count": 100},
}
IL2_SEEDS_BLOCK = {
    "train": {"start": 0, "count": 4096},
    "eval": {"start": EVAL_START, "count": 100},
    "tune": {"start": 2_000_000, "count": 20},
}


def seed_digest(seeds) -> str:
    return hashlib.sha256(json.dumps(sorted(seeds), separators=(",", ":")).encode("utf-8")).hexdigest()


def il1_row(seed: int, **over: Any) -> dict[str, Any]:
    row = {
        "seed": seed, "light_vehicles": seed % 4, "termination": "success", "success": True, "collision": False, "steps": 1000,
        "sum_sq_lateral_error_m2": 100.0, "rms_lateral_error_m": math.sqrt(100.0 / 1000.0), "max_lateral_error_m": 0.6,
        "min_ttc_s": math.inf, "energy_kwh_per_t_km": 0.15, "frac_within_v_lim": 0.97,
    }  # fmt: skip
    row.update(over)
    return row


def dig_row(seed: int, **over: Any) -> dict[str, Any]:
    row = {
        "seed": seed, "termination": "completed", "fill_factor": 0.9, "cycle_time_s": 18.0, "productivity_per_s": 0.9 / 18.0,
        "stalled": False, "lift_off": True,
    }  # fmt: skip
    row.update(over)
    return row


def meta(
    policy: str,
    arm: str,
    rows: list[dict],
    *,
    controller_kind: str | None = None,
    deterministic: bool = True,
    run_id: str = RUN,
) -> dict[str, Any]:
    column_set = "il1-episode" if policy == "IL-1" else "dig-episode"
    kind = controller_kind or {
        ("IL-1", "baseline"): "pure-pursuit-pid",
        ("IL-2", "baseline"): "scripted-dig",
        ("IL-3", "baseline"): "scripted-dig",
    }.get((policy, arm), "policy")
    return {
        "schema_version": "1.0",
        "policy": policy,
        "arm": arm,
        "run_id": run_id,
        "controller": {"kind": kind, "sha256": hashlib.sha256(f"{policy}-{arm}".encode()).hexdigest()},
        "deterministic_actions": deterministic,
        "seed_set_sha256": seed_digest(r["seed"] for r in rows),
        "column_set": column_set,
        "table": {
            "path": f"il/{policy.lower().replace('-', '')}/episodes-{arm}.parquet",
            "bytes": 1000,
            "sha256": ZERO,
            "rows": len(rows),
        },
    }


def table(policy: str, arm: str, rows: list[dict], **kw: Any) -> dict[str, Any]:
    return {"meta": meta(policy, arm, rows, **kw), "rows": rows}


def il1_rows(n: int = 100, start: int = EVAL_START, make=il1_row, **over: Any) -> list[dict]:
    return [make(start + i, **over) for i in range(n)]


def dig_rows(n: int = 100, start: int = EVAL_START, make=dig_row, **over: Any) -> list[dict]:
    return [make(start + i, **over) for i in range(n)]
