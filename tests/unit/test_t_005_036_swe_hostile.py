"""T-005-036 - FR-005-32: hostile shallow-water inputs are rejected before any kernel launch.

Oracle: the requirement itself, one case per condition it lists. Each bad input must raise a `PhysicsError` of class
`swe-input-invalid` whose message starts with that class, and Warp's `launch` must not have been called.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.errors import PhysicsError  # noqa: E402
from pitstudio_studio.physics.swe import Breach, SweParams, SweSimulation  # noqa: E402

Z = np.zeros((6, 8))
H = np.full((6, 8), 0.5)


def hole(a, value):
    out = a.copy()
    out[2, 3] = value
    return out


CASES = {
    "nan-terrain": dict(bed=hole(Z, np.nan)),
    "inf-terrain": dict(bed=hole(Z, np.inf)),
    "minus-inf-terrain": dict(bed=hole(Z, -np.inf)),
    "nan-depth": dict(depth=hole(H, np.nan)),
    "inf-depth": dict(depth=hole(H, np.inf)),
    "negative-depth": dict(depth=hole(H, -0.01)),
    "shape-mismatch": dict(depth=np.full((6, 9), 0.5)),
    "not-two-dimensional": dict(depth=np.full(48, 0.5)),
    "zero-cell-size": dict(dx=0.0),
    "negative-cell-size": dict(dx=-1.0),
    "nan-cell-size": dict(dx=float("nan")),
    "cfl-above-half": dict(params=SweParams(cfl=0.51)),
    "cfl-zero": dict(params=SweParams(cfl=0.0)),
    "cfl-negative": dict(params=SweParams(cfl=-0.1)),
    "cfl-nan": dict(params=SweParams(cfl=float("nan"))),
    "negative-yield-stress": dict(params=SweParams(tau_y=-1.0)),
    "negative-viscosity": dict(params=SweParams(mu_b=-0.5)),
    "zero-density": dict(params=SweParams(rho=0.0)),
    "negative-density": dict(params=SweParams(rho=-1000.0)),
    "zero-threshold": dict(params=SweParams(h_thr=0.0)),
    "negative-threshold": dict(params=SweParams(h_thr=-0.05)),
    "zero-gravity": dict(params=SweParams(gravity=0.0)),
    "zero-volume-hydrograph": dict(breach=Breach(cells=[(1, 1)], volume=0.0, peak_discharge=5.0)),
    "negative-volume-hydrograph": dict(breach=Breach(cells=[(1, 1)], volume=-3.0, peak_discharge=5.0)),
    "zero-peak-hydrograph": dict(breach=Breach(cells=[(1, 1)], volume=100.0, peak_discharge=0.0)),
    "negative-peak-hydrograph": dict(breach=Breach(cells=[(1, 1)], volume=100.0, peak_discharge=-1.0)),
    "peak-fraction-one": dict(breach=Breach(cells=[(1, 1)], volume=100.0, peak_discharge=5.0, peak_fraction=1.0)),
    "breach-cell-outside": dict(breach=Breach(cells=[(1, 99)], volume=100.0, peak_discharge=5.0)),
    "breach-without-cells": dict(breach=Breach(cells=[], volume=100.0, peak_discharge=5.0)),
    "unknown-boundary": dict(boundaries={"x-min": "periodic"}),
    "unknown-side": dict(boundaries={"z-min": "wall"}),
    "inflow-without-state": dict(boundaries={"x-min": "inflow"}),
    "inflow-negative-depth": dict(boundaries={"x-min": "inflow"}, inflow={"x-min": (-1.0, 0.0, 0.0)}),
    "inflow-on-a-wall": dict(inflow={"x-min": (1.0, 0.0, 0.0)}),
    "momentum-shape": dict(momentum=(np.zeros((6, 9)), np.zeros((6, 9)))),
    "momentum-nan": dict(momentum=(hole(Z, np.nan), Z)),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_hostile_input_is_rejected_with_the_error_class_and_no_kernel_launch(name):
    args = {"bed": Z, "depth": H, "dx": 1.0, **CASES[name]}
    with mock.patch("warp.launch") as launch, pytest.raises(PhysicsError) as caught:
        SweSimulation(args.pop("bed"), args.pop("depth"), device="cpu", **args)
    assert caught.value.error_class == "swe-input-invalid"
    assert str(caught.value).startswith("swe-input-invalid: ")
    launch.assert_not_called()


def test_advancing_to_a_time_in_the_past_is_rejected():
    s = SweSimulation(Z, H, dx=1.0, device="cpu")
    s.advance(0.5)
    with pytest.raises(PhysicsError, match="swe-input-invalid"):
        s.advance(0.1)
    with pytest.raises(PhysicsError, match="swe-input-invalid"):
        s.advance(float("nan"))


def test_a_valid_scenario_is_accepted_at_the_limits_of_the_rules():
    SweSimulation(Z, H, dx=1.0, device="cpu", params=SweParams(cfl=0.5, tau_y=0.0, mu_b=0.0, h_thr=1e-9))
    SweSimulation(Z, np.zeros_like(Z), dx=1.0, device="cpu", breach=Breach([(0, 0)], 1.0, 1e-3, 0.999))
