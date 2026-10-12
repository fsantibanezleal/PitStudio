"""Manifest records and labels of the surrogate artefacts (FR-011-45, DC-000-01).

Every rollout, field and calibration dataset and every surrogate artefact is described by a manifest `artefact` record naming
the producing tool (Warp, Newton, PyTorch, ONNX Runtime), its stage, its inputs with SHA-256 and its lane, and is labelled
"calibrated synthetic - not validated against real data" (FR-000-09, the dash is U+2014); the literature repose targets are the only real-world
anchor and do not change the label. The lane is measured, never declared: an ONNX record claims `live` only when its T2
lane measurements pass the gate of `thresholds.yaml` (`lane_gate`).
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from pitstudio.surrogate_io import load_contract_schema

LABEL = "calibrated synthetic — not validated against real data"
_MAX_NOTES = 20
_MAX_NOTE = 300
_GIT_LIMIT = 10 * 1024 * 1024  # a git-hosted asset must be under 10 MiB (manifest schema)

# kind -> (artefact kind, producer tool or {solver: tool}, stage id, lane rule, budget class, needs a solver)
_TABLE: dict[str, tuple[str, Any, str, str, str, bool]] = {
    "rollout-set": ("shard", {"warp-dem": "warp", "newton-mpm": "newton"}, "st50_physics", "replay", "shards-clouds", True),
    "field-dataset": ("field", "warp", "st50_physics", "replay", "shards-clouds", False),
    "calibration-dataset": ("table", {"warp-dem": "warp", "newton-mpm": "newton"}, "st50_physics", "static", "own-code", True),
    "gns-onnx": ("onnx", "pytorch", "s60_export", "measured", "onnx", False),
    "fno-onnx": ("onnx", "pytorch", "s60_export", "measured", "onnx", False),
    "parity-report": ("table", "onnxruntime", "s60_export", "static", "own-code", False),
    "model-card": ("model-card", "pytorch", "s50_evaluate", "static", "own-code", False),
}
KINDS: tuple[str, ...] = tuple(_TABLE)


def label_for(kind: str) -> str:
    """The label of an artefact kind: the same string for every kind; ValueError for an unknown kind."""
    if not isinstance(kind, str) or kind not in _TABLE:
        raise ValueError(f"unknown kind {kind!r}; expected one of {list(KINDS)}")
    return LABEL


def _manifest_defs() -> dict[str, Any]:
    return load_contract_schema("manifest")["$defs"]


def _check(defs: Mapping[str, Any], definition: str, value: Any, argument: str) -> None:
    validator = Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": defs})
    errors = list(validator.iter_errors(value))
    if errors:
        raise ValueError(f"{argument}: {errors[0].message}")


def _gate_holds(measurements: Mapping[str, Any]) -> bool:
    gate = yaml.safe_load(_thresholds().read_text(encoding="utf-8"))["lane_gate"]
    checks = (
        (measurements.get("max_asset_bytes"), gate["live_asset_mb_max"] * 1_000_000),
        (measurements.get("interaction_ms"), gate["interaction_ms_max"]),
        (measurements.get("run_ms_t2"), gate["run_s_max"] * 1000),
        (measurements.get("trace_bytes"), gate["trace_mb_max"] * 1_000_000),
    )
    return bool(measurements.get("web_drivable") is True) and all(v is not None and v <= limit for v, limit in checks)


def _thresholds() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "specs" / "000-foundation" / "thresholds.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("specs/000-foundation/thresholds.yaml not found")


def artefact_record(
    kind: str,
    *,
    artefact_id: str,
    run_id: str,
    git_sha: str,
    file_path: str | Path,
    rel_path: str,
    inputs: Sequence[Mapping[str, str]],
    lane_measurements: Mapping[str, Any] | None = None,
    solver: str | None = None,
    cases: Sequence[str] = (),
    release_tag: str | None = None,
) -> dict[str, Any]:
    """A manifest `artefact` record for a file of the given kind; see the module docstring for the rules."""
    label_for(kind)
    art_kind, tool, stage, lane_rule, budget_class, needs_solver = _TABLE[kind]
    defs = _manifest_defs()
    _check(defs, "artefact_id", artefact_id, "artefact_id")
    _check(defs, "run_id", run_id, "run_id")
    _check(defs, "git_sha", git_sha, "git_sha")
    _check(defs, "relpath", rel_path, "rel_path")
    if not inputs:
        raise ValueError("inputs: at least one input is required")
    for i, entry in enumerate(inputs):
        validator = Draft202012Validator({"$ref": "#/$defs/input_ref", "$defs": defs})
        for error in sorted(validator.iter_errors(dict(entry)), key=lambda e: [str(p) for p in e.path]):
            field = f".{error.path[0]}" if error.path else ""
            raise ValueError(f"inputs[{i}]{field}: {error.message}")
    if isinstance(tool, dict):
        if solver not in tool:
            raise ValueError(f"solver must be one of {list(tool)} for a {kind}, got {solver!r}")
        producer_tool = tool[solver]
    else:
        producer_tool = tool
    path = Path(file_path)
    if not path.is_file():
        raise ValueError(f"file {file_path} does not exist")
    raw = path.read_bytes()
    if lane_rule == "static":
        lane = "static"
    else:
        if lane_measurements is None:
            raise ValueError(f"lane_measurements are required for a {kind}: the lane is measured, not declared")
        _check(defs, "lane_measurements", dict(lane_measurements), "lane_measurements")
        lane = "live" if lane_rule == "measured" and _gate_holds(lane_measurements) else "replay"
    on_git = len(raw) < _GIT_LIMIT
    record: dict[str, Any] = {
        "id": artefact_id,
        "run_id": run_id,
        "git_sha": git_sha,
        "path": rel_path if on_git else Path(rel_path).name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "kind": art_kind,
        "producer": {"tool": producer_tool, "stage": {"id": stage}},
        "inputs": [dict(i) for i in inputs],
        "cases": list(cases),
        "lane": lane,
        "licence_class": "own",
        "spdx": "Apache-2.0",
        "asset_host": "git" if on_git else "release",
        "budget_class": budget_class,
    }
    if not on_git:
        if release_tag is None:
            raise ValueError("release_tag is required for a file of 10 MiB or more (hosted as a release asset)")
        record["release_tag"] = release_tag
    if lane != "static":
        record["lane_measurements"] = copy.deepcopy(dict(lane_measurements or {}))
    errors = list(Draft202012Validator({"$ref": "#/$defs/artefact", "$defs": defs}).iter_errors(record))
    if errors:
        raise ValueError(f"the record does not match the manifest schema: {errors[0].message}")
    return record


def run_notes(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """One run note per record, "<artefact id>: <label>" (each at most 300 characters, at most 20 notes)."""
    if len(records) > _MAX_NOTES:
        raise ValueError(f"at most {_MAX_NOTES} notes fit a run manifest, got {len(records)} records")
    notes = [f"{r['id']}: {LABEL}" for r in records]
    if any(len(n) > _MAX_NOTE for n in notes):
        raise ValueError(f"a note is longer than {_MAX_NOTE} characters")
    return notes
