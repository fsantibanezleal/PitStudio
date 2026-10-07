# PyTorch

> The training framework for every learned model in PitStudio, run on the CUDA 13 wheel line in the pipeline
> environment and pinned separately where NVIDIA runtimes need their own version. · Part of: [Frameworks](README.md) ·
> Related: [ONNX Runtime](onnx-runtime.md) · [TensorRT](tensorrt.md) · [Training recipes](../models/training-recipes.md) ·
> [Pipeline stages](../pipelines/pipeline-stages.md)

## What and why

PyTorch trains all eleven learned methods of the method ladder: detectors (D-FINE), instance segmentation (RF-DETR-Seg),
the fragmentation U-Net, the GNS and FNO surrogates, the PPO and attention dispatch policies, the slope forecasters and
the mine-to-mill meta-model ([Models](../models/README.md)). Isaac Lab policies train with PyTorch inside their own
environment.

Why PyTorch: it is the framework every chosen model ships for; it has CUDA wheels for Windows and Python 3.14; its
ONNX exporter feeds both the browser and TensorRT. Rejected: JAX (no NVIDIA GPU support on native Windows) [1];
PhysicsNeMo as a model library ([PhysicsNeMo, not adopted](not-adopted-physicsnemo.md)).

## Identity

| Environment | Version in the lock | Wheel index | Why this version |
|---|---|---|---|
| `pipeline/` | **2.14.1**, torchvision 0.29.1 | three mutually exclusive extras: `cpu`, `cu126` (driver ≥ 525), `cu130` (driver ≥ 580) | the current release; cp314 Windows wheels exist on all three indexes [2][3] |
| `studio/isaac/` | 2.11.0+cu130, torchvision 0.26.0 | cu130 | Isaac Sim's pip guide installs `torch==2.11.0` [4] |
| `studio/isaaclab/` | 2.11.0+cu128 | cu128 | the Isaac Lab v3.0.0-EA tested pin ([Isaac Lab](isaac-lab.md)) |

| Item | Value |
|---|---|
| Release | 2.14.1 uploaded 2026-09-30 [5] |
| Licence | BSD-3-style (multiple licence files) [5] · open |
| Ring | Adopt |
| Reference machine | driver R580 → the `cu130` extra; CI uses `cpu` |

The extras are declared conflicting in `pipeline/pyproject.toml`, so a lock can never mix CPU and CUDA builds.

## How PitStudio uses it

- **Stage `s30_train`** in `pipeline/`, with estimated budgets (for example D-FINE 12–25 GPU-hours at 8–11 GB;
  U-Net 2–4 GPU-hours) ([Training recipes](../models/training-recipes.md)).
- **Export** via `torch.onnx` (dynamo exporter) with an **explicit** opset, because the default opset is not
  documented [6], and an explicit ONNX IR version ([ONNX Runtime](onnx-runtime.md)).
- **VRAM guard:** `torch.cuda.memory.set_per_process_memory_fraction` makes an over-allocation raise an out-of-memory
  error in the allocator instead of starving other work [7]; the runner sets it from the recipe.
- **Determinism:** evaluation runs set `torch.use_deterministic_algorithms(True)` and `cudnn.benchmark = False`; PyTorch
  itself warns that full reproducibility is not guaranteed across releases or platforms [8].
- **Profiling without admin:** `torch.profiler` traces device kernels through CUPTI and exports Chrome JSON [9]
  ([Nsight / NVML](nsight-nvml.md)).

Artefacts it will produce: checkpoints (local, git-ignored), training curves, model cards and ONNX exports with parity
reports.

## Licence and redistribution

BSD-style: free to depend on. Trained weights are Apache-2.0 plus attribution when all inputs permit; otherwise the
most restrictive input licence, stated in the model card.

## Assumptions and limits

- The torch versions differ between environments by design. A model trained in `pipeline/` crosses into another
  environment only as an ONNX file.
- Laptop training throughput is an open measurement; the bench records fp16 and bf16 GEMM throughput and parity
  before any long run.
- Results of training are reported by the pre-registered decision rule: "better" only when the paired 95 % CI of the
  difference excludes 0 ([DEC-0016](../architecture/decisions/DEC-0016-pre-registered-decision-rule.md)).

## In PitStudio

- Probe: `probe_torch_ort.py` measures fp16 and bf16 GEMM throughput at 4096² and checks torch (cuDNN) against the ONNX
  Runtime CUDA execution provider on the same tiny graph ([Capabilities probe](../studio/capabilities-probe.md)).
  Checked without a GPU: the probe graph matches torch on the CPU to a max absolute error of 3 × 10⁻⁶. **Not yet run**
  on the GPU.
- Status of training: **not yet run** — produced in the data-and-models phase. Each model card lists its pre-registered acceptance
  criterion ([Models](../models/README.md)).

## References

1. JAX. *Installation*. https://docs.jax.dev/en/latest/installation.html
2. PyTorch. *cu130 wheel index* (torch 2.14.1). https://download.pytorch.org/whl/cu130/torch/
3. PyTorch. *cu126 wheel index*. https://download.pytorch.org/whl/cu126/torch/
4. NVIDIA. *Isaac Sim Python (pip) installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
5. Python Package Index. *torch* 2.14.1. https://pypi.org/pypi/torch/2.14.1/json
6. PyTorch. *torch.onnx (2.14)*. https://docs.pytorch.org/docs/2.14/onnx_export.html
7. PyTorch. *set_per_process_memory_fraction (2.14)*.
   https://docs.pytorch.org/docs/2.14/generated/torch.cuda.memory.set_per_process_memory_fraction.html
8. PyTorch. *Reproducibility notes (source)*. https://raw.githubusercontent.com/pytorch/pytorch/main/docs/source/notes/randomness.md
9. PyTorch. *Profiler (2.14)*. https://docs.pytorch.org/docs/2.14/profiler.html
