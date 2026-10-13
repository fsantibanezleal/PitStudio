# ruff: noqa: E501
"""T-014-061 (GPU, local): torch task cores against the NumPy references.

Requirements: P-014-15, FR-014-17, FR-014-18.

Spec: specs/014-robot-learning/spec.md P-014-15: "Task-reference parity: the vectorised FEE force and fill model used in the Isaac Lab task (float32, torch) match the NumPy float64 reference. Input domain: 10^4 random
admissible states. Tolerance: rtol 1e-5." (Section 7: float32 epsilon 1.19e-7 times a condition number of about 10^2.) Marked `gpu`: runs on the reference machine under the `gpu0.compute` lock, not in CI.

Oracle: the NumPy float64 reference of this repository (`pitstudio.robots.fee.solve_fee`, `pitstudio.robots.fill.cut_step`), themselves verified against the hand calculations and metamorphic relations of
T-014-020 to T-014-023; 10^4 random admissible states drawn here from the FR-014-19 soil ranges and the P-014-01 tool domain with a fixed seed.

Expected API of the implementation (module `pitstudio_isaaclab.parity` of the studio/isaaclab project): `python -m pitstudio_isaaclab.parity --input <states.npz> --output <out.npz> --device cuda` reads the arrays
alpha, delta, phi (rad), rho, c, c_a, q (SI), d, w (m) of shape (n,) and v_fill, ds, v_heaped (m3, m, m3) and writes, computed with the torch cores of the tasks in float32 on the device: `force` (the minimum FEE
force F of FR-014-17), `draft`, `vertical`, `beta` and `v_fill_next` (the fill model of FR-014-18 for one cutting step with the cap 1.15 V_h); the last stdout line is {"status": "pass", "n": int, "device": str}.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "support"))
import il_gpu_kit as kit  # noqa: E402

N = 10_000
DEG = math.pi / 180.0


def states(seed: int = 14061) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    phi = rng.uniform(25.0, 40.0, N) * DEG
    delta = np.minimum(rng.uniform(10.0, 25.0, N) * DEG, phi)
    c = rng.uniform(0.0, 20_000.0, N)
    out = {
        "alpha": rng.uniform(5.0, 90.0, N) * DEG, "delta": delta, "phi": phi, "rho": rng.uniform(1500.0, 2100.0, N), "c": c,
        "c_a": rng.uniform(0.0, 0.5, N) * c, "q": np.zeros(N), "d": rng.uniform(0.01, 2.0, N), "w": rng.uniform(0.5, 2.5, N),
        "v_fill": rng.uniform(0.0, 1.15, N), "ds": rng.uniform(0.0, 0.2, N), "v_heaped": rng.uniform(1.0, 3.0, N),  # v_fill is rescaled below to a fraction of the cap
    }  # fmt: skip
    out["v_fill"] = out["v_fill"] * out["v_heaped"]  # a fill below the cap 1.15 V_h: v_fill = u V_h with u in [0, 1.15)
    return out


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    from pitstudio.robots.fee import solve_fee
    from pitstudio.robots.fill import FILL_CAP

    s = states()
    tmp = tmp_path_factory.mktemp("il-parity")
    src, dst = tmp / "states.npz", tmp / "out.npz"
    np.savez(src, **s)
    info = kit.run_module("parity", "--input", str(src), "--output", str(dst), "--device", "cuda", timeout=900)
    out = dict(np.load(dst))
    ref = [
        solve_fee(
            alpha=s["alpha"][i],
            delta=s["delta"][i],
            phi=s["phi"][i],
            rho=s["rho"][i],
            c=s["c"][i],
            c_a=s["c_a"][i],
            q=0.0,
            d=s["d"][i],
            w=s["w"][i],
        )
        for i in range(N)
    ]
    gain = s["w"] * s["d"] * s["ds"]
    v_next = np.minimum(s["v_fill"] + gain, FILL_CAP * s["v_heaped"])
    return info, out, ref, v_next


@pytest.mark.gpu
@pytest.mark.req("P-014-15")
def test_the_task_ran_on_the_gpu_for_all_states(run) -> None:
    info, out, _ref, _v = run
    assert info["_returncode"] == 0
    assert info["status"] == "pass"
    assert info["n"] == N
    assert "cuda" in info["device"].lower() or "nvidia" in info["device"].lower()
    for k in ("force", "draft", "vertical", "beta", "v_fill_next"):
        assert out[k].shape == (N,)
        assert out[k].dtype == np.float32


@pytest.mark.gpu
@pytest.mark.req("P-014-15")
@pytest.mark.req("FR-014-17")
def test_the_torch_fee_force_matches_the_numpy_reference_to_rtol_1e_5(run) -> None:
    _info, out, ref, _v = run
    want = np.array([r.force for r in ref])
    np.testing.assert_allclose(out["force"].astype(np.float64), want, rtol=1e-5, atol=1e-6)


@pytest.mark.gpu
@pytest.mark.req("FR-014-17")
def test_the_draft_and_vertical_components_match(run) -> None:
    _info, out, ref, _v = run
    np.testing.assert_allclose(out["draft"].astype(np.float64), np.array([r.draft for r in ref]), rtol=1e-5, atol=1e-3)
    np.testing.assert_allclose(
        out["vertical"].astype(np.float64), np.array([r.vertical for r in ref]), rtol=1e-5, atol=1e-3
    )


@pytest.mark.gpu
@pytest.mark.req("P-014-15")
def test_the_failure_angle_agrees_where_the_minimum_is_sharp(run) -> None:
    _info, out, ref, _v = run
    want = np.array([r.beta for r in ref])
    # F is flat at its minimum: the force agrees to 1e-5 while beta only agrees to the flatness of F (see T-014-020); a loose bound
    np.testing.assert_allclose(out["beta"].astype(np.float64), want, atol=2e-3)


@pytest.mark.gpu
@pytest.mark.req("FR-014-18")
@pytest.mark.req("P-014-15")
def test_the_torch_fill_model_matches_the_numpy_reference(run) -> None:
    _info, out, _ref, v_next = run
    np.testing.assert_allclose(out["v_fill_next"].astype(np.float64), v_next, rtol=1e-5, atol=1e-7)
