"""Acceptance of the published models from their parity reports (SC-016-02, SC-016-03).

The verdicts are recomputed from the numbers in the reports; a stored `verdict` or `delta_pp` is never trusted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

PRE_REGISTERED_LAYER1 = {"rtol": 1.0e-3, "atol": 1.0e-5, "max_abs": 1.0e-4}
METRIC_DELTA_MAX_PP = 1.0
MASK_IOU_MIN = 0.99


@dataclass(frozen=True)
class Layer1Acceptance:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class Layer2Acceptance:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _layer1_problems(report: Mapping[str, Any]) -> list[str]:
    name = f"{report.get('model')} ({report.get('variant', 'deployed')})"
    problems = []
    tol = report.get("tolerances") or {}
    if any(tol.get(k) != v for k, v in PRE_REGISTERED_LAYER1.items()):
        problems.append(f"{name}: tolerance triple {tol} differs from the pre-registered {PRE_REGISTERED_LAYER1}")
    max_error = report.get("max_abs_error")
    if not isinstance(max_error, (int, float)) or not max_error <= PRE_REGISTERED_LAYER1["max_abs"]:
        problems.append(f"{name}: max_abs error {max_error} exceeds {PRE_REGISTERED_LAYER1['max_abs']}")
    if report.get("mismatch_fraction") != 0:
        problems.append(f"{name}: mismatch fraction {report.get('mismatch_fraction')} is not 0")
    argmax = report.get("argmax")
    if argmax is not None and argmax.get("agreement") != 1:
        problems.append(f"{name}: argmax agreement {argmax.get('agreement')} is below 1")
    if report.get("verdict") != "pass":
        problems.append(f"{name}: verdict is {report.get('verdict')!r}")
    return problems


def layer1_acceptance(published_models: Sequence[str], reports: Sequence[Mapping[str, Any]]) -> Layer1Acceptance:
    """Every published model needs layer-1 reports and every one of them must pass from its numbers."""
    problems: list[str] = []
    for model in published_models:
        own = [r for r in reports if r.get("layer") == 1 and r.get("model") == model]
        if not own:
            problems.append(f"{model}: layer-1 parity report missing")
        for report in own:
            problems.extend(_layer1_problems(report))
    return Layer1Acceptance(problems)


def _layer2_problems(report: Mapping[str, Any]) -> list[str]:
    name = f"{report.get('model')} {report.get('precision')}"
    problems = []
    tol = report.get("tolerances") or {}
    if tol.get("metric_delta_pp_max") != METRIC_DELTA_MAX_PP:
        problems.append(f"{name}: tolerance metric_delta_pp_max {tol.get('metric_delta_pp_max')} is not 1")
    if tol.get("mask_iou_min") not in (None, MASK_IOU_MIN):
        problems.append(f"{name}: tolerance mask_iou_min {tol.get('mask_iou_min')} is not 0.99")
    metric = report.get("metric") or {}
    try:
        delta = metric["variant"] - metric["fp32"]
    except (KeyError, TypeError):
        problems.append(f"{name}: delta cannot be computed, metric numbers missing")
    else:
        if not abs(delta) <= METRIC_DELTA_MAX_PP:
            problems.append(f"{name}: delta {delta:+.4g} pp is beyond {METRIC_DELTA_MAX_PP} pp")
    iou = report.get("mask_iou")
    # the spec example (valid-layer2) carries mask_iou_min 0.99 with a null mask_iou and passes: only a measured IoU is checked
    if iou is not None and not iou >= MASK_IOU_MIN:
        problems.append(f"{name}: mask IoU {iou} is below {MASK_IOU_MIN}")
    if report.get("verdict") != "pass":
        problems.append(f"{name}: verdict is {report.get('verdict')!r}")
    return problems


def layer2_acceptance(published: Sequence[tuple[str, str]], reports: Sequence[Mapping[str, Any]]) -> Layer2Acceptance:
    """Every published reduced-precision variant needs a layer-2 report that passes from its numbers."""
    problems: list[str] = []
    for model, precision in published:
        own = [
            r
            for r in reports
            if r.get("layer") == 2 and r.get("model") == model and r.get("precision") == precision
        ]
        if not own:
            problems.append(f"{model} {precision}: layer-2 parity report missing")
        for report in own:
            problems.extend(_layer2_problems(report))
    return Layer2Acceptance(problems)
