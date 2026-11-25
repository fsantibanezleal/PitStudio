"""Footprint bench contract of the reason lane (FR-015-13, NFR-015-01, NFR-015-02, DC-015-07, DC-015-08).

`st59_reason_bench` measures, on 200 mixed queries (single 1280 x 720 images and 8-frame 640 x 360 sequences), the
device-peak VRAM, prefill and decode tokens/s and the wall time per query of the Q8_0 and BF16 paths. The numbers are
`public` (MIT runtime, open-model licence without a benchmark clause) and carry the label "our hardware, not a
comparative benchmark". This module builds and checks the `bench` object of `contracts/vlm-metrics.schema.json`, the
VRAM limits ("GB" is 10^9 bytes) and the GPU-time projection with its split over queue slots.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

LABEL = "our hardware, not a comparative benchmark"
PERFORMANCE = "public"
N_QUERIES = 200
FULL_CONTEXT = 16_384
VRAM_LIMITS = {"q8_0": 6_000_000_000, "bf16": 12_000_000_000}
KV_BYTES_PER_TOKEN = 2 * 28 * 8 * 128 * 2  # K and V, 28 layers, 8 KV heads, head size 128, 2 bytes
Q8_BLOCK_WEIGHTS, Q8_BLOCK_BYTES = 32, 34
MAX_SLOT_HOURS = 16.0


def bench_queries(seed: int = 0) -> list[dict[str, Any]]:
    """The 200 mixed queries: about half single 1280 x 720 images, half 8-frame 640 x 360 sequences, shuffled."""
    kinds = ["image"] * (N_QUERIES // 2) + ["sequence"] * (N_QUERIES - N_QUERIES // 2)
    random.Random(f"pitstudio-015-bench|{seed}").shuffle(kinds)
    return [
        {"kind": k, "frames": 1, "width_px": 1280, "height_px": 720}
        if k == "image"
        else {"kind": k, "frames": 8, "width_px": 640, "height_px": 360}
        for k in kinds
    ]


def vram_limit_bytes(path: str) -> int:
    if path not in VRAM_LIMITS:
        raise ValueError(f"unknown path {path!r}; known: {sorted(VRAM_LIMITS)}")
    return VRAM_LIMITS[path]


def within_vram_limit(path: str, peak_bytes: int, context_tokens: int = FULL_CONTEXT) -> bool:
    """True when the peak is within the path's limit. The limit is defined at the full context; a run at a smaller
    context is judged against the same limit and the verdict is only meaningful together with that context."""
    del context_tokens
    return peak_bytes <= vram_limit_bytes(path)


def kv_cache_bytes(tokens: int) -> int:
    if tokens < 0:
        raise ValueError("tokens must be non-negative")
    return KV_BYTES_PER_TOKEN * tokens


def weight_bytes(path: str, n_params: int) -> int:
    """Weight size: 2 bytes per parameter for BF16; Q8_0 blocks of 32 weights take 34 bytes."""
    if path == "bf16":
        return 2 * n_params
    if path == "q8_0":
        return n_params // Q8_BLOCK_WEIGHTS * Q8_BLOCK_BYTES
    raise ValueError(f"unknown path {path!r}")


def _finite_nonneg(name: str, value: float) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")
    return float(value)


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (the NumPy default) of a sorted list."""
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def summarise_path(
    path: str,
    *,
    vram_peak_bytes: int,
    prefill_tokens_per_s: float,
    decode_tokens_per_s: float,
    wall_s: Sequence[float],
    gpu: Mapping[str, str],
    context_tokens: int = FULL_CONTEXT,
) -> dict[str, Any]:
    """One measured `bench_path` of the metrics contract."""
    vram_limit_bytes(path)
    if not isinstance(context_tokens, int) or context_tokens < 1:
        raise ValueError("context_tokens must be a positive integer")
    if not isinstance(vram_peak_bytes, int) or isinstance(vram_peak_bytes, bool) or vram_peak_bytes < 0:
        raise ValueError("vram_peak_bytes must be a non-negative integer")
    prefill = _finite_nonneg("prefill_tokens_per_s", prefill_tokens_per_s)
    decode = _finite_nonneg("decode_tokens_per_s", decode_tokens_per_s)
    if len(wall_s) == 0:
        raise ValueError("no wall times")
    walls = sorted(_finite_nonneg("wall_s", w) for w in wall_s)
    return {
        "path": path,
        "status": "measured",
        "context_tokens": context_tokens,
        "vram_peak_bytes": vram_peak_bytes,
        "prefill_tokens_per_s": prefill,
        "decode_tokens_per_s": decode,
        "wall_s_per_query": {
            "mean": sum(walls) / len(walls),
            "p50": _percentile(walls, 0.5),
            "p95": _percentile(walls, 0.95),
        },
        "gpu": dict(gpu),
    }


def not_run_path(path: str, reason: str, context_tokens: int = FULL_CONTEXT) -> dict[str, Any]:
    """A `bench_path` that was not measured, with the measured reason."""
    vram_limit_bytes(path)
    return {
        "path": path,
        "status": "not_run",
        "reason": reason[:300],
        "context_tokens": context_tokens,
        "vram_peak_bytes": None,
        "prefill_tokens_per_s": None,
        "decode_tokens_per_s": None,
        "wall_s_per_query": None,
        "gpu": None,
    }


def build_bench(paths: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The `bench` object: measured, public, labelled, 200 queries."""
    return {
        "status": "measured",
        "performance": PERFORMANCE,
        "label": LABEL,
        "n_queries": N_QUERIES,
        "paths": [dict(p) for p in paths],
    }


def not_run_bench(reason: str) -> dict[str, Any]:
    return {
        "status": "not_run",
        "reason": reason,
        "performance": PERFORMANCE,
        "label": LABEL,
        "n_queries": N_QUERIES,
        "paths": [],
    }


def project_gpu_hours(seconds_per_query: float, n_queries: int) -> float:
    if not isinstance(n_queries, int) or n_queries < 0:
        raise ValueError("n_queries must be a non-negative integer")
    return _finite_nonneg("seconds_per_query", seconds_per_query) * n_queries / 3600.0


def split_workload(n_queries: int, hours: float, max_hours: float = MAX_SLOT_HOURS) -> list[int]:
    """Slot sizes (whole queries, summing to `n_queries`): one slot when the projection fits in `max_hours`, otherwise
    the fewest slots whose every projection fits; no sample size is reduced."""
    if not isinstance(n_queries, int) or n_queries < 1:
        raise ValueError("n_queries must be a positive integer")
    hours = _finite_nonneg("hours", hours)
    if hours <= max_hours:
        return [n_queries]
    slots = max(2, math.ceil(hours / max_hours))
    while slots < n_queries and math.ceil(n_queries / slots) * hours / n_queries > max_hours:
        slots += 1
    base, extra = divmod(n_queries, slots)
    return [base + (1 if i < extra else 0) for i in range(slots)]
