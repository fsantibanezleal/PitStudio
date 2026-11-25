# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Lane gate of the Isaac Lab robot-learning lane (FR-014-03).

The lane is optional. Unless the ``isaaclab`` probe of ``studio/capabilities.json`` says ``pass``, the planner skips the two
IL stages with the recorded reason, the registry entry of the tool becomes ``evaluated-not-adopted``, no IL artefact is
published and the web panels show "evaluated, not adopted". The registry id of the tool (``isaac-lab``, shown to people) and
the id of its capability probe and environment (``isaaclab``) are different strings; the two constants below are their one
explicit mapping.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pitstudio.contracts.validate import validate

__all__ = ["PROBE", "STAGES", "TOOL_ID", "LaneState", "apply_to_tools", "evaluate_lane", "filter_publishable"]

STAGES = ("st60_il_train", "st61_il_mpm_eval")
TOOL_ID = "isaac-lab"  # registry id in studio/tools.yaml
PROBE = "isaaclab"  # probe id in studio/capabilities.json and environment id of studio/isaaclab
DOCS_PAGE = "docs/frameworks/not-adopted-isaac-lab.md"
MAX_REASON = 600
MIN_REASON = 20


@dataclass(frozen=True)
class LaneState:
    adopted: bool
    probe_status: str  # "pass" | "fail" | "skip" | "missing" | "invalid"
    reason: str | None
    skipped: dict[str, str] = field(default_factory=dict)
    publish_artefacts: bool = False
    panel_state: str = "evaluated, not adopted"

    def skip_reason(self, stage_id: str) -> str | None:
        return self.skipped.get(stage_id)


def _not_adopted(status: str, reason: str) -> LaneState:
    reason = reason[:MAX_REASON]
    return LaneState(
        adopted=False,
        probe_status=status,
        reason=reason,
        skipped=dict.fromkeys(STAGES, reason),
        publish_artefacts=False,
        panel_state="evaluated, not adopted",
    )


def _load(capabilities: Any) -> tuple[Any, str | None]:
    """(document, problem): the parsed capability report, or the reason it cannot be read."""
    if capabilities is None:
        return None, "missing"
    if isinstance(capabilities, str | bytes):
        try:
            text = capabilities.decode("utf-8") if isinstance(capabilities, bytes) else capabilities
            return json.loads(text), None
        except (UnicodeDecodeError, ValueError) as exc:
            return None, f"the capability report is not valid JSON ({type(exc).__name__})"
    return capabilities, None


def evaluate_lane(capabilities: Mapping[str, Any] | str | bytes | None) -> LaneState:
    """The lane state from the parsed capability report, its JSON text, or None when the file is absent."""
    doc, problem = _load(capabilities)
    if problem == "missing":
        return _not_adopted(
            "missing", "Isaac Lab probe missing: studio/capabilities.json is absent, the lane is not adopted"
        )
    if problem is not None:
        return _not_adopted("invalid", f"Isaac Lab probe invalid: {problem}; the lane is not adopted")
    errors = validate(doc, "capabilities") if isinstance(doc, Mapping) else None
    if errors is None or errors:
        detail = (
            "the capability report is not an object"
            if errors is None
            else f"{errors[0].pointer or '/'}: {errors[0].message}"
        )
        return _not_adopted("invalid", f"Isaac Lab probe invalid: {detail[:300]}; the lane is not adopted")
    record = doc["probes"].get(PROBE)
    if record is None:
        return _not_adopted(
            "missing", "Isaac Lab probe missing: no isaaclab entry in the capability report, the lane is not adopted"
        )
    status = record["status"]
    if status == "pass":
        return LaneState(True, "pass", None, {}, True, "available")
    notes = record.get("notes") or []
    recorded = record.get("error") or (notes[0] if notes else None)
    head = f"Isaac Lab probe {status}: "
    if recorded:
        reason = head + str(recorded)
    else:
        reason = head + "no reason was recorded in the capability report; the kit-less Cartpole smoke did not pass"
    return _not_adopted(status, reason)


def apply_to_tools(tools_doc: Mapping[str, Any], state: LaneState) -> dict[str, Any]:
    """A deep copy of the registry; a not-adopted lane sets the isaac-lab entry to evaluated-not-adopted with the reason."""
    tools = tools_doc.get("tools") if isinstance(tools_doc, Mapping) else None
    if not isinstance(tools, list) or not any(isinstance(t, Mapping) and t.get("id") == TOOL_ID for t in tools):
        raise ValueError(f"tools_doc has no tools list with an entry {TOOL_ID!r}")
    out = copy.deepcopy(dict(tools_doc))
    if state.adopted:
        return out
    for tool in out["tools"]:
        if tool.get("id") == TOOL_ID:
            tool["status"] = "evaluated-not-adopted"
            tool["reason"] = state.reason
            tool["docs_page"] = DOCS_PAGE
    return out


def filter_publishable(artefacts: Sequence[Mapping[str, Any]], state: LaneState) -> list[Mapping[str, Any]]:
    """Drop every artefact of an IL stage when the lane is not adopted."""
    if state.adopted:
        return list(artefacts)
    return [a for a in artefacts if a.get("stage") not in STAGES]
