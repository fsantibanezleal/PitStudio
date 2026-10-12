"""Shared fake DEM simulator for the spec 011 calibration tests (T-011-033 ... T-011-039 and T-011-060).

The fake is an analytic stand-in for the Warp DEM repose response (plan 011 test strategy): the repose angle is
    theta(mu, seed) = a + b * mu + sigma * z(seed)        (z(seed) a standard normal from a generator seeded with the
                                                           packing seed: the same seed gives the same noise at every mu)
so the exact optimum of L(mu) = (theta - theta*)^2 is mu = (theta* - a - sigma z) / b, the exact gradient of theta is b,
and every call is counted. It implements the simulator protocol the calibration arms and the driver consume (see the
expected API in tests/unit/test_t_011_033_cmaes_arm.py): attributes `solver`, `differentiable`, `particle_count`,
`free_device_memory_bytes`; methods `theta(mu, seed)`, `hard_theta(mu, seed)` and `theta_and_grad(mu, seed)`.
"""

from __future__ import annotations

import numpy as np


def z_of(seed: int) -> float:
    return float(np.random.default_rng(seed).standard_normal())


class FakeDem:
    def __init__(
        self,
        a: float = 24.0,
        b: float = 20.0,
        sigma: float = 0.0,
        *,
        solver: str = "warp-dem",
        differentiable: bool = True,
        particle_count: int = 2000,
        free_device_memory_bytes: int = 2**40,
        flat_above: float | None = None,
        grad_scale: float = 1.0,
        hard_offset: float = 0.2,
    ) -> None:
        self.a, self.b, self.sigma = a, b, sigma
        self.solver = solver
        self.differentiable = differentiable
        self.particle_count = particle_count
        self.free_device_memory_bytes = free_device_memory_bytes
        self.flat_above = flat_above
        self.grad_scale = grad_scale
        self.hard_offset = hard_offset
        self.forward_calls: list[tuple[float, int]] = []
        self.grad_calls: list[tuple[float, int]] = []

    # ---- response
    def _mean(self, mu: float) -> float:
        m = mu if self.flat_above is None else min(mu, self.flat_above)
        return self.a + self.b * m

    def theta(self, mu: float, seed: int) -> float:
        self.forward_calls.append((float(mu), int(seed)))
        return self._mean(mu) + self.sigma * z_of(seed)

    def hard_theta(self, mu: float, seed: int) -> float:
        return self._mean(mu) + self.sigma * z_of(seed) + self.hard_offset

    def theta_and_grad(self, mu: float, seed: int) -> tuple[float, float]:
        """Forward pass with the tape plus the adjoint: theta and d theta / d mu (scaled by `grad_scale`)."""
        self.grad_calls.append((float(mu), int(seed)))
        slope = 0.0 if (self.flat_above is not None and mu > self.flat_above) else self.b
        return self._mean(mu) + self.sigma * z_of(seed), self.grad_scale * slope

    # ---- accounting (forward-equivalent simulations, spec FR-011-21: one adjoint pass counts as two)
    @property
    def equivalent_simulations(self) -> int:
        return len(self.forward_calls) + 3 * len(self.grad_calls)

    # ---- the loss the protocol minimises
    def loss(self, mu: float, seeds, theta_star: float) -> float:
        vals = [self._mean(mu) + self.sigma * z_of(s) - theta_star for s in seeds]
        return float(np.mean(np.square(vals)))


class FakeDem2:
    """Two-parameter fake for the optional (sliding, rolling) arm of FR-011-27.

    theta = a + b mu_s + c mu_r + sigma z(seed)   (repose angle, deg)
    q     = q0 (1 + k mu_s + m mu_r)              (hopper discharge rate, kg/s; noise-free)
    A small c and m make the rolling friction almost invisible (a weakly identified parameter).
    """

    solver = "warp-dem"
    differentiable = True

    def __init__(self, *, a=24.0, b=20.0, c=0.05, q0=2.0, k=0.5, m=0.0005, sigma=0.05, particle_count=2000) -> None:
        self.a, self.b, self.c, self.q0, self.k, self.m, self.sigma = a, b, c, q0, k, m, sigma
        self.particle_count = particle_count
        self.free_device_memory_bytes = 2**40
        self.calls: list[tuple[float, float, int]] = []

    def observables(self, mu_s: float, mu_r: float, seed: int) -> tuple[float, float]:
        self.calls.append((float(mu_s), float(mu_r), int(seed)))
        theta = self.a + self.b * mu_s + self.c * mu_r + self.sigma * z_of(seed)
        return theta, self.q0 * (1.0 + self.k * mu_s + self.m * mu_r)


def default_request(**overrides) -> dict:
    """A valid synthetic-truth calibration request (keys documented in
    tests/contract/test_t_011_036_calibration_result.py)."""
    req = {
        "kind": "synthetic-trial",
        "arm": "gradient",
        "trial_id": "trial-001",
        "target": {"theta_deg": 32.0, "packing_seed": 9001},
        "truth": {"sliding_friction": 0.40},
        "mu0": 0.55,
        "bounds": [0.1, 1.0],
        "budget": 60,
        "window_steps": 1000,
        "settling_steps": 20000,
        "packing_seeds": 2,
        "interval_runs": 8,
        "seeds": {
            "target": [9001],
            "optimisation": [9101, 9102],
            "interval": [9201 + i for i in range(8)],
            "gradient_check": [9301 + i for i in range(4)],
        },
        "particle_count": 2000,
        "adam_lr": 0.02,
        "cma_seed": 0,
        "secondary_arm": False,
        "solver_version": "1.17.0",
    }
    req.update(overrides)
    return req
