"""Warp heap simulator for the calibration driver (FR-011-17): a loose column of grains collapses onto a flat plate.

`HeapSimulator` implements the simulator protocol of the driver on the differentiable DEM of `tape`:

- `theta(mu, seed)`: the packing seed jitters a lattice column of `particle_count` grains (radius `radius_m`) a few
grain diameters above
  the plate, the column collapses and settles for `settle_steps` unrecorded steps, the bin range of the observable is
  frozen, the
  window of `window_steps` steps runs and the smooth repose angle (FR-011-18) of the final heap is returned; the hard
  angle of the
  same run is kept for `hard_theta`;
- `theta_and_grad(mu, seed)`: the same run under the tape, returning the smooth angle and d theta / d mu_s (FR-011-19).

The sliding friction is the only parameter; rolling friction, restitution, modulus and density are held at the material
values given
(cited knowledge-table values, FR-011-17). `free_device_memory_bytes` comes from the Warp device (NVML-free: the CUDA
mempool free size)
and is infinite on the CPU.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import warp as wp

from pitstudio.calibration.errors import InvalidCalibrationError
from pitstudio_studio.physics.calibration import tape


@dataclass(frozen=True)
class HeapMaterial:
    """Grain material in SI units (values from the cited knowledge tables)."""

    density: float = 2650.0
    youngs_modulus: float = 50.0e6
    poisson_ratio: float = 0.25
    restitution: float = 0.5
    rolling_friction: float = 0.1


def column_scene(
    particle_count: int, radius_m: float, material: HeapMaterial, seed: int, *, column_radius_over_r: float = 8.0
) -> tape.TapeScene:
    """A jittered lattice column of `particle_count` grains above the plate z = 0, reproducible by `seed`."""
    if particle_count < 1:
        raise InvalidCalibrationError(f"particle_count must be at least 1, got {particle_count}")
    rng = np.random.default_rng(seed)
    spacing = 2.05 * radius_m
    half = math.ceil(column_radius_over_r * radius_m / spacing)
    lattice = [
        (i * spacing, j * spacing)
        for i in range(-half, half + 1)
        for j in range(-half, half + 1)
        if math.hypot(i * spacing, j * spacing) <= column_radius_over_r * radius_m
    ]
    per_layer = len(lattice)
    pos = np.zeros((particle_count, 3))
    for k in range(particle_count):
        layer, slot = divmod(k, per_layer)
        x, y = lattice[slot]
        shift = 0.5 * spacing if layer % 2 else 0.0
        pos[k] = (x + shift, y, radius_m + 1.5 * radius_m + layer * spacing)
    pos[:, :2] += rng.uniform(-0.02, 0.02, size=(particle_count, 2)) * radius_m
    pos[:, 2] += rng.uniform(0.0, 0.02, size=particle_count) * radius_m
    return tape.TapeScene(
        positions=pos,
        velocities=np.zeros_like(pos),
        radii=np.full(particle_count, radius_m),
        density=material.density,
        youngs_modulus=material.youngs_modulus,
        poisson_ratio=material.poisson_ratio,
        restitution=material.restitution,
        rolling_friction=material.rolling_friction,
    )


class HeapSimulator:
    """Protocol of the calibration driver on the differentiable Warp DEM (see the module docstring)."""

    solver = "warp-dem"
    differentiable = True
    deterministic_accumulation = True

    def __init__(
        self,
        *,
        particle_count: int,
        radius_m: float,
        settle_steps: int,
        window_steps: int,
        dt: float,
        material: HeapMaterial | None = None,
        device: str = "cuda:0",
        column_radius_over_r: float = 8.0,
        solver_version: str | None = None,
    ) -> None:
        self.particle_count = int(particle_count)
        self.radius_m = float(radius_m)
        self.settle_steps = int(settle_steps)
        self.window_steps = int(window_steps)
        self.dt = float(dt)
        self.material = material or HeapMaterial()
        self.device = device
        self.column_radius_over_r = column_radius_over_r
        self.solver_version = solver_version or f"pitstudio-tape-dem+warp{wp.__version__}"
        self._hard: dict[tuple[float, int], float] = {}

    @property
    def free_device_memory_bytes(self) -> float:
        if str(self.device).startswith("cuda"):
            free, _total = (
                wp.get_device(self.device).get_memory_info()
                if hasattr(wp.get_device(self.device), "get_memory_info")
                else (2**30, 0)
            )
            return float(free)
        return float("inf")

    def _scene(self, seed: int) -> tape.TapeScene:
        return column_scene(
            self.particle_count, self.radius_m, self.material, seed, column_radius_over_r=self.column_radius_over_r
        )

    def theta(self, mu: float, seed: int) -> float:
        run = tape.rollout_repose(
            self._scene(seed),
            mu,
            settle_steps=self.settle_steps,
            record_steps=self.window_steps,
            dt=self.dt,
            device=self.device,
            differentiate=False,
        )
        self._hard[(float(mu), int(seed))] = run.theta_hard_deg
        return run.theta_smooth_deg

    def hard_theta(self, mu: float, seed: int) -> float:
        key = (float(mu), int(seed))
        if key not in self._hard:
            self.theta(mu, seed)
        return self._hard[key]

    def theta_and_grad(self, mu: float, seed: int) -> tuple[float, float]:
        run = tape.rollout_repose(
            self._scene(seed),
            mu,
            settle_steps=self.settle_steps,
            record_steps=self.window_steps,
            dt=self.dt,
            device=self.device,
            differentiate=True,
        )
        self._hard[(float(mu), int(seed))] = run.theta_hard_deg
        assert run.gradient_deg_per_unit is not None
        return run.theta_smooth_deg, run.gradient_deg_per_unit


def simulator_factory(
    *,
    radius_m: float,
    settle_steps: int,
    window_steps: int,
    dt: float,
    device: str,
    material: HeapMaterial | None = None,
):
    """`factory(particle_count) -> HeapSimulator`, the form `calibrate_with_oom_fallback` takes."""

    def make(particle_count: int) -> HeapSimulator:
        return HeapSimulator(
            particle_count=particle_count,
            radius_m=radius_m,
            settle_steps=settle_steps,
            window_steps=window_steps,
            dt=dt,
            material=material,
            device=device,
        )

    return make


__all__: Sequence[str] = ["HeapMaterial", "HeapSimulator", "column_scene", "simulator_factory"]
