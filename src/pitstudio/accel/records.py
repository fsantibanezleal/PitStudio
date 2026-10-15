"""Bench records (DC-016-01): cell keys, the record builder and uniqueness (FR-016-32, FR-016-36)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

BACKENDS = ("pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt", "tensorrt-rtx")
PRECISIONS = ("fp32", "fp16", "int8", "fp8")


class InvalidRecord(ValueError):
    """A record or cell key that is discarded; `.reason` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def check_cell_key(backend: str, precision: str) -> None:
    """Backend and precision must be in their enums, otherwise the measurement is discarded."""
    if backend not in BACKENDS:
        raise InvalidRecord(f"invalid measurement: backend {backend!r} is not one of {', '.join(BACKENDS)}")
    if precision not in PRECISIONS:
        raise InvalidRecord(f"invalid measurement: precision {precision!r} is not one of {', '.join(PRECISIONS)}")


FINGERPRINT_FIELDS = (
    "gpu_name",
    "driver",
    "ort_version",
    "torch_version",
    "onnx_sha256",
    "engine_sha256",
    "power_limit_enforced_w",
    "power_source",
    "os_power_mode",
    "tensorrt_licence_sha256",
)


def make_bench_record(cell: Mapping[str, Any], *, run: Mapping[str, Any], fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    """A DC-016-01 record: schema version, run, measured cell, `performance` and the fingerprint (all fields present)."""
    missing = [f for f in FINGERPRINT_FIELDS if f not in fingerprint]
    if missing:
        raise InvalidRecord(f"fingerprint is missing {', '.join(missing)}")
    return {
        "schema_version": "1.0",
        "run_id": run["run_id"],
        "git_sha": run["git_sha"],
        "date": run["date"],
        **cell,
        "performance": "public",
        "fingerprint": dict(fingerprint),
    }


def check_unique_records(records: Sequence[Mapping[str, Any]]) -> None:
    """One record per model, backend, precision and TensorRT version."""
    seen: set[tuple[Any, ...]] = set()
    for record in records:
        key = (record["model"], record["backend"], record["precision"], record.get("tensorrt_version"))
        if key in seen:
            raise ValueError(f"duplicate bench record for {key[0]} / {key[1]} / {key[2]} / {key[3]}")
        seen.add(key)
