"""Relative drop under corruption, the curve rows and the robustness criterion SC-009-03 (FR-009-30, P-009-10).

delta_rel(c, s) = 100 (m_clean - m_c,s) / m_clean in percent of the clean score; m is mAP50 for the detectors and mask
AP50
(descriptive) for RF-DETR-Seg-N.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from pitstudio_pipeline.perception.acceptance import CORRUPTIONS, acceptance_row

MODELS = ("d-fine-n", "d-fine-s", "rf-detr-seg-n")
PRECISIONS = ("fp32", "fp16", "int8")
ARMS = ("S", "U")
SEVERITIES = (1, 2, 3, 4, 5)
# SC-009-03: D-FINE-S and D-FINE-N, fp32 and every live variant (D-FINE-N fp16, D-FINE-S int8), severities 1 and 2
_SC03_VARIANTS = (("d-fine-n", "fp32"), ("d-fine-n", "fp16"), ("d-fine-s", "fp32"), ("d-fine-s", "int8"))
_SC03_SEVERITIES = (1, 2)


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number, got {value!r}")
    return float(value)


def delta_rel(m_clean: float, m_corrupted: float) -> float:
    """100 (m_clean - m_corrupted) / m_clean; ValueError names the offending score."""
    clean = _number("m_clean", m_clean)
    corrupted = _number("m_corrupted", m_corrupted)
    if not math.isfinite(clean) or clean <= 0:
        raise ValueError(f"m_clean must be finite and > 0, got {m_clean!r}")
    if not math.isfinite(corrupted) or corrupted < 0:
        raise ValueError(f"m_corrupted must be finite and >= 0, got {m_corrupted!r}")
    return 100.0 * (clean - corrupted) / clean


def corruption_rows(
    clean: Mapping[tuple[str, str, str], float], corrupted: Mapping[tuple[str, str, str, str, int], float]
) -> list[dict[str, Any]]:
    """One DC-009-05 `corruption_point` per corrupted score, sorted by (model, precision, arm, corruption, severity)."""
    rows = []
    for key in sorted(corrupted):
        model, precision, arm, corruption, severity = key
        if model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}, got {model!r}")
        if precision not in PRECISIONS:
            raise ValueError(f"precision must be one of {PRECISIONS}, got {precision!r}")
        if arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}, got {arm!r}")
        if corruption not in CORRUPTIONS:
            raise ValueError(f"corruption must be one of {CORRUPTIONS}, got {corruption!r}")
        if isinstance(severity, bool) or severity not in SEVERITIES:
            raise ValueError(f"severity must be one of {SEVERITIES}, got {severity!r}")
        if (model, precision, arm) not in clean:
            raise ValueError(f"m_clean: no clean score for {model} {precision} arm {arm}")
        m_clean = clean[(model, precision, arm)]
        m_corrupted = corrupted[key]
        mask = model == "rf-detr-seg-n"
        rows.append(
            {
                "model": model,
                "precision": precision,
                "training_arm": arm,
                "metric": "mask_ap50" if mask else "map50",
                "corruption": corruption,
                "severity": severity,
                "m_clean": float(m_clean),
                "m_corrupted": float(m_corrupted),
                "delta_rel_pct": delta_rel(m_clean, m_corrupted),
                "descriptive": mask,
            }
        )
    return rows


def sc03_rows(
    points: Sequence[Mapping[str, Any]], *, support: Sequence[tuple[str, str, int]], reason: str | None = None
) -> list[dict[str, Any]]:
    """The 24 SC-009-03 rows (4 variants x 3 corruptions x severities 1 and 2) from the arm S curve points.

    A missing point gives a `not run` row with a reason (`reason`, or a default one) and no value.
    """
    index = {
        (p["model"], p["precision"], p["corruption"], p["severity"]): p for p in points if p.get("training_arm") == "S"
    }
    rows = []
    for model, precision in sorted(_SC03_VARIANTS):
        for corruption in CORRUPTIONS:
            for severity in _SC03_SEVERITIES:
                point = index.get((model, precision, corruption, severity))
                if point is None:
                    rows.append(
                        {
                            "criterion": "SC-009-03",
                            "model": model,
                            "precision": precision,
                            "corruption": corruption,
                            "severity": severity,
                            "statistic": "delta_rel_pct",
                            "threshold": 10,
                            "verdict": "not run",
                            "reason": reason
                            or f"no corrupted evaluation of {model} {precision} under {corruption} severity {severity}",
                        }
                    )
                    continue
                rows.append(
                    acceptance_row(
                        "SC-009-03",
                        value=point["delta_rel_pct"],
                        support=support,
                        model=model,
                        precision=precision,
                        corruption=corruption,
                        severity=severity,
                    )
                )
    return rows
