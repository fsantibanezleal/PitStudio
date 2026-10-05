"""Probe (studio env): supervised GPU stability test — VRAM pattern fill, PCIe copy loops, sustained compute.

Run it alone (`run_bench.py stress`), never as part of the default probe set. It is the check that decides whether a
machine is fit for long GPU runs: the runner's telemetry adds the PCIe replay-counter and WHEA (Windows hardware
error) deltas, and any pattern or copy mismatch fails the probe.
Environment: PITSTUDIO_STRESS_MINUTES (compute phase, default 10), PITSTUDIO_STRESS_RESERVE_MB (VRAM left free for
the display, default 2048).
"""

from __future__ import annotations

import os
import time
from typing import Any

from _common import run_probe

CHUNK = 1 << 26  # 64 Mi float32 = 256 MiB per allocation
COPY_MB, COPY_ROUNDS = 1024, 20


def body(r: dict[str, Any]) -> None:
    import numpy as np
    import warp as wp

    wp.config.quiet = True
    wp.init()
    if not wp.is_cuda_available():
        raise RuntimeError("Warp sees no CUDA device")
    dev = wp.get_cuda_device()
    r["versions"]["warp"] = wp.config.version
    r["metrics"]["device"] = dev.name
    minutes = float(os.environ.get("PITSTUDIO_STRESS_MINUTES", "10"))
    reserve = int(os.environ.get("PITSTUDIO_STRESS_RESERVE_MB", "2048")) * 2**20

    @wp.kernel
    def fill(a: wp.array(dtype=wp.uint32), seed: wp.uint32):  # type: ignore[valid-type]
        i = wp.tid()
        a[i] = wp.uint32(i) * wp.uint32(2654435761) ^ seed

    @wp.kernel
    def check(a: wp.array(dtype=wp.uint32), seed: wp.uint32, bad: wp.array(dtype=wp.int32)):  # type: ignore[valid-type]
        i = wp.tid()
        if a[i] != (wp.uint32(i) * wp.uint32(2654435761) ^ seed):
            wp.atomic_add(bad, 0, 1)

    @wp.kernel
    def burn(x: wp.array(dtype=float), iters: int):  # type: ignore[valid-type]
        i = wp.tid()
        v = x[i]
        for _ in range(iters):
            v = v * 0.999999 + 0.000001
        x[i] = v

    # 1. VRAM: fill free memory (minus the reserve) with a per-chunk pattern, then verify every word
    free = dev.free_memory if hasattr(dev, "free_memory") else dev.total_memory // 2
    n_chunks = max(1, int((free - reserve) // (CHUNK * 4)))
    bad = wp.zeros(1, dtype=wp.int32, device=dev)
    chunks = []
    t0 = time.perf_counter()
    for k in range(n_chunks):
        a = wp.empty(CHUNK, dtype=wp.uint32, device=dev)
        wp.launch(fill, dim=CHUNK, inputs=[a, wp.uint32(0x9E3779B9 + k)], device=dev)
        chunks.append(a)
    for k, a in enumerate(chunks):
        wp.launch(check, dim=CHUNK, inputs=[a, wp.uint32(0x9E3779B9 + k), bad], device=dev)
    wp.synchronize_device(dev)
    r["metrics"]["vram_tested_gb"] = round(n_chunks * CHUNK * 4 / 2**30, 2)
    r["metrics"]["vram_pattern_errors"] = int(bad.numpy()[0])
    r["metrics"]["vram_phase_s"] = round(time.perf_counter() - t0, 1)
    del chunks

    # 2. PCIe: round-trip host <-> device copies of a random buffer, byte-exact
    host = np.random.default_rng(0).integers(0, 2**32, COPY_MB * 2**18, dtype=np.uint32)
    d = wp.empty(host.shape[0], dtype=wp.uint32, device=dev)
    up = down = 0.0
    copy_errors = 0
    for _ in range(COPY_ROUNDS):
        t = time.perf_counter()
        wp.copy(d, wp.array(host, dtype=wp.uint32, device="cpu"))
        wp.synchronize_device(dev)
        up += time.perf_counter() - t
        t = time.perf_counter()
        back = d.numpy()
        down += time.perf_counter() - t
        copy_errors += int(np.count_nonzero(back != host))
    r["metrics"]["pcie_h2d_gbps"] = round(COPY_MB * COPY_ROUNDS / 1024 / up, 2)
    r["metrics"]["pcie_d2h_gbps"] = round(COPY_MB * COPY_ROUNDS / 1024 / down, 2)
    r["metrics"]["pcie_copy_word_errors"] = copy_errors
    del d

    # 3. Sustained compute for the requested minutes
    x = wp.array(np.ones(1 << 24, dtype=np.float32), device=dev)
    t0 = time.perf_counter()
    launches = 0
    while time.perf_counter() - t0 < minutes * 60:
        wp.launch(burn, dim=x.shape[0], inputs=[x, 2000], device=dev)
        wp.synchronize_device(dev)
        launches += 1
    r["metrics"]["compute_minutes"] = round((time.perf_counter() - t0) / 60, 2)
    r["metrics"]["compute_launches"] = launches
    if not np.all(np.isfinite(x.numpy())):
        raise AssertionError("non-finite values after the compute phase")
    if r["metrics"]["vram_pattern_errors"] or copy_errors:
        raise AssertionError(
            f"data corruption: {r['metrics']['vram_pattern_errors']} VRAM pattern errors, {copy_errors} copy errors"
        )


if __name__ == "__main__":
    run_probe("stress", "public", body)
