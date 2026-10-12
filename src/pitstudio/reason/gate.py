"""The Q8_0 versus BF16 agreement gate (FR-015-14, FR-015-15, SC-015-01).

Agreement is the fraction of the 500 fixed binary queries on which the two paths give identical normalised answers. The
gate decides on the point estimate (a >= 0.95); the Wilson 95 % interval is reported. When the gate fails, every
Cosmos Q8_0 row of the metrics tables becomes a rejected row without a task metric (FR-015-15); when it was not
evaluable, those rows read "not run" (FR-015-10).
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from pitstudio.reason.stats import wilson_interval

GATE_N = 500
THRESHOLD = 0.95
MIN_AGREE = 475  # 0.95 * 500, an integer: the decision is exact
GATE_TYPES = (1, 2, 4, 5, 6)
PER_TYPE = 100
NOT_EVALUABLE = "not run (agreement gate not evaluable)"
Q8_ARM = "cosmos-q8_0"


def agreement(a: Sequence[str], b: Sequence[str]) -> Fraction:
    """Fraction of positions with equal answers."""
    if len(a) != len(b):
        raise ValueError(f"the paths have {len(a)} and {len(b)} answers")
    if len(a) == 0:
        raise ValueError("n = 0: no answers to compare")
    return Fraction(sum(1 for x, y in zip(a, b, strict=True) if x == y), len(a))


def evaluate_gate(q8: Sequence[str], bf16: Sequence[str]) -> dict[str, Any]:
    """The `gate` object of the metrics contract from the aligned answers of the 500 gate queries."""
    if len(q8) != GATE_N or len(bf16) != GATE_N:
        raise ValueError(f"the gate needs exactly {GATE_N} aligned answers per path, got {len(q8)} and {len(bf16)}")
    agree = int(agreement(q8, bf16) * GATE_N)
    lo, hi = wilson_interval(agree, GATE_N)
    passed = agree >= MIN_AGREE
    return {
        "status": "pass" if passed else "fail",
        "n": GATE_N,
        "agree": agree,
        "agreement": agree / GATE_N,
        "wilson95": {"lo": lo, "hi": hi},
        "threshold": THRESHOLD,
        "q8_0_path": "accepted" if passed else "rejected",
    }


def not_run_gate(reason: str = NOT_EVALUABLE) -> dict[str, Any]:
    """The `gate` object when the BF16 reference could not run: nothing was compared."""
    return {
        "status": "not_run",
        "reason": reason,
        "n": GATE_N,
        "agree": None,
        "agreement": None,
        "wilson95": None,
        "threshold": THRESHOLD,
        "q8_0_path": "not_run",
    }


def _decimals(value: float) -> str:
    text = f"{value:.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def apply_gate(rows: Sequence[Mapping[str, Any]], gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Task rows after the gate: Q8_0 rows are rejected (gate failed) or not run (gate not evaluable); others unchanged."""
    status = gate["status"]
    out = []
    for row in rows:
        row = copy.deepcopy(dict(row))
        if row["arm"] == Q8_ARM and status in ("fail", "not_run"):
            if status == "fail":
                row["status"] = "rejected"
                row["reason"] = f"rejected: agreement a = {_decimals(gate['agreement'])} < {THRESHOLD}"
            else:
                row["status"] = "not_run"
                row["reason"] = gate.get("reason") or NOT_EVALUABLE
            row.update(n=0, balanced_accuracy=None, f1=None, unparseable_rate=None, error_rate=None, auroc=None)
            row["by_condition"] = []
        out.append(row)
    return out


def validate_gate_subset(queries: Sequence[Mapping[str, Any]]) -> None:
    """The gate-flagged queries are 500: 100 per binary type, 50 yes and 50 no each, none of type 3."""
    if len(queries) != GATE_N:
        raise ValueError(f"the gate subset has {len(queries)} queries, it must have {GATE_N}")
    counts = Counter((q["type"], q["truth"]) for q in queries)
    expected = {(t, label): PER_TYPE // 2 for t in GATE_TYPES for label in ("yes", "no")}
    if counts != expected:
        raise ValueError(
            f"the gate subset must hold 50 yes and 50 no for each of types {GATE_TYPES}; found {dict(counts)}"
        )
