# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""IL task parameter validation and the configuration hash (FR-014-46).

An invalid task document raises ``TaskParamsError`` (exit code 2) naming the JSON pointer of the first offending member.
Beyond the JSON Schema it checks the rules the schema cannot express: a randomisation range with lower > upper or outside
the FR-014-13 / FR-014-19 limits, the observation layout sum, and evaluation seeds that overlap training or tuning seeds.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

from pitstudio.robots._contract import schema_problems
from pitstudio.robots.randomise import IL1_LIMITS, SOIL_LIMITS

__all__ = ["TaskParamsError", "config_hash", "validate_task_params"]

_DEFINITION = {"IL-1": "haul_truck_task", "IL-2": "dig_task", "IL-3": "dig_task"}
_LIMITS = {"IL-1": IL1_LIMITS, "IL-2": SOIL_LIMITS, "IL-3": SOIL_LIMITS}
_SUM = {"IL-1": 63, "IL-2": 46, "IL-3": 46}


class TaskParamsError(ValueError):
    """An invalid IL task parameter document; the stage exits with code 2 before any GPU work."""

    exit_code = 2

    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


def config_hash(params: Mapping[str, Any]) -> str:
    """SHA-256 (hex) of the canonical JSON text of the whole parameter document."""
    text = json.dumps(dict(params), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_task_params(params: Any) -> None:
    """Raise TaskParamsError naming the first offending member; return None for a valid document."""
    if not isinstance(params, Mapping):
        raise TaskParamsError("/", f"task parameters must be a JSON object, got {type(params).__name__}")
    policy = params.get("policy")
    if policy not in _DEFINITION:
        raise TaskParamsError("/policy", f"must be one of {sorted(_DEFINITION)}, got {policy!r}")
    problems = schema_problems(params, "il-task", _DEFINITION[policy])
    if problems:
        pointer, message = problems[0]
        raise TaskParamsError(pointer, message)
    _rules(params, policy)


def _rules(params: Mapping[str, Any], policy: str) -> None:
    rand = params["randomisation"]
    for key, (lo_limit, hi_limit) in _LIMITS[policy].items():
        if key not in rand:
            continue
        lo, hi = rand[key]
        if not (math.isfinite(lo) and math.isfinite(hi)):
            raise TaskParamsError(f"/randomisation/{key}", "bounds must be finite")
        if lo > hi:
            raise TaskParamsError(f"/randomisation/{key}", f"lower bound {lo} is above upper bound {hi}")
        if lo < lo_limit or hi > hi_limit:
            raise TaskParamsError(f"/randomisation/{key}", f"must lie within [{lo_limit}, {hi_limit}]")
    for key, value in params["reward_weights"].items():
        if not math.isfinite(value) or value < 0:
            raise TaskParamsError(f"/reward_weights/{key}", "reward weights must be finite and >= 0")
    total = sum(seg["size"] for seg in params["observation_layout"])
    if total != _SUM[policy]:
        raise TaskParamsError("/observation_layout", f"segment sizes sum to {total}, expected {_SUM[policy]}")
    ranges = {
        name: (blk["start"], blk["start"] + blk["count"])
        for name, blk in params["seeds"].items()
        if isinstance(blk, Mapping)
    }
    names = list(ranges)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if ranges[a][0] < ranges[b][1] and ranges[b][0] < ranges[a][1]:
                raise TaskParamsError("/seeds", f"seed ranges {a!r} and {b!r} overlap")
