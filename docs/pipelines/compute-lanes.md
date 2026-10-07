# Compute lanes

> Where local computation runs: the CPU, CUDA 12.6 and CUDA 13.0 builds of the pipeline (extras `cpu`, `cu126`,
> `cu130`), the GPU-only studio environments, and the pip fallbacks for people without uv. · Part of:
> [Pipelines](README.md) · Related: [Environments](../studio/environments.md) · [Run instructions](run-instructions.md) ·
> [Scaling to Linux](../studio/scaling-to-linux.md) · [Compute tiers](../web/compute-tiers.md)

## What and why

PitStudio uses the word *lane* in two places. **Web lanes** (live, precompute, replay) say where a result is computed
for a visitor ([Compute tiers](../web/compute-tiers.md)). **Compute lanes**, on this page, say which build of the
heavy libraries runs the local work: a CPU build anyone can install, or a CUDA build matched to the NVIDIA driver.
The rule is that the same lock file serves every lane, the lane is chosen from the driver, and a silent fall-back to
the CPU is treated as an error, not as a convenience.

## The pipeline lanes: one lock, three extras

`pipeline/pyproject.toml` declares three mutually exclusive extras (uv `conflicts`), each resolved against its own
PyTorch package index; the versions below are those in `pipeline/uv.lock`.

| Extra | PyTorch build | ONNX Runtime | NVIDIA driver | Who uses it |
|---|---|---|---|---|
| `cpu` | `torch` 2.14.1+cpu, `torchvision` 0.29.1+cpu | `onnxruntime` 1.30.0 (CPU) | none | CI, readers without an NVIDIA GPU |
| `cu126` | `torch` 2.14.1+cu126, `torchvision` 0.29.1+cu126 | `onnxruntime` 1.30.0 (CPU) | ≥ 525 | older NVIDIA drivers |
| `cu130` | `torch` 2.14.1+cu130, `torchvision` 0.29.1+cu130 | `onnxruntime-gpu` 1.30.0 | ≥ 580 | the reference laptop (driver 582.78) |

Why the thresholds and the split:

- **Driver floors.** Under CUDA minor-version compatibility, CUDA 13.x applications need driver ≥ 580 and CUDA 12.x
  applications driver ≥ 525 [1].
- **CUDA 13 wheels exist for Python 3.14 on Windows.** The PyTorch cu130 index carries
  `torch-2.14.1+cu130-cp314-cp314-win_amd64` and the matching Linux wheels [2].
- **ONNX Runtime GPU follows CUDA 13.** Since 1.27 the GPU packages on PyPI are built with CUDA 13.0 by default; CUDA 12
  variants need CUDA ≥ 12.8 [3]. The `cu126` lane therefore keeps ONNX Runtime on the CPU, which is also the parity
  reference of every model ([Export, parity and acceleration](../models/export-parity-acceleration.md)).
- **Shared CUDA libraries.** ONNX Runtime GPU 1.30 links the CUDA 13 cuBLAS; PyTorch cu130 ships CUDA 13 runtime,
  cuBLAS and cuDNN 9 libraries, and `onnxruntime.preload_dlls()` loads those, so one CUDA stack serves both (bootstrap
  finding).

### Choosing the lane

The bootstrap scripts (`scripts/bootstrap.ps1`, `scripts/bootstrap.sh`) read the driver version with `nvidia-smi` and
pick `cu130` for a major version ≥ 580, `cu126` for ≥ 525 and `cpu` otherwise. They then run
`scripts/verify_gpu.py --expect <extra>`, which fails fast when PyTorch cannot use CUDA or was built for another CUDA
version than requested. The scripts never install system software; they only report what is missing.

## The other environments

| Environment | Python | Compute | Notes |
|---|---|---|---|
| root (`pitstudio`) | 3.14 | CPU | core, contracts, runner (extra `runner`: `filelock`, `nvidia-ml-py`, `psutil`), `minephys` |
| `pipeline/accel/` | 3.14 | NVIDIA GPU only | TensorRT 11.3.0.99 from NVIDIA's index, `polygraphy` 0.53.6, CUDA 13 runtime wheel 13.4.92; TensorRT 11.3 needs a CUDA 13 driver of the R580 branch or later [4] |
| `studio/` | 3.14 | NVIDIA GPU; Warp also runs on the CPU | Warp's PyPI wheels are built with CUDA 12.9 (driver ≥ 525), its CUDA 13 builds need driver ≥ 580 [5]; Warp can execute kernels on the CPU [6], which keeps small physics checks reproducible without a GPU |
| `studio/isaac/` | 3.12 | NVIDIA RTX GPU only | Isaac Sim 6.1.0.0 with its own `torch` 2.11.0 (cu130 index); uv-managed interpreter only; long paths enabled on Windows [7] |
| `studio/rtx/` | 3.12 | NVIDIA RTX GPU only | ovrtx, ovstage, ovphysx (pre-release, NVIDIA's index) |
| `studio/isaaclab/` | 3.12 | NVIDIA GPU only | Isaac Lab v3.0.0-EA tag, kit-less on Newton; `torch` 2.11.0 from the cu128 index (the tag's tested pin) |
| `studio/kit/`, `studio/reason/` | — | NVIDIA RTX GPU | our Kit extension; llama.cpp CUDA build as an external tool |

Every environment is entered only through `uv run --project <env> --frozen …`, so a stage always runs against its
locked versions.

## What runs without an NVIDIA GPU

| Reproducible on CPU | Needs an NVIDIA GPU |
|---|---|
| `minephys` models, the DES, LP dispatch, min-cut, analytical slope, dust and comminution models | RTX rendering, synthetic image generation, RTX sensors (Isaac Sim, Replicator, ovrtx, Kit) |
| ingestion, evaluation and export of baked data; ONNX inference with ONNX Runtime CPU | Isaac Lab training, Cosmos Reason 2 inference |
| small Warp kernels on the CPU | Warp / Newton physics at scale, TensorRT engines, NVENC encoding |
| every live engine of the web app (it runs in the visitor's browser) | — |

Precomputed GPU results are published as replay artefacts, so a reader without a GPU can still inspect every result;
what they cannot do is regenerate the GPU ones.

## Linux GPU hosts

The same lock files drive Windows and Linux. A Linux GPU host is a second machine profile (`linux-gpu`), not a second
code path: recipes do not change ([Scaling to Linux](../studio/scaling-to-linux.md)). CI already plans every recipe with
that profile against a fake GPU backend; a container definition for the open lanes follows uv's documented Docker
pattern [8], and an Isaac Sim container would be built only on a real Linux GPU host and never pushed to a public
registry.

## pip fallbacks: `requirements/`

For readers who do not use uv, `requirements/` will hold pip requirement files **generated from the locks** (runtime,
`pipeline-cpu`, `pipeline-cu126`, `pipeline-cu130`). They are validated by CI and never edited by hand. Today the folder
contains only its README; the files are generated in the build phase. Usage will look like this (illustrative):

```bash
python -m venv .venv-pipeline
.venv-pipeline/bin/pip install -r requirements/pipeline-cpu.txt   # or pipeline-cu126 / pipeline-cu130
```

The CUDA files need the matching PyTorch package index (`https://download.pytorch.org/whl/cu126` or `…/cu130`), as the
uv project declares. uv remains the supported path: only uv reproduces the exact lock, hashes included.

## Assumptions and limits

- The driver thresholds are those of the CUDA compatibility rules; a driver can meet them and still lack a feature a
  specific tool needs (for example NVENC API levels), which is why the capability probe exists
  ([Capabilities](../data-contract/capabilities.md)).
- The `cu126` lane is not exercised on the reference machine, which runs `cu130`; CI covers `cpu` only.
- Laptop GPUs are power-limited; the lane says which build runs, not how fast it runs.

## In PitStudio

- **Files:** `pipeline/pyproject.toml` (extras, conflicts, indexes), `pipeline/uv.lock`, `scripts/bootstrap.ps1`,
  `scripts/bootstrap.sh`, `scripts/verify_gpu.py`, `requirements/README.md`.
- **CI:** the `cpu` lane is installed and tested on every push.

```bash run
cd pipeline
uv sync --extra cpu --all-groups --locked
uv run pytest -m "not gpu and not slow"
```

## References

1. NVIDIA, *CUDA minor version compatibility*. https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html
2. PyTorch cu130 wheel index (`torch` 2.14.1). https://download.pytorch.org/whl/cu130/torch/
3. ONNX Runtime, *CUDA Execution Provider*. https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
4. NVIDIA, *TensorRT installation prerequisites*. https://docs.nvidia.com/deeplearning/tensorrt/latest/installing-tensorrt/prerequisites.html
5. NVIDIA Warp, *Installation*. https://nvidia.github.io/warp/stable/user_guide/installation.html
6. NVIDIA Warp repository. https://github.com/NVIDIA/warp
7. NVIDIA, *Isaac Sim 6.1.0 Python installation*. https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/install_python.html
8. uv, *Using uv in Docker*. https://docs.astral.sh/uv/guides/integration/docker/
