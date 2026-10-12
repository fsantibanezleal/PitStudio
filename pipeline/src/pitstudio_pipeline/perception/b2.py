"""B2 baked data of the perception case: JSON files built from the evaluation report (FR-009-32, FR-009-41, SC-009-07).

Every file carries the report's `sim_to_real` and `honesty_label` at its top, every object that names a class carries both
labels, and no file holds a real-domain field or a throughput, timing or telemetry figure of Isaac Sim, Replicator or
ovrtx. A fixture report is published first, so its files hold no metric.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from pitstudio_pipeline.perception.availability import assert_no_local_only_figures
from pitstudio_pipeline.perception.honesty import check_sim_to_real_labels
from pitstudio_pipeline.perception.publish import publish_report


def _label_shortfalls(rows: list[dict[str, Any]], labels: Mapping[str, str]) -> list[dict[str, Any]]:
    """The class entries of insufficient-support lists carry the labels too (every class entry is labelled)."""
    out = copy.deepcopy(rows)
    for row in out:
        for entry in row.get("insufficient_support", []):
            entry.update(labels)
    return out


def build_b2_data(report: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The B2 baked data files as {relative file name: JSON document}; pure, the report is not modified."""
    rep = publish_report(report)
    labels = {"sim_to_real": rep["sim_to_real"], "honesty_label": rep["honesty_label"]}
    status = {k: rep[k] for k in ("fixture", "partial") if k in rep}
    files: dict[str, dict[str, Any]] = {
        "perception-per-class.json": {
            **labels,
            **status,
            "families": rep["families"],
            "models": rep.get("models", []),
            "classes": rep["per_class"],
            "summary": rep["summary"],
        },
        "perception-corruption.json": {**labels, **status, "corruption": rep["corruption"]},
        "perception-acceptance.json": {
            **labels,
            **status,
            "acceptance": _label_shortfalls(rep["acceptance"], labels),
        },
    }
    if "dr_ablation" in rep:
        files["perception-ablation.json"] = {**labels, **status, "dr_ablation": rep["dr_ablation"]}
    if "real_probe" in rep:  # the labelled probe: aggregate metrics only, published with the per-class file
        files["perception-per-class.json"]["real_probe"] = rep["real_probe"]
    for document in files.values():
        if rep["sim_to_real"] == "not measured":
            check_sim_to_real_labels(document)
        assert_no_local_only_figures(document)
    return files
