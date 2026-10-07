# Scaling to a Linux GPU host

> The same recipes, locks and command line run on a Linux GPU host later; only a machine profile changes, and a CI
> check will prove it by planning every recipe for Linux against a fake GPU. · Part of: [Studio](README.md) · Related:
> [Runner](runner.md) · [Environments](environments.md) · [Deployment](../architecture/deployment.md) ·
> [Isaac Sim + Replicator](../frameworks/isaac-sim-replicator.md)

## What and why

The reference studio is one Windows laptop with a 16 GB GPU. Some work would go faster, or only becomes possible, on a
Linux host with more or larger GPUs: multi-GPU training, the Isaac Sim container, NVIDIA's Linux-only tools such as
cuOpt, and models that do not fit in 16 GB. The design goal is that moving there costs a profile, not a rewrite:
**nothing in a recipe is laptop-specific except the profile it is run with**.

"Scalable" is not a promise in prose; it is an executable check in CI (below).

## Machine profiles

A profile is a YAML file in `studio/recipes/_profiles/` read by the runner. Two are planned, written with the runner:

| Field | `laptop-rtx5000ada` | `linux-gpu` |
|---|---|---|
| OS | Windows 11, native | Linux |
| GPUs | 1 × 16 GB, power-limited | N (from the host) |
| Store root | `PITSTUDIO_STORE` (default `C:\ps`) | `PITSTUDIO_STORE` on a local disk |
| CPU slots | a share of the cores | from the host |
| Enabled environments | all, including `studio/kit/` and `studio/reason/` | open lanes; NVIDIA lanes only where installed |
| Process control | Windows job objects | process groups |
| Locks | `gpu0.compute`, `gpu0.nvenc` | `gpuN.compute`, `gpuN.nvenc` per device |

Recipes refer to data by logical id and digest, never by path, and every machine uses the same `uv.lock` files, so a
run on either machine records the same tool versions.

## The CI plan check (fake GPU backend)

A CI job on a GitHub-hosted Ubuntu runner (no GPU) will, on every push:

1. run `studio plan` for **every recipe** with the `linux-gpu` profile, against a **fake GPU backend** that answers NVML
   queries with a declared device;
2. fail if any plan leaks an OS-specific detail or a machine detail (a Windows path, a drive letter, a host name);
3. build `studio/containers/Dockerfile.open` and run the CPU test subset inside it.

The runner's own tests use the same fake backend for locks, guards, resume and the out-of-memory fallback, so the GPU
logic is tested without a GPU.

```bash run deferred=P6
uv run studio plan studio/recipes/cases/a1.yaml --profile linux-gpu
```

## The open container

`Dockerfile.open` covers the open lanes (`studio/` and `pipeline/` with the root project). It follows uv's documented
container pattern: a pinned uv image, `uv sync --locked`, `--no-install-project` to cache the dependency layer,
`UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`, and the base image pinned by SHA-256, which uv calls best practice [1].
The same lock files drive Windows and Linux.

## The Isaac Sim container: built on the host, never pushed

On Linux, Isaac Sim is container-native: NVIDIA publishes `nvcr.io/nvidia/isaac-sim:6.1.0`, run headless with
`ACCEPT_EULA=Y` and `PRIVACY_CONSENT=Y`, with cache volumes for its shader and compute caches [2]. PitStudio's rule:

- `Dockerfile.isaac` is `FROM` that image plus our `studio/isaac/` package;
- it is **built only on a real Linux GPU host** by whoever accepts the EULA there;
- the resulting image is **never pushed to any public registry**, because it contains NVIDIA software that PitStudio
  never redistributes ([DEC-0004](../architecture/decisions/DEC-0004-proprietary-sdks-reference-only.md));
- the old IsaacSim-dockerfiles repository is deprecated and is not used [3].

The Isaac Sim container is Linux-only; Windows hosts, including WSL, are not supported for it [2]. That is why the
laptop runs Isaac Sim natively.

## What becomes possible there

| Capability | Why Linux | Page |
|---|---|---|
| Multi-GPU robot learning | Isaac Lab multi-GPU and multi-node training "is only supported on Linux" because of NCCL [4] | [Isaac Lab](../frameworks/isaac-lab.md) |
| GPU LP / MILP | cuOpt ships Linux wheels only | [cuOpt, not adopted](../frameworks/not-adopted-cuopt.md) |
| Models over 16 GB | larger GPUs | [Cosmos Predict / Transfer, not adopted](../frameworks/not-adopted-cosmos-predict-transfer.md) |
| Reuse of the console | over SSH port forwarding; it stays bound to loopback | [Console](console.md) |

Stores are synchronised by `studio publish` bundles, not by copying raw caches between machines.

## What is deliberately not built now

Kubernetes, Ray, Kit app-streaming servers, a Prefect or Dagster server, a remote object store, DVC, multi-node
training and Docker on the laptop. None is needed until a second machine exists, and each would add operations work
the project does not budget.

## Assumptions and limits

- No Linux GPU host exists yet; `linux-gpu` is exercised only by the CI plan check until one does.
- The NVIDIA Container Toolkit version for such a host is not pinned here; it is recorded when the host is set up.
- NVIDIA software runs only on NVIDIA platforms under its terms, so the Isaac lane never runs on CI runners [5].

## In PitStudio

- Status: **planned.** `studio/recipes/_profiles/`, the CI job and `Dockerfile.open` are created with the runner in the
  build phase.

## References

1. Astral. *Using uv in Docker*. https://docs.astral.sh/uv/guides/integration/docker/
2. NVIDIA. *Isaac Sim container installation*. https://docs.isaacsim.omniverse.nvidia.com/latest/installation/install_container.html
3. NVIDIA. *IsaacSim-dockerfiles (deprecated)*. https://github.com/NVIDIA-Omniverse/IsaacSim-dockerfiles
4. Isaac Lab. *Multi-GPU and multi-node training*. https://isaac-sim.github.io/IsaacLab/main/source/features/multi_gpu.html
5. NVIDIA. *Product Specific Terms for NVIDIA AI Products* (§8.15, PDF).
   https://www.nvidia.com/content/dam/en-zz/Solutions/license-agreements/enterprise-software/product-specific-terms-ai-products-omniverse-16042026.pdf
