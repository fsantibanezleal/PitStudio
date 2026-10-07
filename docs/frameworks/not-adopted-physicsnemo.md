# NVIDIA PhysicsNeMo (evaluated, not adopted)

> NVIDIA's framework for physics-ML models, evaluated for the granular and field surrogates and not adopted because
> PitStudio's surrogates are small plain-PyTorch models that must also run in the browser. · Part of:
> [Frameworks](README.md) · Related: [PyTorch](pytorch.md) · [M08 GNS surrogate](../methods/m08-gns-surrogate.md) ·
> [M15 shallow-water FNO](../methods/m15-shallow-water-fno.md) · [GNS model card](../models/gns-granular.md)

## What and why

**PhysicsNeMo** (formerly Modulus) is NVIDIA's Apache-2.0 library of physics-ML architectures and training utilities,
including MeshGraphNet, Fourier neural operators (FNO), DeepONet and physics-informed networks [1][2]. PitStudio trains
two surrogates of exactly these kinds: a graph network simulator (GNS) of granular flow (M8) and an FNO of tailings
and dust fields (M15).

## What we evaluated

| Check | Finding |
|---|---|
| Version and licence | `nvidia-physicsnemo` 2.2.2, uploaded 2026-09-11, Apache-2.0 [1] |
| Windows | the wheel is `py3-none-any` and OS-independent, so it installs on Windows [1] |
| Python | `requires_python` ≥ 3.11, < 3.15 [1] |
| Dependencies | pulls in `hydra-core` ≥ 1.3.2; `hydra-core` 1.3.7 (2026-09-14) classifies Python 3.7–3.11 only, and its Python 3.14 behaviour is unverified [1][3] |
| Fit to our models | our GNS is pure-PyTorch message passing exported to ONNX; our FNO uses a DFT-as-matrix-multiply design so the same graph runs in WebGPU |

## Why not adopted

- **The models are small.** The GNS is about 3 MB and the FNO about 5 MB as ONNX, both under the 25 MB live-model cap.
  Plain PyTorch implements them in a few hundred lines that we own and test.
- **The browser decides the architecture.** Every surrogate must export to ONNX operators that ORT-web's WebGPU
  backend runs; a framework's general implementations would have to be re-exported and re-checked anyway
  ([ONNX Runtime](onnx-runtime.md)).
- **It adds a configuration stack** (`hydra-core`) whose classifiers stop at Python 3.11, in an environment pinned to
  3.14; PitStudio already configures recipes with JSON Schema and Pydantic.

## What PitStudio uses instead

| Surrogate | Implementation | Size as ONNX | Pre-registered acceptance |
|---|---|---|---|
| GNS 2-D (granular flow, M8) | pure-PyTorch message passing; a dense-adjacency export for small graphs, because ORT-web's WebGPU support for scatter operators is unconfirmed | about 3 MB, live | repose within ±1.5° and run-out within ±5 % on held-out geometries |
| FNO-2D (tailings and dust fields, M15) | spectral layers written as DFT matrix multiplies, so the browser runs the same graph | about 5 MB, live | relative L2 error ≤ 5 % on held-out terrains |

Both train in `pipeline/` with PyTorch 2.14.1 and are exported by `s60_export` with the opset and IR version pinned
([GNS model card](../models/gns-granular.md), [FNO model card](../models/fno-fields.md)).

## Assumptions and limits

- No PhysicsNeMo model was trained or timed; the decision rests on fit and dependency weight, not on accuracy.
- A mesh-based surrogate (for example MeshGraphNet on slope stress fields) would change the trade-off; it is not in the
  current method ladder.

## When to re-assess

- If the method ladder adds a **mesh-based** surrogate where MeshGraphNet's reference implementation would save real
  work.
- If `hydra-core` (or PhysicsNeMo's need for it) is resolved for Python 3.14.
- If a surrogate outgrows the browser and becomes precompute-only, so web export no longer constrains its design.

## In PitStudio

- Status: **evaluated, not adopted.** The surrogates are trained with PyTorch in `pipeline/` ([PyTorch](pytorch.md)).

## References

1. Python Package Index. *nvidia-physicsnemo* 2.2.2. https://pypi.org/project/nvidia-physicsnemo/
2. NVIDIA. *PhysicsNeMo repository*. https://github.com/NVIDIA/physicsnemo
3. Python Package Index. *hydra-core* 1.3.7. https://pypi.org/pypi/hydra-core/1.3.7/json
