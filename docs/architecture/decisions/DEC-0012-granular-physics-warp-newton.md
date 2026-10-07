# DEC-0012: Granular physics with an own Warp DEM and Newton implicit MPM

> Muck piles, bucket fill, stockpiles and run-out are simulated with PitStudio's own discrete-element kernels in Warp
> (Hertz–Mindlin contacts) and with Newton's implicit material-point solver, both Apache-2.0 and Windows-native, and
> validated against laboratory laws before any mining result is shown. · Part of: [decisions](README.md) · Related:
> [bulk flow, DEM and MPM](../../theory/bulk-flow-dem-mpm.md) · [M07 GPU granular physics](../../methods/m07-gpu-granular-physics.md) ·
> [Warp](../../frameworks/warp.md) · [Newton](../../frameworks/newton.md)

**Status:** Accepted, 2026-10-04

## Context

Cases A3 (loading and payload variance) and D1 (blast muck pile) need granular physics: how broken rock flows into a
bucket, piles up at its angle of repose and spreads. The discrete-element method (DEM) models each particle and its
contacts [1]; the material-point method (MPM) treats the material as a continuum with a granular yield law and handles
large deformation and tool interaction well [2] [3]. Requirements: run natively on Windows on the 16 GB GPU, be open
source and Apache-2.0-compatible, support differentiable calibration, and be validated.

- **Warp 1.17** (Apache-2.0) writes GPU kernels in Python, is differentiable, and since 1.15 has a deterministic mode for
  supported atomic operations [4] [5]. Its examples include a small DEM (a linear spring–dashpot model on 65,536
  particles) [6], a starting point rather than a calibrated solver.
- **Newton 1.6** (Apache-2.0, a Linux Foundation project) runs on Windows and Linux and includes an implicit MPM solver
  with Drucker–Prager rheology and coupling to rigid bodies, with granular and dam-break examples [7] [8] [9].
- **PhysX particles** in Omniverse are position-based dynamics for fluids and granular effects, GPU-only, with a particle
  schema that is not finalised [10]; they are not a calibrated granular model.
- **Genesis** (Apache-2.0) offers MPM and other solvers but requires Python < 3.14 [11].
- **Chrono DEM-Engine** (BSD-3) is a strong GPU DEM but publishes Linux wheels only and targets WSL2 on Windows [12] [13].
- MPM has been validated against the Beverloo discharge law and granular column-collapse scaling in the literature [14].

## Decision

- **DEM:** PitStudio's own Warp kernels with Hertz–Mindlin contacts, in `studio/` (Python 3.14); the contact and
  damping models are derived on [bulk flow, DEM and MPM](../../theory/bulk-flow-dem-mpm.md). Stages whose results feed parity or golden checks run Warp's deterministic mode;
  its cost is measured once by the bench.
- **MPM:** Newton's implicit MPM for bulk material, stockpiles, bucket penetration and the zero-shot check of the
  excavator policy (IL-2).
- **Validation first:** Beverloo discharge (±5 %), angle of repose (±1.5°), column collapse run-out (±5 %) and mass drift
  (< 0.5 %), as locked tests ([quality and validation](../quality-and-validation.md#physics-benchmarks)).
- **Calibration:** DEM friction parameters are recovered from repose targets with Warp's differentiable tape and compared
  with CMA-ES ([M09](../../methods/m09-differentiable-dem-calibration.md)).
- **Web:** granular runs are replayed as ≤ 10 MB quantized shards; a WGSL twin runs up to 2×10⁴ particles live with
  observable parity; a GNS surrogate trained on the runs runs live through ORT-web ([M08](../../methods/m08-gns-surrogate.md)).

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| PhysX particles (Isaac Sim / ovphysx) | Already inside the RTX stack; good visuals | Position-based particles, not a calibrated granular law; GPU-only; schema not final [10] | Visual twin only, not the physics of record |
| Genesis | Many solvers including MPM | Requires Python < 3.14 [11]; independent benchmarks question its headline speed claims [15] | Python pin and maturity |
| Chrono DEM-Engine as the primary engine | Mature GPU DEM with validation | Linux and WSL2 only [12] [13] | No native Windows path on the reference machine |
| A commercial DEM package | Calibrated material libraries | Closed and not reproducible by the public | Against the open-product goal |

## Consequences

**Positive.** Windows-native, open, differentiable granular physics with validation benchmarks as tests; one source for
replays, surrogates and live twins.

**Negative, accepted.** A DEM to write and calibrate; DEM parameters are non-unique, so calibration reports confidence
intervals rather than single values [16]; Newton's implicit MPM is not differentiable, so calibration uses the Warp DEM.

**Watch.** Newton releases (solver APIs, classifiers); Warp's deterministic-mode cost; VRAM use at the target particle
counts (an open measurement).

## References

1. Cundall, P. A., Strack, O. D. L. (1979). A discrete numerical model for granular assemblies. *Géotechnique*
   29(1):47–65. https://doi.org/10.1680/geot.1979.29.1.47
2. Klár, G. et al. (2016). Drucker–Prager elastoplasticity for sand animation. *ACM Transactions on Graphics* 35(4).
   https://doi.org/10.1145/2897824.2925906
3. Hu, Y. et al. (2018). A moving least squares material point method with displacement discontinuity and two-way rigid
   body coupling. *ACM Transactions on Graphics* 37(4). https://doi.org/10.1145/3197517.3201293
4. Warp repository. https://github.com/NVIDIA/warp
5. Warp changelog (deterministic atomics mode in 1.15.0). https://raw.githubusercontent.com/NVIDIA/warp/main/CHANGELOG.md
6. Warp DEM example. https://raw.githubusercontent.com/NVIDIA/warp/main/warp/examples/core/example_dem.py
7. Newton repository. https://github.com/newton-physics/newton
8. Newton `SolverImplicitMPM` documentation.
   https://newton-physics.github.io/newton/latest/api/_generated/newton.solvers.SolverImplicitMPM.html
9. Newton MPM examples. https://github.com/newton-physics/newton/tree/main/newton/examples/mpm
10. Omniverse Physics: particles. https://docs.omniverse.nvidia.com/kit/docs/omni_physics/latest/dev_guide/particles/particles.html
11. `genesis-world` on PyPI. https://pypi.org/pypi/genesis-world/json
12. Chrono DEM-Engine repository. https://github.com/projectchrono/DEM-Engine
13. `deme` on PyPI (Linux-only wheels). https://pypi.org/pypi/deme/json
14. Dunatunga, S., Kamrin, K. (2015). Continuum modelling and simulation of granular flows through their many phases.
    *Journal of Fluid Mechanics.* https://doi.org/10.1017/jfm.2015.383
15. An independent benchmark of the Genesis simulator. https://stoneztao.substack.com/p/the-new-hyped-genesis-simulator-is
16. Coetzee, C. J. (2017). Review: Calibration of the discrete element method. *Powder Technology* 310:104–142.
    https://doi.org/10.1016/j.powtec.2017.01.015
