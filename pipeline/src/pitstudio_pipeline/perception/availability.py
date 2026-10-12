"""Honest "not run" of the perception stages and the local-only rule of SDG and sensor figures (FR-009-40, FR-009-41).

The capability report of the machine decides what runs: Isaac Sim / Replicator (probe `isaacsim`) is needed by `st55_sdg`
and so by every stage downstream of it; ovrtx (probe `ovrtx`) feeds the crusher family only. Nothing is ever substituted:
a stage that cannot run ends "not run" and B2 shows "not yet run" (FR-000-07).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pitstudio.contracts.io import pointer_of

STAGES: tuple[str, ...] = ("st55_sdg", "s10_preprocess", "s30_train", "s40_infer", "s50_evaluate", "s60_export")
LOCAL_ONLY_STAGES: frozenset[str] = frozenset({"st55_sdg", "st53_sensors"})
_NOTICE = "measured locally, not published (licence)"  # FR-000-08 and the capability schema
_CRUSHER_NOTE = "crusher family not run"

# keys that name a throughput, rate, latency, duration, elapsed / wall time, fps, GPU-hours or telemetry figure
_FIGURE_KEY = re.compile(
    r"throughput|fps|latency|elapsed|wall[_-]?(clock|time)|duration|gpu[_-]?hours|telemetry|timing|render[_-]time"
    r"|frame[_-]?rate|(^|[_-])per[_-](s|sec|second|minute|min|hour|h)($|[_-])|[_-](ms|msec|seconds|secs)$|[_-]time[_-]?s$"
)


@dataclass(frozen=True)
class StageStatus:
    """Status of one perception stage: `run`, or `not run` with the probe that blocks it as the reason."""

    stage: str
    status: Literal["run", "not run"]
    reason: str


@dataclass(frozen=True)
class PerceptionPlan:
    """What the capability report lets the perception chain do."""

    stages: tuple[StageStatus, ...]
    families: dict[str, str]
    train_families: tuple[str, ...]
    b2_status: Literal["run", "not yet run"]
    model_card_notes: tuple[str, ...]
    substitute_data: bool = field(default=False)  # never: no substitute data is created


def _passes(probes: Mapping[str, Any], name: str) -> bool:
    entry = probes.get(name)
    return isinstance(entry, Mapping) and entry.get("status") == "pass"


def plan_perception(capabilities: Mapping[str, Any]) -> PerceptionPlan:
    """Stage statuses, families, training families and card notes for a capability report (probes under `probes`)."""
    probes = capabilities.get("probes") if isinstance(capabilities, Mapping) else None
    if not isinstance(probes, Mapping):
        raise ValueError("capabilities must be a capability report with a `probes` mapping")
    if not _passes(probes, "isaacsim"):
        reason = "probe isaacsim does not pass (Isaac Sim / Replicator unavailable): st55_sdg cannot run, no substitute data"
        return PerceptionPlan(
            stages=tuple(StageStatus(s, "not run", reason) for s in STAGES),
            families={"pit": "not run", "crusher": "not run"},
            train_families=(),
            b2_status="not yet run",
            model_card_notes=(),
        )
    stages = tuple(StageStatus(s, "run", "") for s in STAGES)
    if _passes(probes, "ovrtx"):
        return PerceptionPlan(stages, {"pit": "run", "crusher": "run"}, ("pit", "crusher"), "run", ())
    return PerceptionPlan(stages, {"pit": "run", "crusher": "not run"}, ("pit",), "run", (_CRUSHER_NOTE,))


def local_only_notice() -> str:
    """The exact label shown instead of a figure that is measured locally and not published (FR-000-08)."""
    return _NOTICE


class LocalOnlyViolation(ValueError):
    """A throughput, timing or telemetry figure of a local-only stage: `pointer` is the first offending key."""

    def __init__(self, pointer: str) -> None:
        self.pointer = pointer
        super().__init__(f"{pointer}: a throughput, timing or telemetry figure of Isaac Sim, Replicator or ovrtx is not published; {_NOTICE}")


def _first_figure(node: Any, path: list[Any]) -> list[Any] | None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            if isinstance(key, str) and _FIGURE_KEY.search(key.lower()):
                return [*path, key]
            found = _first_figure(value, [*path, key])
            if found is not None:
                return found
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found = _first_figure(value, [*path, i])
            if found is not None:
                return found
    return None


def assert_no_local_only_figures(document: object) -> None:
    """Raise `LocalOnlyViolation` for the first key that names a throughput, timing or telemetry figure."""
    found = _first_figure(document, [])
    if found is not None:
        raise LocalOnlyViolation(pointer_of(found))


def validate_stage_record(record: Mapping[str, Any]) -> None:
    """A manifest stage entry: SDG and sensor stages carry `performance: local-only` and no figure."""
    if record.get("stage") not in LOCAL_ONLY_STAGES:
        return
    if record.get("performance") != "local-only":
        raise ValueError(f"stage {record.get('stage')!r} must carry performance 'local-only', got {record.get('performance')!r}")
    assert_no_local_only_figures(record)
