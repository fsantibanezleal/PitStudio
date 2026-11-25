"""Measured lane of an exported artefact (FR-016-11, FR-016-12, FR-016-13).

The lane is computed by the spec 001 gate from measurements taken from the web timing record of the artefact SHA-256;
a record that is missing or fails validation is ignored with its reason and the lane is `replay`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from pitstudio.contracts.lane import lane_of

_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LaneResult:
    lane: str
    measurements: dict[str, Any]
    ignored_reason: str | None


def _date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _time_ok(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def _record_problem(artefact: Mapping[str, Any], timing: Mapping[str, Any]) -> str | None:
    sha = timing.get("sha256")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha) or sha != artefact["sha256"]:
        return "sha256 of the timing record is missing, malformed or differs from the artefact"
    recorded, created = _date(timing.get("date")), _date(artefact.get("created"))
    if recorded is None or created is None or recorded < created:
        return "date of the timing record is missing, malformed or earlier than the artefact creation"
    for field in ("interaction_ms", "run_ms_t2"):
        if not _time_ok(timing.get(field)):
            return f"time {field} of the timing record is not a finite number >= 0"
    if timing.get("tier") != "T2" or not isinstance(timing.get("browser"), str) or not timing["browser"]:
        return "time record without tier T2 and a browser name"
    return None


def derive_lane(
    artefact: Mapping[str, Any], timing: Mapping[str, Any] | None, *, measured: Mapping[str, Any]
) -> LaneResult:
    """The lane, its `lane_measurements` object and the reason a given timing record was ignored (or None)."""
    ignored = None if timing is None else _record_problem(artefact, timing)
    if timing is not None and ignored is None:
        interaction = None if timing["interaction_ms"] is None else float(timing["interaction_ms"])
        run = None if timing["run_ms_t2"] is None else float(timing["run_ms_t2"])
        stamp = {"tier": timing["tier"], "date": timing["date"], "browser": timing["browser"]}
    else:
        interaction = run = None
        stamp = {"tier": measured["tier"], "date": measured["date"], "browser": measured["browser"]}
    measurements = {
        "web_drivable": bool(artefact["web_drivable"]),
        "max_asset_bytes": int(artefact["bytes"]),
        "interaction_ms": interaction,
        "run_ms_t2": run,
        "trace_bytes": artefact.get("trace_bytes"),
        "measured": stamp,
    }
    return LaneResult(lane_of(measurements), measurements, ignored)
