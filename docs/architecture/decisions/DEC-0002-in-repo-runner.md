# DEC-0002: A small in-repo runner

> A runner of about 1,500 lines inside the core package drives every studio and pipeline stage: schema-validated YAML
> recipes, a content-addressed cache, per-device GPU locks, NVML guards and telemetry, Windows job objects and
> resumable shards. · Part of: [decisions](README.md) · Related: [runner](../../studio/runner.md) ·
> [recipes and tool registry](../../data-contract/recipes-and-tool-registry.md) · [DEC-0001](DEC-0001-isolated-studio-environments.md)

**Status:** Accepted, 2026-10-04

## Context

Studio work is long (training runs, synthetic-data generation, physics sweeps), spans several isolated environments
([DEC-0001](DEC-0001-isolated-studio-environments.md)) and shares one 16 GB laptop GPU that throttles at its power
limit. The orchestration has to:

- launch each stage in its own locked environment and pass only files between them;
- never run two heavy GPU jobs at once, and never leave orphan processes when a job is killed;
- skip work whose inputs have not changed, and resume an interrupted run at shard granularity;
- record telemetry that makes timings comparable, including the time spent power- or thermally-throttled;
- keep the record in PitStudio's own manifest format, not in a tool's private database.

The options were checked in October 2026. Prefect's in-memory SQLite "cannot be used across multiple processes", so a
real multi-process queue needs a running server and database [1]; Dagster is similar in weight. Snakemake recommends WSL
on Windows [2], which the studio cannot use for RTX work. doit is a sound make-style DAG, but its up-to-date state lives
in its own database [3]. Hydra and OmegaConf classify only up to Python 3.11.

## Decision

The runner lives in `src/pitstudio/runner/` in the root project (Python 3.14), with the extra
`runner = [filelock, psutil, nvidia-ml-py]`. The heavy environments never import it; they receive a job-spec file.

- **Recipes** are YAML files validated by `contracts/recipe.schema.json`, forming a DAG of stages per case. Each stage
  declares its environment, entry point, inputs, parameters, resources (`gpu: exclusive | nvenc | none`, VRAM and disk
  estimates), determinism class, retry policy, timeout, outputs and whether it is shardable.
- **Cache.** The cache key is the SHA-256 of canonical JSON over the stage id, the stage's code digest, the
  environment's lock digest, the parameters, the derived seed and the input digests. A hit materialises outputs from a
  content-addressed store under `PITSTUDIO_STORE`. Outputs are written to a temporary folder and promoted by rename only
  after they validate.
- **GPU locks.** Per-device file locks, `gpu0.compute` (exclusive) and `gpu0.nvenc`, held through `filelock`, which uses
  `LockFileEx` on Windows; the operating system releases such locks when a process dies [4] [5]. Locks are per device from
  day one, so a multi-GPU host needs no redesign. One heavy GPU job runs at a time until co-residence is measured.
- **Guards.** Before a stage: free device VRAM, free disk, GPU temperature and the capabilities the stage requires from
  the committed `studio/capabilities.json`. VRAM is checked at device level because per-process memory is not observable
  under WDDM [6].
- **Telemetry.** A 1–4 Hz NVML sampler records used VRAM, utilisation, power against the enforced limit, temperature, SM
  clock and the clock-event (throttle) reasons, with NVTX ranges [7]. The manifest stores peak VRAM, mean and peak
  power, energy and the fraction of time in each throttle state.
- **Process control.** Each stage runs inside a Windows job object with kill-on-close, so a killed run leaves no orphans
  [8]; the runner keeps the machine awake while the queue is not empty [9].
- **Failures.** Retries only for classified transient failures (CUDA out-of-memory retries with the stage's declared
  fallback; first-run shader-cache warm-up). Deterministic failures fail fast with the log tail in the manifest.
  Shardable stages resume at shard granularity because each shard is its own cache entry.
- **Machine profiles.** Recipes are machine-independent; per-machine profiles (`laptop-rtx5000ada`, `linux-gpu`) hold
  VRAM, power class, GPU count, store root and enabled environments.
- **CLI.** `studio plan | run | queue | worker | status | gc | publish | bench | profile`.
- **Budget.** About 1,500 lines of code excluding tests. If it grows beyond that, doit is re-assessed as the DAG core.

## Alternatives considered

| Option | Pros | Cons | Why rejected |
|---|---|---|---|
| Prefect or Dagster | Mature lineage UI | A server and database for a multi-process queue; spans the isolated environments only through subprocess wrappers; its state is not our manifest | Operational weight with no gain on one machine |
| Snakemake | Mature file-based DAGs | Windows use through WSL per its own documentation | The studio must be Windows-native |
| doit as the core | Small, OS-independent, sound up-to-date rules | Up-to-date state in its own database; GPU exclusivity still to be added | Kept as the fallback if the runner outgrows its budget |
| Plain PowerShell or shell scripts | No code to maintain | No cache, no resume, no locks | Fails the robustness goal |

## Consequences

**Positive.** Heavy GPU jobs never collide; every result carries its manifest and telemetry; interrupted runs resume;
the cache makes reruns cheap; the same recipes run on a Linux host with another profile.

**Negative, accepted.** A runner to maintain and test (against a fake GPU backend in CI); a lock directory shared by
every project on the machine.

**Watch.** The line budget; whether co-residence of two GPU jobs is safe once measured; keep-awake behaviour (it cannot
stop a lid close).

## References

1. Prefect settings reference (ephemeral server, in-memory SQLite). https://docs.prefect.io/v3/api-ref/settings-ref
2. Snakemake installation (Windows via WSL). https://snakemake.readthedocs.io/en/stable/getting_started/installation.html
3. doit: dependencies and up-to-date rules. https://pydoit.org/dependencies.html
4. filelock documentation (Windows backend: LockFileEx). https://py-filelock.readthedocs.io/en/latest/
5. Microsoft Learn. LockFileEx. https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex
6. NVIDIA. nvidia-smi documentation (per-process memory unavailable under WDDM). https://docs.nvidia.com/deploy/nvidia-smi/index.html
7. NVIDIA. NVML API: clocks event reasons. https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
8. Microsoft Learn. Job objects. https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
9. Microsoft Learn. SetThreadExecutionState. https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
