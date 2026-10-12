"""GNS export parity (FR-011-08, SC-011-04): ONNX Runtime CPU fp32 against PyTorch fp32 on golden steps, and the fp16 rule.

The tolerances are `models.onnx_cpu_fp32` of `thresholds.yaml` (rtol, atol, max abs); the fp16 acceptance limits are
`models.surrogate_fp16_rollout_delta` (repose in degrees, run-out relative), both read at call time, never copied here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import torch

from pitstudio.granular.graph import build_radius_graph
from pitstudio_pipeline.surrogates.gns.infer import INPUTS
from pitstudio_pipeline.surrogates.gns.model import HISTORY, GnsStep
from pitstudio_pipeline.surrogates.thresholds import model_threshold

MIN_GOLDEN = 200
_SIZES = (5, 11, 24, 40, 63, 97, 150)  # particle counts cycled through the golden steps


@dataclass(frozen=True)
class ParityReport:
    passed: bool
    n_golden: int
    max_abs: float
    max_rel: float
    tolerances: dict[str, float]
    worst_step: int


def golden_steps(model: GnsStep, n: int = MIN_GOLDEN, *, seed: int = 0) -> list[dict[str, np.ndarray]]:
    """`n` deterministic, valid GNS step inputs with particle counts that differ between steps."""
    rng = np.random.default_rng(seed)
    radius = model.connectivity_radius
    v_std = model.velocity_std.detach().cpu().numpy().astype(np.float64)
    steps = []
    for i in range(n):
        count = _SIZES[i % len(_SIZES)] + int(rng.integers(0, 4))
        side = 0.6 * radius * math.sqrt(count)  # about nine neighbours per particle
        pos = rng.uniform(0.0, side, (count, 2)).astype(np.float32)
        graph = build_radius_graph(pos, radius)
        steps.append(
            {
                "positions": pos,
                "velocities": (rng.normal(0.0, 1.0, (count, HISTORY, 2)) * v_std).astype(np.float32),
                "particle_type": rng.integers(0, model.n_particle_types, count).astype(np.int64),
                "bounds": np.array([0.0, 0.0, side, side], dtype=np.float32),
                "neighbour_index": graph.neighbour_index.astype(np.int64),
                "neighbour_mask": graph.neighbour_mask,
            }
        )
    return steps


def check_parity(model: GnsStep, onnx_path: str | Path, *, n_golden: int = MIN_GOLDEN, seed: int = 0) -> ParityReport:
    """Run the ONNX file (CPU provider) and `model` (PyTorch fp32) on the golden steps and compare (SC-011-04)."""
    if n_golden < MIN_GOLDEN:
        raise ValueError(f"at least {MIN_GOLDEN} golden steps are required, got {n_golden}")
    tol = model_threshold("onnx_cpu_fp32")
    tolerances = {"rtol": float(tol["rtol"]), "atol": float(tol["atol"]), "max_abs": float(tol["max_abs"])}
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    model = model.eval().float().cpu()
    max_abs = max_rel = 0.0
    worst, worst_step, passed = -1.0, 0, True
    for k, feed in enumerate(golden_steps(model, n_golden, seed=seed)):
        got = np.asarray(session.run(None, feed)[0], dtype=np.float64)
        with torch.no_grad():
            want = model(*[torch.from_numpy(feed[name]) for name in INPUTS]).numpy().astype(np.float64)
        diff = np.abs(got - want)
        bound = tolerances["atol"] + tolerances["rtol"] * np.abs(want)
        if not (np.isfinite(got).all() and bool((diff <= bound).all())):
            passed = False
        step_max = float(diff.max()) if np.isfinite(diff).all() else math.inf
        max_abs = max(max_abs, step_max)
        max_rel = max(max_rel, float((diff / np.maximum(np.abs(want), 1e-12)).max()))
        if step_max > worst:
            worst, worst_step = step_max, k
    if max_abs > tolerances["max_abs"]:
        passed = False
    return ParityReport(
        passed=passed, n_golden=n_golden, max_abs=max_abs, max_rel=max_rel, tolerances=tolerances, worst_step=worst_step
    )


def choose_live_precision(deltas: Sequence[Mapping[str, Any]]) -> str:
    """"fp16" iff every held-out geometry's fp16 rollout stays within the limits of FR-011-08 (inclusive), else "fp32".

    `deltas`: one {"geometry_id", "delta_repose_deg", "delta_runout_rel"} per geometry (absolute changes against the fp32
    rollout). No evidence, a non-finite or a negative delta keeps fp32.
    """
    if not deltas:
        return "fp32"
    limits = model_threshold("surrogate_fp16_rollout_delta")
    for delta in deltas:
        repose = delta.get("delta_repose_deg")
        runout = delta.get("delta_runout_rel")
        for value, limit in ((repose, limits["repose_deg"]), (runout, limits["runout_rel"])):
            if value is None or not math.isfinite(value) or value < 0 or value > limit:
                return "fp32"
    return "fp16"
