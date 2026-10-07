# Studio environments

> Each tool family lives in its own uv project with its own lock and Python version; stages cross between them only
> through schema-validated files, never through imports. · Part of: [Studio](README.md) · Related:
> [Runner](runner.md) · [Frameworks](../frameworks/README.md) · [Set up the studio](../guides/set-up-the-studio.md) ·
> [DEC-0001](../architecture/decisions/DEC-0001-isolated-studio-environments.md)

## What and why

The studio drives open tools (OpenUSD, Warp, Newton, PyTorch) and NVIDIA runtimes (Isaac Sim, Kit, ovrtx, TensorRT) on
one machine. They cannot share one Python environment:

1. **Python versions differ.** The apps and the open stack run on Python 3.14; Isaac Sim and Kit require exactly 3.12
   [1][2]; ovrtx and ovstage classify 3.10–3.13 and NVIDIA's own example caps below 3.14 [3][4].
2. **Torch pins differ.** Isaac Sim's pip guide installs `torch==2.11.0` [1]; the pipeline trains on 2.14.1; Isaac Lab's
   v3.0.0-EA tag tests 2.11.0 from the cu128 index and its `release/3.0.0` branch pins 2.12.0 [5].
3. **Two RTX runtimes must not share a process.** ovrtx brings its own RTX runtime; loading it next to Kit is
   undocumented, so they never meet in one interpreter.
4. **Two TensorRT majors share one distribution name.** The ONNX Runtime TensorRT execution provider in ORT 1.30 is
   built against TensorRT 10.14.1.48 and requests `nvinfer_10.dll`, while the acceleration lane uses TensorRT 11.3 [6][7].
5. **Pins inside NVIDIA libraries.** ovphysx requires `packaging<24` and `warp-lang<2,>=1.16` [8].
6. **NVIDIA itself advises** "a dedicated Python environment" for Isaac Sim [1].

Rejected alternatives ([DEC-0001](../architecture/decisions/DEC-0001-isolated-studio-environments.md)): one large
environment (the conflicts above), and containers on the laptop: the Isaac Sim container is Linux-only, OpenGL interop
is unsupported in WSL2 and Vulkan/RTX initialisation failures are reported there [9][10][11].

![Studio environments: one uv project and one lock each](../assets/diagrams/studio-environment-map.svg)

*Every environment with its Python version and key locked packages. Dashed boxes hold NVIDIA proprietary runtimes.*

## The environments

| Environment | Python | Lock | Holds (versions from the lock) | Stages | In CI? |
|---|---|---|---|---|---|
| root | 3.14 | `uv.lock` | core and contracts, the runner (planned), `minephys` (git `143e709`); extra `runner`: filelock 4.0.10, psutil 7.2.2, nvidia-ml-py 13.615.71; extra `api`: FastAPI 0.142.2, uvicorn 0.54.0 | runner CLI, bench | yes |
| `api/` | 3.14 | root extra `api` | the loopback console (placeholder folder today) | — | contract tests (planned) |
| `studio/` | 3.14 | `studio/uv.lock` | usd-core 26.8, warp-lang 1.17.0, newton 1.6.0 (+ mujoco / mujoco-warp 3.12.0), usd-validation-nvidia 1.22.0, simready-validate 2026.8.0, pynvvideocodec 2.2.3, nvtx 0.2.16, laspy 2.7.0, rasterio 1.5.2, trimesh 5.1.1, ortools 9.15.6755 | `st10`–`st50`, `st56_encode` | CPU subset (planned) |
| `studio/isaac/` | 3.12 | `studio/isaac/uv.lock` | isaacsim[all,extscache] 6.1.0.0 (+ isaacsim-replicator), torch 2.11.0+cu130, mujoco-usd-converter 0.5.0 | `st52`, `st54`, `st55`, `st57` | never |
| `studio/rtx/` | 3.12 | `studio/rtx/uv.lock` | ovrtx 0.5.0.377615, ovstage 0.2.0.377349, ovphysx 0.6.3, openexr 3.5.2 | `st53_sensors` | never |
| `studio/isaaclab/` | 3.12 | `studio/isaaclab/uv.lock` | Isaac Lab tag v3.0.0-EA (commit `ae37b02`): isaaclab 17.0.2, isaaclab-newton 5.4.1, isaaclab-rl 0.16.3; the tag's tested stack mirrored from upstream (torch 2.11.0+cu128, Warp 1.16.0, Newton 1.5.2, rsl-rl-lib 5.4.1) | `st60`, `st61` | never |
| `studio/kit/` | Kit's own 3.12 | none (planned folder) | our Apache-2.0 extension and minimal `.kit` file only; Kit 110.3 is generated outside the repo | `st58_kit_capture`, `st45b_kit_validate` | never |
| `studio/reason/` | — | none (planned folder) | llama.cpp b11381 as an external tool; model files pinned by SHA-256 | `st59*` | never |
| `pipeline/` | 3.14 | `pipeline/uv.lock` | torch 2.14.1 with mutually exclusive extras `cpu`, `cu126`, `cu130`; onnxruntime(-gpu) 1.30.0; onnx 1.23.1; minehaulsim 0.12.1; oreblocks 0.5.2; polars, duckdb, zarr, pooch, pandera | `s00`–`s60` | CPU extra, samples only |
| `pipeline/accel/` | 3.14 | `pipeline/accel/uv.lock` | tensorrt-cu13 11.3.0.99, polygraphy 0.53.6, nvidia-cuda-runtime 13.4.92, onnxruntime-gpu 1.30.0 (CUDA EP), nvidia-ml-py 13.615.71 | `s62_accel`, `s64_bench` | never |

The same package can sit at different versions in two lanes. The locks today resolve, for example:

| Package | `studio/` | `studio/isaac/` | `studio/isaaclab/` | `pipeline/` |
|---|---|---|---|---|
| torch | — | 2.11.0+cu130 | 2.14.1+cu130 | 2.14.1 (per extra) |
| warp-lang | 1.17.0 | 1.17.0 | — | — |
| newton | 1.6.0 | 1.5.0 (Isaac Sim's) | — | — |
| mujoco-warp | 3.12.0 | 3.11.0 | — | — |
| numpy | 2.5.3 | 2.3.1 | 2.5.3 | 2.5.3 |

That is why every run manifest records the versions it actually used, read from the lock, and why science numbers
come from the open lane only.

## Interpreter and index policy

- **Exact Python per project.** `requires-python` is `==3.14.*` or `==3.12.*`, and each project has a
  `.python-version` file.
- **`python-preference = "only-managed"`** in the three 3.12 projects: uv uses only interpreters it installed itself
  (`uv python install 3.12`, per user, no admin). A system Python, and above all the Microsoft Store shim, can never be
  picked up. The capability probe enforces it: a probe whose `sys.executable` lives under `WindowsApps` fails.
- **Explicit indexes.** NVIDIA wheels come from `https://pypi.nvidia.com`, declared `explicit = true` and pinned per
  package, so the resolver never builds the 23 KB ovrtx sdist that PyPI hosts; PyTorch comes from its own wheel
  indexes per CUDA variant. uv "will stop at the first index on which a given package is available", and an explicit
  index serves only the packages pinned to it [12].
- **Entering an environment.** The runner launches every stage as `uv run --project <env> --frozen …`: `--frozen` runs
  "without updating the `uv.lock` file"; the bench uses `--locked`, which asserts that the lock stays unchanged [13].
- **Security floors.** `studio/isaac/` overrides transitive pins of the Isaac Sim stack to their first patched
  versions (`override-dependencies`); Isaac Sim and its torch pin are untouched.

## File-only handoff

![File-only handoff between the Python 3.14 and 3.12 environments](../assets/diagrams/file-handoffs.svg)

*The seven file kinds that cross lanes, each validated on write and on read.*

Lanes never import each other. Everything that crosses goes through the studio store (`PITSTUDIO_STORE`) as one of
seven file kinds:

| File kind | Format | Contract |
|---|---|---|
| Job spec | JSON | `contracts/recipe.schema.json` (planned) |
| Scene | USD layers (`.usda` / `.usdc`) + `scene.manifest.json` | units, axis, SHA-256 per layer |
| Poses and fields | Parquet, Zarr v3, time-sampled USD | stage output schema |
| Images and labels | PNG / EXR, COCO JSON, masks | dataset schema |
| Point clouds and radar | NPZ in the 3.12 lanes, LAZ in 3.14 | point-cloud schema |
| Models and policies | ONNX with IR and opset pinned | parity report |
| Run manifest | JSON | `contracts/manifest.schema.json` (planned) |

The contracts are JSON Schema 2020-12; Python (Pydantic) and TypeScript types are generated from them and CI fails on
drift ([Data contract](../data-contract/README.md)). Both sides validate, so a file that fails its schema stops the
stage instead of corrupting the next lane — the main failure mode of a split Python world.

## Setting up

The root project and the pipeline's CPU extra are what CI installs:

```bash run
uv sync --locked
uv sync --project pipeline --extra cpu --locked
```

The GPU and NVIDIA lanes follow the same pattern on the reference machine, after the maintainer's acts
([Maintainer acts and licences](owner-acts-and-licences.md)); `studio/isaac/` downloads tens of gigabytes:

```bash run deferred=P6
uv python install 3.12
uv sync --project studio --locked
uv sync --project pipeline --extra cu130 --locked
uv sync --project pipeline/accel --locked
uv sync --project studio/rtx --locked
uv sync --project studio/isaac --locked
uv sync --project studio/isaaclab --locked
```

Full steps per environment: [Set up the studio](../guides/set-up-the-studio.md).

## Assumptions and limits

- **Isaac Lab's dependency set is mirrored, not inherited.** Its packages declare no third-party dependencies (upstream
  keeps them in its root `pyproject.toml`), so `studio/isaaclab/pyproject.toml` copies that list and its tested
  overrides at the EA tag: torch 2.11.0 (cu128), Warp 1.16.0, Newton 1.5.2 [5][14]. The lock is consistent; the kit-less
  smoke validates it on the GPU ([Isaac Lab](../frameworks/isaac-lab.md)).
- The TensorRT 10.14 libraries for the ORT TensorRT EP are planned for `pipeline/` and are not in its lock yet.
- `studio/kit/`, `studio/reason/` and the console code do not exist yet.
- Disk: Isaac Sim and its extension cache need tens of gigabytes; the exact size is measured at set-up.

## In PitStudio

- Status: the seven Python projects are locked and committed; CI installs only the root and the pipeline's CPU extra.
- The [Capabilities probe](capabilities-probe.md) runs each probe in its own environment.

## References

1. NVIDIA. *Isaac Sim Python (pip) installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_python.html
2. Python Package Index. *omniverse-kit*. https://pypi.org/pypi/omniverse-kit/json
3. Python Package Index. *ovrtx*. https://pypi.org/pypi/ovrtx/json
4. NVIDIA. *ovrtx lidar example pins*. https://raw.githubusercontent.com/NVIDIA-Omniverse/ovrtx/main/examples/python/lidar/pyproject.toml
5. Isaac Lab. *release/3.0.0 pyproject.toml*. https://raw.githubusercontent.com/isaac-sim/IsaacLab/release/3.0.0/pyproject.toml
6. Microsoft. *ONNX Runtime v1.30.0 CI variables*. https://raw.githubusercontent.com/microsoft/onnxruntime/v1.30.0/tools/ci_build/github/azure-pipelines/templates/common-variables.yml
7. Microsoft. *Issue #32278*. https://github.com/microsoft/onnxruntime/issues/32278
8. Python Package Index. *ovphysx*. https://pypi.org/pypi/ovphysx/json
9. NVIDIA. *Isaac Sim container installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
10. NVIDIA. *CUDA on WSL user guide*. https://docs.nvidia.com/cuda/wsl-user-guide/index.html
11. GitHub issue (2026-03-30). *Isaac Sim fails in WSL2 + Docker due to Vulkan/RTX initialization*. https://github.com/robotmcp/ros-mcp-server/issues/289
12. Astral. *uv indexes*. https://docs.astral.sh/uv/concepts/indexes/
13. Astral. *uv CLI reference*. https://docs.astral.sh/uv/reference/cli/
14. Isaac Lab. *v3.0.0-EA release note*. https://api.github.com/repos/isaac-sim/IsaacLab/releases/tags/v3.0.0-EA
