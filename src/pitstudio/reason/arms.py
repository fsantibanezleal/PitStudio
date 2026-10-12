"""The arm plan of task A (FR-015-28): which arm answers which queries.

Every arm sees the same query ids and prompts, except where the spec narrows it: Cosmos with reasoning on runs on the
300-query reasoning subset, the Cosmos BF16 reference on the 500-query gate subset, and the detector rule only answers
types 1, 3 and 5 (it is "not applicable" to types 2, 4 and 6).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

# (arm, reasoning), in the order the plan lists them
ARM_ORDER = (
    ("cosmos-q8_0", False),
    ("cosmos-q8_0", True),
    ("cosmos-bf16", False),
    ("qwen-base", False),
    ("detector-rule", False),
    ("constant", False),
)
DETECTOR_TYPES = (1, 3, 5)
BINARY_CONSTANT = "no"
TYPE3_CONSTANT = "1"


def constant_answer(qtype: int) -> str:
    """The constant arm's answer: "no" for the binary types, "1" for type 3."""
    if isinstance(qtype, bool) or qtype not in (1, 2, 3, 4, 5, 6):
        raise ValueError(f"unknown question type {qtype!r}")
    return TYPE3_CONSTANT if qtype == 3 else BINARY_CONSTANT


def arm_plan(queries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One entry per (arm, reasoning): `{"arm", "reasoning", "query_ids", "not_applicable_ids"}`, in query order."""
    plan = []
    for arm, reasoning in ARM_ORDER:
        if arm == "cosmos-q8_0" and reasoning:
            chosen = [q for q in queries if q["reasoning_subset"]]
        elif arm == "cosmos-bf16":
            chosen = [q for q in queries if q["gate_subset"]]
        else:
            chosen = list(queries)
        if arm == "detector-rule":
            ids = [q["query_id"] for q in chosen if q["type"] in DETECTOR_TYPES]
            not_applicable = [q["query_id"] for q in chosen if q["type"] not in DETECTOR_TYPES]
        else:
            ids = [q["query_id"] for q in chosen]
            not_applicable = []
        plan.append({"arm": arm, "reasoning": reasoning, "query_ids": ids, "not_applicable_ids": not_applicable})
    return plan
