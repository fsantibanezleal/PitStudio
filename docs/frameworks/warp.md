# NVIDIA Warp

> The Python GPU kernel language that carries PitStudio's own physics: the granular DEM, the tailings shallow-water
> solver, the dust particles and the differentiable friction calibration. · Part of: [Frameworks](README.md) ·
> Related: [Newton](newton.md) · [M07 GPU granular physics](../methods/m07-gpu-granular-physics.md) ·
> [M09 differentiable DEM calibration](../methods/m09-differentiable-dem-calibration.md) ·
> [DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md)

## What and why

Warp compiles Python functions decorated with `@wp.kernel` into CUDA (or CPU) kernels, with spatial types, hash-grid
neighbour queries and a tape for automatic differentiation [1][2]. PitStudio writes its own physics in Warp rather
than adopting a black-box engine, for three reasons:

- **An owned, testable core.** The repo's DEM and MPM are short enough to read, cite and property-test. They mirror
  one-to-one in WGSL for the browser, which makes Python-to-browser parity tests possible.
- **Determinism when it matters.** Warp 1.15 (2026-07-07) added deterministic atomic modes (`RUN_TO_RUN`,
  `GPU_TO_GPU`) that remove run-to-run variation of atomic accumulation [3]. Reference runs that feed parity or golden
  checks use them, at a cost measured once by the bench.
- **Differentiability.** `wp.Tape` gives gradients through our own kernels, which is what the DEM friction
  calibration (M9) needs. Newton's implicit MPM is not differentiable [4].

Rejected alternatives for the granular core ([DEC-0012](../architecture/decisions/DEC-0012-granular-physics-warp-newton.md)):

| Alternative | Why not |
|---|---|
| PhysX particles | Position-based dynamics: animation-grade, no calibrated constitutive model; schema "not finalized" [5] |
| Genesis | Published speed claims were about 150× lower in an independent re-run; Python below 3.14 [6][7] |
| DEM-Engine (DEME) as the primary engine | Linux-only wheels, so Windows needs WSL2 [8] |
| Taichi | No release since 2025-07-31 [9] |
| `warp.sim` | Removed in Warp 1.10 in favour of Newton [2] |

## Identity

| Item | Value |
|---|---|
| Package | `warp-lang` 1.17.0, pinned in `studio/uv.lock` (also resolved in `studio/isaac/` and `studio/rtx/`) |
| Release | 2026-08-31 [1] |
| Licence | Apache-2.0; the bundled `libmathdx` is under the NVIDIA Software License Agreement [10] |
| Class | open (used as a dependency, never vendored) |
| Ring | Adopt |
| Environment | `studio/` (Python 3.14) |
| GPU | PyPI wheels are built against CUDA 12.9; separate CUDA 13 wheels need an R580+ driver and compute capability ≥ 7.5 [11] |

## How PitStudio uses it

| Kernel family | Model | Case | Validation target |
|---|---|---|---|
| Soft-sphere DEM | Hertz normal + Mindlin tangential spring, Coulomb cap, rolling resistance; `HashGrid` neighbours [12] | A3, D1 (muck piles, bucket fill, chutes) | Beverloo discharge with exponent 5/2; angle of repose ([Bulk flow](../theory/bulk-flow-dem-mpm.md)) |
| Explicit MLS-MPM sand | Drucker–Prager return mapping [13] | reference twin of the WGSL kernel | Column-collapse run-out scaling |
| Depth-averaged shallow water | finite-volume, HLL / Rusanov flux, Bingham / Voellmy basal resistance | C2 (tailings run-out, pit flooding) | Dam-break front ([Tailings](../theory/tailings.md)) |
| Lagrangian dust | Stokes drag, settling, stochastic dispersion; AP-42 source term | C3 | Analytic settling velocity, mass balance ([Dust](../theory/dust.md)) |
| Calibration | `wp.Tape` gradients of repose and run-out losses w.r.t. friction | M9 | 95 % CI covers the synthetic truth in ≥ 90 % of trials |

Shipped Warp examples are scaffolds only. The DEM example uses a linear spring–dashpot with Coulomb-capped friction
and forward Euler; it is not Hertz–Mindlin and has no calibrated material [12].

Stages: `st50_physics` (scenarios at roughly 1–2 per hour, measured by the runner), `st45_validate` checks. Kernels run
under the `gpu0.compute` lock. Profiling uses `wp.ScopedTimer(..., use_nvtx=True)` so stage timelines show the kernels
([Nsight / NVML](nsight-nvml.md)) [14].

Artefacts it will produce: particle replays and field shards (Zarr), aggregate observables (Parquet), a loss
landscape for M9, and a determinism-mode cost table. GPU telemetry of these open-runtime stages is publishable.

## Licence and redistribution

Apache-2.0 for Warp itself. `libmathdx` inside the wheel is NVIDIA-licensed, so the wheel is installed from PyPI and
never copied into the repo or a release [10].

## Assumptions and limits

- Autodiff limits for atomics and in-place writes are **UNVERIFIED** (the differentiability page was unreachable
  during research); M9 tests gradients against finite differences before trusting them.
- Real rock stiffness forces tiny Hertz time steps. A reduced Young's modulus is standard practice and must be shown
  not to shift the repose and Beverloo targets.
- Throughput on the 16 GB laptop GPU is an open measurement. The bench records particle-steps per second; nothing is
  extrapolated from desktop numbers.
- No float atomics in WGSL: the browser twin uses fixed-point scatter, so parity is statistical, never bitwise.

## In PitStudio

- Probe: `probe_warp_newton.py` runs a 16 M-element saxpy and checks the result exactly
  ([Capabilities probe](../studio/capabilities-probe.md)). A one-off Warp + Newton GPU smoke on Python 3.14 passed
  during research; the committed probe has **not yet run** on the reference machine.
- Status of the physics kernels: **not yet run** — produced in the data-and-models phase. They are written test-first in the build phase, against the
  benchmarks above.

## References

1. Python Package Index. *warp-lang* 1.17.0. https://pypi.org/project/warp-lang/
2. NVIDIA. *Warp releases* (`warp.sim` removed in 1.10). https://github.com/NVIDIA/warp/releases
3. NVIDIA. *Warp CHANGELOG* (deterministic atomics, 1.15.0).
   https://raw.githubusercontent.com/NVIDIA/warp/main/CHANGELOG.md
4. Newton. *SolverImplicitMPM API*.
   https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
5. NVIDIA. *Omni Physics particles*. https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
6. S. Tao (2024). *The new hyped Genesis simulator is up to 10x slower*.
   https://stoneztao.substack.com/p/the-new-hyped-genesis-simulator-is
7. Python Package Index. *genesis-world*. https://pypi.org/pypi/genesis-world/json
8. Python Package Index. *deme* 3.0.14 (Linux-only wheels). https://pypi.org/pypi/deme/json
9. Taichi. *Releases*. https://github.com/taichi-dev/taichi/releases
10. NVIDIA. *Warp README* (licence, `libmathdx`). https://github.com/NVIDIA/warp
11. NVIDIA. *Warp installation guide*. https://nvidia.github.io/warp/stable/user_guide/installation.html
12. NVIDIA. *Warp DEM example*. https://raw.githubusercontent.com/NVIDIA/warp/main/warp/examples/core/example_dem.py
13. G. Klár et al. (2016). *Drucker–Prager elastoplasticity for sand animation*. ACM TOG 35(4). DOI
    10.1145/2897824.2925906
14. NVIDIA. *Warp profiling*. https://nvidia.github.io/warp/stable/user_guide/execution_and_performance/profiling.html
