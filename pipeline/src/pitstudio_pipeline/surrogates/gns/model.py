"""GNS step (FR-011-01, FR-011-15, P-011-01, P-011-02, P-011-05): encode, M residual message-passing steps, decode, Euler.

Design (Sanchez-Gonzalez et al. 2020, "Learning to Simulate Complex Physics with Graph Networks"; the `geoelements/gns`
reference is cited, not copied): every MLP has two hidden layers of the latent width with ReLU; the encoders and the
processor MLPs end in a layer normalisation, the decoder does not. Node features are the C = 5 standardised velocities, a
type embedding and the four wall distances clipped at R; edge features are (x_i - x_j) / R and its norm. No absolute
position enters, so a shift of particles and bounds together changes nothing (P-011-02).

The neighbour layout is the padded one of FR-011-02: `neighbour_index` [N, K] lists the senders of particle i, the mask tells
the listed ones. "padded" aggregation gathers and sums the masked edge latents along K (Gather + ReduceSum in ONNX, the live
graph); "scatter" aggregation sums the same masked edges with `scatter_add` (ScatterElements in ONNX, bench only); the two
are equal up to the order of the additions (P-011-05).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import torch
from torch import nn
from torch.utils.checkpoint import checkpoint

from pitstudio.granular.errors import InvalidGraphError

HISTORY = 5  # C: velocities fed to the step
K_MAX = 32
TYPE_EMBEDDING = 16


def validate_gns_inputs(
    positions: object,
    velocities: object,
    particle_type: object,
    bounds: object,
    neighbour_index: object,
    neighbour_mask: object,
    *,
    n_particle_types: int,
) -> None:
    """Raise InvalidGraphError (naming the argument) unless the six inputs are those of FR-011-01 (FR-011-15).

    Accepts numpy arrays or torch tensors. Checked in the order of the arguments: shapes first, then values.
    """
    arrays = {
        "positions": _as_numpy(positions),
        "velocities": _as_numpy(velocities),
        "particle_type": _as_numpy(particle_type),
        "bounds": _as_numpy(bounds),
        "neighbour_index": _as_numpy(neighbour_index),
        "neighbour_mask": _as_numpy(neighbour_mask),
    }
    pos = arrays["positions"]
    if pos.ndim != 2 or pos.shape[1] != 2:
        raise InvalidGraphError(f"positions must have shape [N, 2], got {list(pos.shape)}")
    n = pos.shape[0]
    if n == 0:
        raise InvalidGraphError("positions: N = 0, there is no particle to step")
    shapes = {
        "velocities": (n, HISTORY, 2),
        "particle_type": (n,),
        "bounds": (4,),
        "neighbour_index": (n, K_MAX),
    }
    for name, shape in shapes.items():
        if tuple(arrays[name].shape) != shape:
            raise InvalidGraphError(f"{name} must have shape {list(shape)}, got {list(arrays[name].shape)}")
    if arrays["neighbour_mask"].shape != arrays["neighbour_index"].shape:
        raise InvalidGraphError(
            f"neighbour_mask must have the shape of neighbour_index {list(arrays['neighbour_index'].shape)}, "
            f"got {list(arrays['neighbour_mask'].shape)}"
        )
    if arrays["neighbour_mask"].dtype != np.bool_:
        raise InvalidGraphError(f"neighbour_mask must be boolean, got {arrays['neighbour_mask'].dtype}")
    for name in ("particle_type", "neighbour_index"):
        if not np.issubdtype(arrays[name].dtype, np.integer):
            raise InvalidGraphError(f"{name} must hold integers, got {arrays[name].dtype}")
    for name in ("positions", "velocities", "bounds"):
        if not np.isfinite(arrays[name]).all():
            raise InvalidGraphError(f"{name} contains a non-finite value")
    types = arrays["particle_type"]
    if types.min() < 0 or types.max() >= n_particle_types:
        raise InvalidGraphError(f"particle_type holds a type outside [0, {n_particle_types}): unknown particle type")
    index = arrays["neighbour_index"]
    if index.min() < 0 or index.max() >= n:
        raise InvalidGraphError(f"neighbour_index holds an index outside [0, {n})")


def _as_numpy(value: object) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    return np.asarray(value)


def _mlp(n_in: int, latent: int, n_out: int, *, norm: bool) -> nn.Sequential:
    layers: list[nn.Module] = [
        nn.Linear(n_in, latent),
        nn.ReLU(),
        nn.Linear(latent, latent),
        nn.ReLU(),
        nn.Linear(latent, n_out),
    ]
    if norm:
        layers.append(nn.LayerNorm(n_out))
    return nn.Sequential(*layers)


class _Processor(nn.Module):
    """One residual message-passing step: edge update, aggregation at the receiver, node update."""

    def __init__(self, latent: int) -> None:
        super().__init__()
        self.edge_mlp = _mlp(3 * latent, latent, latent, norm=True)
        self.node_mlp = _mlp(2 * latent, latent, latent, norm=True)

    def forward(
        self, h: torch.Tensor, e: torch.Tensor, index: torch.Tensor, mask: torch.Tensor, aggregation: str
    ) -> tuple[torch.Tensor, torch.Tensor]:
        k = e.shape[1]
        h_j = h[index]  # [N, K, L] senders (Gather)
        h_i = h.unsqueeze(1).expand(-1, k, -1)  # receivers
        e = e + self.edge_mlp(torch.cat([e, h_i, h_j], dim=-1))
        masked = e * mask.unsqueeze(-1).to(e.dtype)
        if aggregation == "padded":
            agg = masked.sum(dim=1)  # [N, L] (ReduceSum over the padded axis)
        else:  # "scatter": the same masked edges, summed at their receiver with scatter_add (bench only)
            n, latent = h.shape
            receiver = torch.arange(n, device=h.device).unsqueeze(1).expand(n, k).reshape(-1)
            agg = torch.zeros_like(h).scatter_add(0, receiver.unsqueeze(1).expand(-1, latent), masked.reshape(-1, latent))
        h = h + self.node_mlp(torch.cat([h, agg], dim=-1))
        return h, e


class GnsStep(nn.Module):
    """The GNS step: [positions, velocities, particle type, bounds, padded neighbours] -> acceleration (m/s^2)."""

    def __init__(
        self,
        *,
        connectivity_radius: float,
        frame_interval: float,
        n_particle_types: int,
        latent: int = 128,
        steps: int = 10,
        aggregation: str = "padded",
        acceleration_mean: Sequence[float] = (0.0, 0.0),
        acceleration_std: Sequence[float] = (1.0, 1.0),
        velocity_mean: Sequence[float] = (0.0, 0.0),
        velocity_std: Sequence[float] = (1.0, 1.0),
        checkpoint_steps: bool = False,
    ) -> None:
        super().__init__()
        if aggregation not in ("padded", "scatter"):
            raise ValueError(f"aggregation must be 'padded' or 'scatter', got {aggregation!r}")
        if connectivity_radius <= 0 or frame_interval <= 0 or n_particle_types < 1 or latent < 1 or steps < 1:
            raise ValueError("connectivity_radius, frame_interval, n_particle_types, latent and steps must be positive")
        self.latent = latent
        self.steps = steps
        self.history = HISTORY
        self.k_max = K_MAX
        self.connectivity_radius = float(connectivity_radius)
        self.frame_interval = float(frame_interval)
        self.n_particle_types = n_particle_types
        self.aggregation = aggregation
        self.checkpoint_steps = checkpoint_steps  # recompute the processor steps in the backward pass (memory for time)
        self.type_embedding = nn.Embedding(n_particle_types, TYPE_EMBEDDING)
        self.node_encoder = _mlp(2 * HISTORY + TYPE_EMBEDDING + 4, latent, latent, norm=True)
        self.edge_encoder = _mlp(3, latent, latent, norm=True)
        self.processor = nn.ModuleList(_Processor(latent) for _ in range(steps))
        self.decoder = _mlp(latent, latent, 2, norm=False)
        self.register_buffer("acceleration_mean", torch.tensor(acceleration_mean, dtype=torch.float32))
        self.register_buffer("acceleration_std", torch.tensor(acceleration_std, dtype=torch.float32))
        self.register_buffer("velocity_mean", torch.tensor(velocity_mean, dtype=torch.float32))
        self.register_buffer("velocity_std", torch.tensor(velocity_std, dtype=torch.float32))

    def set_normalisation(
        self,
        *,
        velocity_mean: Sequence[float],
        velocity_std: Sequence[float],
        acceleration_mean: Sequence[float],
        acceleration_std: Sequence[float],
    ) -> None:
        """Replace the standardisation statistics (in place); the export writes them into the graph."""
        for name, value in (
            ("velocity_mean", velocity_mean),
            ("velocity_std", velocity_std),
            ("acceleration_mean", acceleration_mean),
            ("acceleration_std", acceleration_std),
        ):
            tensor = torch.tensor(value, dtype=torch.float32, device=getattr(self, name).device)
            if tuple(tensor.shape) != (2,) or not bool(torch.isfinite(tensor).all()):
                raise ValueError(f"{name} must be two finite numbers")
            if name.endswith("_std") and bool((tensor <= 0).any()):
                raise ValueError(f"{name} must be positive")
            getattr(self, name).copy_(tensor)

    # ------------------------------------------------------------------ core (no input checks; used by training)

    def acceleration_unchecked(
        self,
        positions: torch.Tensor,
        velocities: torch.Tensor,
        particle_type: torch.Tensor,
        bounds: torch.Tensor,
        neighbour_index: torch.Tensor,
        neighbour_mask: torch.Tensor,
    ) -> torch.Tensor:
        """The network; `bounds` is [4] or one row per particle [N, 4] (training batches several geometries)."""
        n = positions.shape[0]
        r = self.connectivity_radius
        vel = (velocities - self.velocity_mean) / self.velocity_std
        b = bounds if bounds.dim() == 2 else bounds.unsqueeze(0)
        walls = torch.stack(
            [positions[:, 0] - b[:, 0], b[:, 2] - positions[:, 0], positions[:, 1] - b[:, 1], b[:, 3] - positions[:, 1]],
            dim=-1,
        )
        walls = torch.clamp(walls / r, -1.0, 1.0)  # wall distances clipped at R
        node_in = torch.cat([vel.reshape(n, 2 * HISTORY), self.type_embedding(particle_type), walls], dim=-1)
        h = self.node_encoder(node_in)
        sender_pos = positions[neighbour_index]  # [N, K, 2]
        rel = (positions.unsqueeze(1) - sender_pos) / r
        dist = torch.sqrt((rel * rel).sum(dim=-1, keepdim=True))
        e = self.edge_encoder(torch.cat([rel, dist], dim=-1))
        for block in self.processor:
            if self.checkpoint_steps and self.training and torch.is_grad_enabled():
                h, e = checkpoint(block, h, e, neighbour_index, neighbour_mask, self.aggregation, use_reentrant=False)
            else:
                h, e = block(h, e, neighbour_index, neighbour_mask, self.aggregation)
        return self.decoder(h) * self.acceleration_std + self.acceleration_mean

    # ------------------------------------------------------------------ public

    def forward(
        self,
        positions: torch.Tensor,
        velocities: torch.Tensor,
        particle_type: torch.Tensor,
        bounds: torch.Tensor,
        neighbour_index: torch.Tensor,
        neighbour_mask: torch.Tensor,
    ) -> torch.Tensor:
        if not (torch.jit.is_tracing() or torch.onnx.is_in_onnx_export()):
            validate_gns_inputs(
                positions,
                velocities,
                particle_type,
                bounds,
                neighbour_index,
                neighbour_mask,
                n_particle_types=self.n_particle_types,
            )
        return self.acceleration_unchecked(
            positions, velocities, particle_type, bounds, neighbour_index, neighbour_mask
        )

    def advance(
        self,
        positions: torch.Tensor,
        velocities: torch.Tensor,
        particle_type: torch.Tensor,
        bounds: torch.Tensor,
        neighbour_index: torch.Tensor,
        neighbour_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Semi-implicit Euler at the frame interval: v' = v_last + a dt, x' = x + v' dt, the history shifted by one."""
        acc = self.forward(positions, velocities, particle_type, bounds, neighbour_index, neighbour_mask)
        new_v = velocities[:, -1, :] + acc * self.frame_interval
        new_x = positions + new_v * self.frame_interval
        history = torch.cat([velocities[:, 1:, :], new_v.unsqueeze(1)], dim=1)
        return new_x, history
