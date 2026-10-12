"""The publish step of the detection evaluation report (FR-009-51).

A report computed from a contract-fixture SDG index (`fixture: true`) is published without any metric: every metric key is
removed at every depth, rows and blocks stay (statuses, supports, labels), and every acceptance verdict becomes "not run".
A real report is published unchanged.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

METRIC_KEYS: frozenset[str] = frozenset(
    {
        "ap50",
        "ap50_95",
        "ap50_interval",
        "ap50_95_interval",
        "value",
        "interval",
        "delta_rel_pct",
        "m_clean",
        "m_corrupted",
        "difference",
        "labeller_b_map50",
        "box_f1",
    }
)
_FIXTURE_REASON = "fixture index: no metric published"


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k not in METRIC_KEYS}
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def publish_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """The report as published: unchanged when real, metric-free when it comes from a fixture index."""
    if not isinstance(report, Mapping):
        raise ValueError(f"report must be a mapping, got {type(report).__name__}")
    if report.get("fixture") is not True:
        return copy.deepcopy(dict(report))
    out = _strip(copy.deepcopy(dict(report)))
    for row in out.get("acceptance", []):
        row["verdict"] = "not run"
        row["reason"] = _FIXTURE_REASON
        row.pop("insufficient_support", None)
    ablation = out.get("dr_ablation")
    if isinstance(ablation, dict):
        ablation.pop("verdict", None)  # a verdict is a claim drawn from the fixture's metric
    return out  # type: ignore[no-any-return]
