"""GNS inference (s40_infer): ONNX Runtime step with the same input guards as PyTorch (FR-011-15), rollout adapters, flags.

`OrtGnsStep` validates its six inputs before the session is run, so a hostile call raises the same `InvalidGraphError`
(same messages) as the PyTorch model and the session never sees it. `make_surrogate` turns any acceleration function into
the `surrogate(initial_state, n_steps)` callable of `evaluate_held_out`, through the rollout loop of FR-011-12 / FR-011-13.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort

from pitstudio.granular.rollout import RolloutResult, run_rollout
from pitstudio_pipeline.surrogates.fixture import stamp
from pitstudio_pipeline.surrogates.gns.model import validate_gns_inputs

INPUTS = ("positions", "velocities", "particle_type", "bounds", "neighbour_index", "neighbour_mask")


class OrtGnsStep:
    """The exported GNS graph on ONNX Runtime; calling it returns the acceleration [N, 2] float32."""

    def __init__(
        self,
        onnx_path: str | Path,
        *,
        n_particle_types: int,
        providers: list[str] | None = None,
        frame_interval: float | None = None,
    ) -> None:
        self.n_particle_types = n_particle_types
        self.frame_interval = frame_interval
        self.session = ort.InferenceSession(str(onnx_path), providers=providers or ["CPUExecutionProvider"])

    def __call__(self, *arrays: np.ndarray) -> np.ndarray:
        if len(arrays) != len(INPUTS):
            raise TypeError(f"expected the six GNS inputs {INPUTS}, got {len(arrays)} arguments")
        validate_gns_inputs(*arrays, n_particle_types=self.n_particle_types)
        feed = dict(zip(INPUTS, arrays, strict=True))
        feed["positions"] = np.ascontiguousarray(feed["positions"], dtype=np.float32)
        feed["velocities"] = np.ascontiguousarray(feed["velocities"], dtype=np.float32)
        feed["bounds"] = np.ascontiguousarray(feed["bounds"], dtype=np.float32)
        feed["particle_type"] = np.ascontiguousarray(feed["particle_type"], dtype=np.int64)
        feed["neighbour_index"] = np.ascontiguousarray(feed["neighbour_index"], dtype=np.int64)
        feed["neighbour_mask"] = np.ascontiguousarray(feed["neighbour_mask"], dtype=np.bool_)
        return np.asarray(self.session.run(None, feed)[0], dtype=np.float32)

    def advance(self, *arrays: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Semi-implicit Euler with the graph's acceleration (needs `frame_interval`)."""
        if self.frame_interval is None:
            raise ValueError("OrtGnsStep.advance needs frame_interval")
        return euler_advance(self(*arrays), arrays[0], arrays[1], self.frame_interval)


def euler_advance(
    acceleration: np.ndarray, positions: np.ndarray, velocities: np.ndarray, dt: float
) -> tuple[np.ndarray, np.ndarray]:
    """v' = v_last + a dt, x' = x + v' dt, the history shifted by one (FR-011-01)."""
    new_v = velocities[:, -1, :] + acceleration * np.float32(dt)
    new_x = positions + new_v * np.float32(dt)
    history = np.concatenate([velocities[:, 1:, :], new_v[:, None, :]], axis=1)
    return new_x.astype(np.float32), history.astype(np.float32)


def torch_advance(model: Any) -> Callable[..., tuple[np.ndarray, np.ndarray]]:
    """The rollout step of a PyTorch `GnsStep` (numpy in, numpy out)."""
    import torch

    device = next(model.parameters()).device

    def step(pos, vel, types, bounds, index, mask):  # type: ignore[no-untyped-def]
        with torch.no_grad():
            args = [
                torch.as_tensor(np.asarray(a), device=device)
                for a in (pos, vel, types.astype(np.int64), bounds, index.astype(np.int64), mask)
            ]
            new_x, new_v = model.advance(*args)
        return new_x.cpu().numpy(), new_v.cpu().numpy()

    return step


def make_surrogate(
    advance: Callable[..., tuple[np.ndarray, np.ndarray]],
) -> Callable[[Mapping[str, Any], int], RolloutResult]:
    """`surrogate(initial_state, n_steps)` for `evaluate_held_out`: the rollout loop around a one-step `advance`."""

    def surrogate(state: Mapping[str, Any], n_steps: int) -> RolloutResult:
        return run_rollout(
            advance,
            state["positions"],
            state["velocities"],
            state["particle_type"],
            bounds=state["bounds"],
            radius=2.5 * float(state["d"]),
            n_steps=n_steps,
        )

    return surrogate


def stamp_rollout(record: Mapping[str, Any], dataset_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """The s40_infer record with `fixture: true` when the dataset is a fixture (FR-011-49)."""
    return stamp(record, dataset_manifest)
