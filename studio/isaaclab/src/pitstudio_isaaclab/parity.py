# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""Task-reference parity of the torch cores (T-014-061, P-014-15).

``python -m pitstudio_isaaclab.parity --input states.npz --output out.npz --device cuda`` reads the arrays alpha, delta, phi,
rho, c, c_a, q, d, w, v_fill, ds and v_heaped, computes the minimum FEE force and one fill step with the float32 torch cores
and writes force, draft, vertical, beta and v_fill_next. ``--dry-run`` asserts a CUDA device is visible, then runs the same
code path on the CPU for 256 states against the NumPy float64 reference and stops before any CUDA work.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

from pitstudio_isaaclab import runtime
from pitstudio_isaaclab.cores import FILL_CAP, fill_step, solve_fee

NAMES = ("alpha", "delta", "phi", "rho", "c", "c_a", "q", "d", "w")


def compute(arrays: dict[str, np.ndarray], device: str) -> dict[str, np.ndarray]:
    t = {k: torch.as_tensor(np.asarray(v), dtype=torch.float32, device=device) for k, v in arrays.items()}
    fee = solve_fee(**{k: t[k] for k in NAMES})
    v_next = fill_step(t["v_fill"], depth=t["d"], ds=t["ds"], width=t["w"], v_heaped=t["v_heaped"])
    out = {k: v.detach().cpu().numpy() for k, v in fee.items()}
    out["v_fill_next"] = v_next.detach().cpu().numpy()
    return out


def _dry_states(n: int = 256) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(14061)
    deg = np.pi / 180.0
    phi = rng.uniform(25.0, 40.0, n) * deg
    c = rng.uniform(0.0, 20_000.0, n)
    v_h = rng.uniform(1.0, 3.0, n)
    return {
        "alpha": rng.uniform(5.0, 90.0, n) * deg, "delta": np.minimum(rng.uniform(10.0, 25.0, n) * deg, phi), "phi": phi,
        "rho": rng.uniform(1500.0, 2100.0, n), "c": c, "c_a": rng.uniform(0.0, 0.5, n) * c, "q": np.zeros(n),
        "d": rng.uniform(0.01, 2.0, n), "w": rng.uniform(0.5, 2.5, n), "v_fill": rng.uniform(0.0, 1.15, n) * v_h,
        "ds": rng.uniform(0.0, 0.2, n), "v_heaped": v_h,
    }  # fmt: skip


def _check_against_numpy(s: dict[str, np.ndarray], out: dict[str, np.ndarray]) -> float:
    from pitstudio.robots.fee import solve_fee as ref_solve

    worst = 0.0
    for i in range(len(s["alpha"])):
        ref = ref_solve(**{k: float(s[k][i]) for k in NAMES})
        worst = max(worst, abs(float(out["force"][i]) - ref.force) / abs(ref.force))
        want_v = min(float(s["v_fill"][i]) + s["w"][i] * s["d"][i] * s["ds"][i], FILL_CAP * s["v_heaped"][i])
        worst = max(worst, abs(float(out["v_fill_next"][i]) - want_v) / want_v)
    return worst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--make-states", type=Path, help="write the 10^4 admissible states of the T-014-061 test and exit"
    )
    parser.add_argument(
        "--check", action="store_true", help="also compare with the NumPy float64 reference (adds the error)"
    )
    args = parser.parse_args(argv)
    if args.make_states is not None:
        args.make_states.parent.mkdir(parents=True, exist_ok=True)
        np.savez(args.make_states, **_dry_states(10_000))
        runtime.emit({"status": "pass", "n": 10_000, "states": str(args.make_states)})
        return 0
    if args.dry_run:
        device_name = runtime.require_cuda()
        s = _dry_states()
        worst = _check_against_numpy(s, compute(s, "cpu"))
        ok = worst < 1e-5
        runtime.emit(
            {"status": "dry-run-ok" if ok else "fail", "n": 256, "device": device_name, "worst_rel_error_cpu": worst}
        )
        return 0 if ok else 1
    if args.input is None or args.output is None:
        parser.error("--input and --output are required")
    runtime.require_cuda()
    with np.load(args.input) as data:
        arrays = {k: data[k] for k in data.files}
    with runtime.gpu_session():
        out = compute(arrays, args.device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.output, **out)
    result = {"status": "pass", "n": len(arrays["alpha"]), "device": args.device}
    if args.check:
        worst = _check_against_numpy(arrays, out)
        result.update(worst_rel_error=worst, status="pass" if worst < 1e-5 else "fail")
    runtime.emit(result)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
