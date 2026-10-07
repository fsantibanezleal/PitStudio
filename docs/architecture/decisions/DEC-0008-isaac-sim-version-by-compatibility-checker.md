# DEC-0008: The Isaac Sim version is chosen by on-machine checks

> PitStudio uses Isaac Sim 6.1.0 if NVIDIA's Compatibility Checker and a headless smoke test pass on the installed
> driver; otherwise 6.0.0.1, or 6.1 after the maintainer installs an R595 driver. The same principle (measure, do not
> assume) chooses the TensorRT and FFmpeg NVENC paths. · Part of: [decisions](README.md) · Related:
> [Isaac Sim + Replicator](../../frameworks/isaac-sim-replicator.md) · [capabilities probe](../../studio/capabilities-probe.md) ·
> [owner acts and licences](../../studio/owner-acts-and-licences.md)

**Status:** Accepted, 2026-10-04

## Context

The reference workstation runs driver 582.78 (R580 branch, CUDA 13.0). The published requirements disagree on whether
that is enough:

- Isaac Sim 6.1's requirements page lists driver 595.97 (Windows) and 595.58.03 (Linux) in all its columns. Those are
  the *tested* drivers. The same page offers a lightweight Compatibility Checker [1].
- The Omniverse technical requirements support Workstation GPUs on R580 from 581.42, and from 582.41 with the Windows
  update KB5074109 [2]. The ovrtx driver table says the same [3].
- Laptop GPUs are not listed in the Isaac Sim tables; 16 GB of VRAM is exactly the minimum class [1].
- GitHub releases show Isaac Sim 6.1.0 as the current release and 7.0.0a1 as an alpha pre-release [4].
- A driver update is an elevated install, which in this project is the maintainer's act, done with a declared purpose
  and only when needed.

## Decision

1. Install Isaac Sim 6.1.0 in `studio/isaac/` (Python 3.12, uv-managed), run NVIDIA's Compatibility Checker
   (`isaacsim[compatibility-check]`) [5] and a headless smoke test on 582.78.
2. If both pass, use 6.1.0.
3. If not, use 6.0.0.1, or 6.1 after the maintainer installs an R595 driver ≥ 595.97. The driver is requested only if the
   check fails, with the failure as its declared purpose.
4. The capability probe (`studio bench env`) records the outcome in the committed `studio/capabilities.json` without
   host identifiers; recipes that need Isaac Sim fail fast when the capability is missing.
5. **Same principle elsewhere.** The TensorRT version and the FFmpeg NVENC path are also chosen by on-machine smoke tests
   on the installed driver ([DEC-0010](DEC-0010-tensorrt-per-engine-parity.md), [DEC-0011](DEC-0011-nvenc-ffmpeg-8-1.md)).

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Assume a driver install is required | Matches the tested driver list | An elevated install that may be unnecessary; the Omniverse table supports R580 [2] | Measure first |
| Use Isaac Sim 7.0.0a1 | Newest features | Alpha pre-release [4] | Not stable enough for a reproducible studio |
| Stay on an older Isaac Sim permanently | Lower driver needs | Loses 6.1's Kit 110.3 and Newton integration | Only as a fallback |

## Consequences

**Positive.** No elevated install unless a measured failure requires it; the version in use is the newest one proven to
work on the machine, and the proof is committed.

**Negative, accepted.** The studio's NVIDIA lane cannot be confirmed until the probe runs; documentation states versions
as "6.1.0 if the checker passes".

**Watch.** Isaac Sim driver matrices and the Isaac Sim 7 timeline; the R595 branch for this laptop GPU.

**Status.** The probe is written but has not yet run on the reference machine. Its first run also needs the
maintainer's acceptance of the Isaac Sim EULA, an owner act.

## References

1. Isaac Sim 6.1 requirements. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html
2. Omniverse technical requirements (driver tables, KB5074109 note).
   https://docs.omniverse.nvidia.com/dev-guide/latest/common/technical-requirements.html
3. ovrtx driver requirements. https://nvidia-omniverse.github.io/ovrtx/driver_requirements.html
4. Isaac Sim releases. https://github.com/isaac-sim/IsaacSim/releases
5. Isaac Sim pip installation. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
