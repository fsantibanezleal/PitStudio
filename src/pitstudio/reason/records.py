"""Published answer records and the optional real probe (FR-015-40, FR-015-45, NFR-015-03).

A published record (`contracts/vlm-record.schema.json`) holds the frame asset ids, the question, the full model output,
the parsed answer, the ground truth, a correct flag and its provenance. Records are a stratified random sample of the
full local set: the selection looks only at a record's id and strata, never at its correctness, so wrong answers are
published in their population share. Cosmos records are `display-only`, every other arm's are `own`.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

SCHEMA_VERSION = "1.0"
NOTICES = {"cosmos": "Built on NVIDIA Cosmos", "honesty": "Zero-shot 2B VLM; not a safety system."}
STRATA = ["task", "type", "condition"]
TEXT_BUDGET_BYTES = 1_000_000
MAX_PROBE_IMAGES = 200


def _cell(record: Mapping[str, Any]) -> tuple[Any, ...]:
    task = record["task"]
    if task == "A":
        return ("A", record["question_type"], record["condition"])
    if task == "B":
        return ("B", record["corruption"])
    return (task, record.get("condition"))


def _positive_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def sample_records(records: Sequence[Mapping[str, Any]], *, seed: int, per_cell: int) -> list[dict[str, Any]]:
    """`min(per_cell, available)` records of each stratum (task A: type and condition; B: corruption; C: condition),
    drawn uniformly with a generator seeded by `seed` from the record ids only, returned ordered by `record_id`."""
    _positive_int("per_cell", per_cell)
    cells: dict[tuple[Any, ...], list[str]] = {}
    by_id: dict[str, Mapping[str, Any]] = {}
    for r in records:
        by_id[r["record_id"]] = r
        cells.setdefault(_cell(r), []).append(r["record_id"])
    chosen: list[str] = []
    for key in sorted(cells, key=repr):
        ids = sorted(cells[key])
        rng = random.Random(f"pitstudio-015-sample|{seed}|{key!r}")
        chosen.extend(rng.sample(ids, min(per_cell, len(ids))))
    return [dict(by_id[i]) for i in sorted(chosen)]


def build_record_document(
    records: Sequence[Mapping[str, Any]], *, case: str, git_sha: str, generated: str, seed: int, n_full: int
) -> dict[str, Any]:
    """The `vlm-record` document of one case."""
    if n_full < len(records):
        raise ValueError(f"n_full ({n_full}) is below the number of published records ({len(records)})")
    for r in records:
        expected = "display-only" if str(r["arm"]).startswith("cosmos") else "own"
        if r["licence_class"] != expected:
            raise ValueError(f"record {r['record_id']}: arm {r['arm']} must carry licence class {expected!r}")
    return {
        "schema_version": SCHEMA_VERSION,
        "case": case,
        "generated": generated,
        "git_sha": git_sha,
        "notices": dict(NOTICES),
        "sample": {
            "method": "stratified-random",
            "strata": list(STRATA),
            "seed": seed,
            "n_full": n_full,
            "n_published": len(records),
            "selection_uses_correctness": False,
        },
        "records": [dict(r) for r in records],
    }


def text_bytes(doc: Any) -> int:
    """UTF-8 bytes of the compact JSON text of a document (sorted keys)."""
    return len(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def check_text_budget(doc: Any, limit_bytes: int = TEXT_BUDGET_BYTES) -> None:
    """Raise ValueError unless the document is smaller than the per-case text budget (< 1 MB, NFR-015-03)."""
    _positive_int("limit_bytes", limit_bytes)
    size = text_bytes(doc)
    if size >= limit_bytes:
        raise ValueError(f"baked text is {size} bytes, the budget is below {limit_bytes}")


def cohen_kappa(a: Sequence[Any], b: Sequence[Any]) -> float:
    """Cohen's kappa between two labellers (exact arithmetic); ValueError when undefined (expected agreement 1)."""
    if len(a) != len(b):
        raise ValueError("the labellers labelled different numbers of images")
    if len(a) == 0:
        raise ValueError("n = 0: nothing to compare")
    n = len(a)
    po = Fraction(sum(1 for x, y in zip(a, b, strict=True) if x == y), n)
    pe = sum(Fraction(a.count(c), n) * Fraction(b.count(c), n) for c in set(a) | set(b))
    if pe == 1:
        raise ValueError("kappa is undefined: both labellers always use one category")
    return float((po - pe) / (1 - pe))


def real_probe_not_measured() -> dict[str, Any]:
    """The real-image result when the optional probe does not exist."""
    return {"status": "not_measured", "n_images": 0, "cohen_kappa": None, "rows": []}


def real_probe_measured(
    labels_a: Sequence[Any], labels_b: Sequence[Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The real-probe result: aggregate rows and the kappa between the labellers, no per-image content."""
    n = len(labels_a)
    if not 1 <= n <= MAX_PROBE_IMAGES:
        raise ValueError(f"the real probe holds 1 to {MAX_PROBE_IMAGES} images, got {n}")
    kappa = cohen_kappa(labels_a, labels_b)
    for row in rows:
        if row.get("type") not in (1, 2, 3, 4, 5, 6):
            raise ValueError(f"row type {row.get('type')!r} is not a task-A question type")
    return {"status": "measured", "n_images": n, "cohen_kappa": kappa, "rows": [dict(r) for r in rows]}
