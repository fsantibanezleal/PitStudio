"""Manifest artefact entries written by s60_export (FR-016-11)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pitstudio.export.lanes import derive_lane

_COPIED = ("id", "path", "bytes", "sha256", "kind", "inputs", "budget_class", "licence_class", "spdx", "asset_host")
_OPTIONAL = ("media_type", "cases", "attribution", "release_tag")


def build_entry(
    spec: Mapping[str, Any],
    *,
    run_id: str,
    git_sha: str,
    tool: str,
    measured: Mapping[str, Any],
    timing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """An artefact object (manifest `$defs/artefact`) with the measured lane and its measurements."""
    lane = derive_lane(spec, timing, measured=measured)
    entry: dict[str, Any] = {"run_id": run_id, "git_sha": git_sha}
    entry.update({key: spec[key] for key in _COPIED})
    entry.update({key: spec[key] for key in _OPTIONAL if spec.get(key) is not None})
    entry["producer"] = {"tool": tool, "stage": {"id": "s60_export"}}
    entry["lane"] = lane.lane
    entry["lane_measurements"] = lane.measurements
    return entry
