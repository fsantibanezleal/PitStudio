# DEC-0005: Performance data follows each licence

> Timings, telemetry and profiles of NVIDIA software covered by a benchmark clause (Kit, Isaac Sim, Replicator, the
> ovrtx/ovstage/ovphysx wheels, TensorRT for RTX) stay local-only; regular TensorRT numbers of PitStudio's own models,
> open-runtime timings and output quality are published. · Part of: [decisions](README.md) · Related:
> [lanes](../lanes.md) · [TensorRT](../../frameworks/tensorrt.md) · [Nsight and NVML](../../frameworks/nsight-nvml.md) ·
> [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md)

**Status:** Accepted, 2026-10-04

## Context

The studio's showcase is meant to show what each tool did on the reference GPU, including how long it took and how hard
the GPU worked. Some licences forbid exactly that:

- The NVIDIA Software License Agreement (2026-05-07), §8.9, forbids sharing "benchmarking … regression or performance
  data relating to the Software" without NVIDIA's written permission. It governs Kit, Isaac Sim, Replicator,
  ovrtx/ovstage and the ovphysx wheels [1].
- The TensorRT for RTX licence, §2.13, bans the same and is broader: it also covers performance data about NVIDIA GPUs [2].
- The regular TensorRT licence, both the documentation SLA [3] and the `LICENSE.txt` shipped in the TensorRT 11.3.0.99
  wheels, contains no benchmark, performance-data or competitive-analysis clause. PitStudio's bootstrap check confirmed
  that both 11.3.0.99 wheels ship the same `LICENSE.txt` (47,141 bytes, SHA-256
  `c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4`), whose only disclosure language concerns NVIDIA
  Confidential Information.

An earlier, conservative draft kept every NVIDIA number local. That would have hidden publishable, useful evidence
(how much TensorRT accelerates PitStudio's own models) for no legal reason.

## Decision

A per-licence rule, not a blanket one:

1. **Local-only.** No performance numbers of software covered by NVIDIA SLA §8.9 or TensorRT-for-RTX §2.13 are published
   unless NVIDIA grants written permission, which would then be recorded. Their timings, telemetry and Nsight summaries
   stay in git-ignored local run records under `PITSTUDIO_TMP` or the store. Public manifests carry an opaque
   `performance: local-only` marker for those stages, and the web app shows "measured locally, not published (licence)".
   The committed `studio/capabilities.json` uses the same wording for licence-restricted probe metrics.
2. **Published.** Latency and throughput of PitStudio's own models under regular TensorRT, with the governing licence text
   quoted in the repository and re-checked at every TensorRT upgrade; the capability probe pins the licence file by
   SHA-256, and if the text changes, the results drop to local-only automatically.
3. **Published without restriction.** Timings of open-source runtimes (PyTorch, ONNX Runtime, Warp, Newton, PitStudio's
   own code), output quality (accuracy, VMAF, sizes) and GPU telemetry of stages that run only open-source code or
   regular TensorRT. Each is labelled "our hardware, not a comparative benchmark".
4. **Outputs are not performance data.** Renders, synthetic datasets and captions produced by restricted tools are
   published under [DEC-0004](DEC-0004-proprietary-sdks-reference-only.md); only their timings stay local.
5. **Enforcement.** CI fails if a public manifest publishes a performance field for a stage marked
   `performance: local-only`. The guard is keyed on that marker, not on the `reference-only` licence class.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Blanket local-only for every NVIDIA tool | Simplest, most conservative | Hides publishable TensorRT evidence of our own models; not required by the regular TensorRT licence [3] | Over-restrictive |
| Publish everything, labelled "our hardware" | Most informative showcase | Breaches SLA §8.9 and TensorRT-for-RTX §2.13 [1] [2] | Licence violation |
| Ask NVIDIA for written permission first | Could unlock the showcase | Uncertain and slow; not needed for the core product | Remains possible later; the rule records any grant |

## Consequences

**Positive.** The showcase publishes every number it may legally publish and marks the rest clearly; the decision can
be audited from the manifests.

**Negative, accepted.** Studio tool pages for Isaac Sim, Kit, Replicator and ovrtx show outputs without timings; the
licence text must be re-checked at every TensorRT upgrade.

**Watch.** Changes to the NVIDIA SLA and the TensorRT and TensorRT-for-RTX licences; any written permission.

## References

1. NVIDIA Software License Agreement (2026-05-07), §8.9.
   https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-software-license-agreement/
2. NVIDIA TensorRT for RTX software license agreement, §2.13.
   https://docs.nvidia.com/deeplearning/tensorrt-rtx/latest/reference/sla.html
3. NVIDIA TensorRT software license agreement. https://docs.nvidia.com/deeplearning/tensorrt/latest/reference/sla.html
