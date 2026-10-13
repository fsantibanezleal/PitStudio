"""The transformers BF16 reference of the Cosmos model (FR-015-09, FR-015-10).

The reference runs the pinned official revision with transformers in bfloat16 from the verified local snapshot (never
a branch name) and is the quality reference of the agreement gate and the native-video path of task B. If it cannot
load or run on the reference GPU, the BF16 arm is "not run" with the measured reason and every Cosmos Q8_0 result is
"not run (agreement gate not evaluable)"."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pitstudio.reason.gate import NOT_EVALUABLE, mark_not_run, not_run_gate

MAX_REASON = 300


def reference_config(pins: Mapping[str, Any]) -> dict[str, Any]:
    cosmos = pins["models"]["cosmos"]
    return {
        "repository": cosmos["repository"],
        "revision": cosmos["revision"],
        "dtype": "bfloat16",
        "library": "transformers",
        "local_files_only": True,
    }


def _reason(exc: BaseException) -> str:
    """`ClassName: first line of the message`, one line of at most 300 characters."""
    lines = str(exc).splitlines()
    first = lines[0] if lines else ""
    text = f"{type(exc).__name__}: {first}" if first.strip() else type(exc).__name__
    return text[:MAX_REASON]


def attempt_bf16(loader: Callable[[], Any]) -> dict[str, Any]:
    """Call the loader: `available` with its model, or `not_run` with the measured reason (KeyboardInterrupt and
    SystemExit propagate)."""
    try:
        return {"status": "available", "model": loader()}
    except Exception as exc:
        return {"status": "not_run", "reason": _reason(exc)}


def degrade_for_missing_bf16(
    state: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """For a `not_run` state: the not-run gate and the rows with every Cosmos result not run (Q8_0: "agreement gate not
    evaluable"; BF16: the measured reason). For an available reference: `(None, rows)` unchanged."""
    if state["status"] != "not_run":
        return None, [dict(r) for r in rows]
    reason = state["reason"]
    gate = not_run_gate(f"BF16 reference not run: {reason}"[:MAX_REASON])
    out = []
    for row in rows:
        if row["arm"] == "cosmos-q8_0":
            out.append(mark_not_run(row, NOT_EVALUABLE))
        elif row["arm"] == "cosmos-bf16":
            out.append(mark_not_run(row, reason))
        else:
            out.append(dict(row))
    return gate, out


def load_reference(snapshot: str, pins: Mapping[str, Any]) -> Any:
    """Load the BF16 reference from the verified snapshot (GPU; imported lazily). Returns `(model, processor)`."""
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    cfg = reference_config(pins)
    model = AutoModelForImageTextToText.from_pretrained(
        snapshot, torch_dtype=torch.bfloat16, device_map="cuda", local_files_only=cfg["local_files_only"]
    )
    processor = AutoProcessor.from_pretrained(snapshot, local_files_only=cfg["local_files_only"])
    return model, processor
