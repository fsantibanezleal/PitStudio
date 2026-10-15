"""Which benchmark cells run on this machine and which are "not run" (FR-016-24)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CellStatus:
    status: str
    reason: str | None


def cell_status(backend: str, capabilities: Mapping[str, bool]) -> CellStatus:
    """`run` or `not_run` (with the missing piece named) for one backend."""
    cap = capabilities.get
    if backend in ("pytorch", "ort-cpu"):
        return CellStatus("run", None)
    if backend == "ort-cuda":
        return CellStatus("run", None) if cap("cuda_gpu") else CellStatus("not_run", "no CUDA GPU")
    if backend == "tensorrt":
        missing = []
        if not cap("tensorrt_11"):
            missing.append("TensorRT 11.3 is not importable")
        if not cap("cuda13_runtime"):
            missing.append("CUDA 13 runtime wheel is missing")
        if not cap("cuda_gpu"):
            missing.append("no CUDA GPU")
        return CellStatus("not_run", "; ".join(missing)) if missing else CellStatus("run", None)
    if backend == "ort-tensorrt":
        missing = []
        if not cap("tensorrt_10_14_lock"):
            missing.append("TensorRT 10.14 libraries not in the pipeline lock")
        if not cap("cuda_gpu"):
            missing.append("no CUDA GPU")
        return CellStatus("not_run", "; ".join(missing)) if missing else CellStatus("run", None)
    raise ValueError(f"unknown backend {backend!r}")
