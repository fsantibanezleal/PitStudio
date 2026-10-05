# Runner

> A small in-repo job runner that turns case recipes into a cached stage graph, runs each stage in its own locked
> environment, never lets two heavy GPU jobs overlap, and records every run as a manifest. · Part of:
> [Studio](README.md) · Related: [Environments](environments.md) · [Console](console.md) ·
> [Recipes and tool registry](../data-contract/recipes-and-tool-registry.md) · [First recipe](../guides/first-recipe.md) ·
> [DEC-0002](../architecture/decisions/DEC-0002-in-repo-runner.md)

## What and why

The studio's GPU work is roughly 55–150 GPU-hours, run as 8–19 overnight slots on one 16 GB laptop GPU, across seven
environments. That needs four guarantees:

1. **One heavy GPU job at a time**, on a GPU that other projects on the same machine also use.
2. **Never redo finished work**: a stage whose code, lock, parameters, seed and inputs did not change is a cache hit.
3. **Survive interruptions**: out-of-memory errors, crashes and sleep must not lose a night's work.
4. **Evidence for every run**: versions, seeds, telemetry and licence class in a manifest.

**Status: planned.** The runner is specified before code and built test-first in the build phase, against a fake GPU
backend, under a budget of about **1,500 lines excluding tests**. Part of it already exists: the capability bench
implements the machine-wide lock, the hold file and the start guards ([Capabilities probe](capabilities-probe.md)).

Why an in-repo runner ([DEC-0002](../architecture/decisions/DEC-0002-in-repo-runner.md)):

| Alternative | Why not |
|---|---|
| Prefect / Dagster | a real multi-process queue needs a running server and database: Prefect's in-memory SQLite "cannot be used across multiple processes" [1]; neither spans isolated uv environments without subprocess wrappers |
| Snakemake | its Windows guide points to WSL [2]; the studio must be Windows-native for RTX |
| doit | a sound make-style DAG [3], but its up-to-date state lives in its own database, not in our manifest; **kept as the fallback** if the runner outgrows its budget |
| Hydra for recipes | `hydra-core` classifiers stop at Python 3.11 [4]; JSON Schema + Pydantic already validate everything else |
| Luigi | requires Python below 3.14 [5] |

![Runner: recipe → plan → queue → guards and locks → workers → store → manifests](../assets/diagrams/runner-architecture.svg)

*The runner's flow. The accent arrow is the GPU gate every GPU stage passes.*

## Recipes and profiles

A **recipe** is a YAML file, validated by `contracts/recipe.schema.json`, that describes one case as a DAG of stages
with parameters and one master seed. Recipes are machine-independent: data is referenced by logical id and digest,
never by path. Each stage declares (fields fixed in the specification):

| Field | Meaning |
|---|---|
| `id`, `env` | stage name and the environment it runs in (`studio`, `isaac`, `rtx`, `isaaclab`, `pipeline`, `accel`, `kit`, `reason`) |
| `inputs`, `outputs` | content-addressed input references; declared outputs with their schema |
| `params` | stage parameters (Pydantic-validated) |
| `resources` | `gpu: exclusive`, `nvenc` or `none`; estimated VRAM and disk |
| `determinism` | `bitwise`, `statistical` or `none` |
| `retry`, `timeout` | classified retry policy, including the out-of-memory fallback |
| `shardable` | whether the stage splits into sub-jobs (for example 1,000 synthetic images per shard) |

A **profile** describes a machine: VRAM, power class, GPU count, store root, CPU slots and enabled environments. Two
exist from the start: `laptop-rtx5000ada` and `linux-gpu` ([Scaling to Linux](scaling-to-linux.md)).

![Example recipe DAG for case C2](../assets/diagrams/recipe-dag-example.svg)

*An illustrative C2 recipe: the terrain and design stages are cache hits shared with other cases; physics, training,
the Kit capture and the encode run.*

## Cache keys and the store

Each stage's cache key is

$$
k_s = \operatorname{SHA256}\!\big(\operatorname{canon}(s,\ h_{\text{code}},\ h_{\text{lock}},\ p_s,\ \sigma_s,\ \{h_{\text{in}}\})\big),
\qquad \sigma_s = H(\sigma_0,\ s,\ \text{shard})
$$

where $s$ is the stage id, $h_{\text{code}}$ the git tree hash of the stage's source folder, $h_{\text{lock}}$ the
SHA-256 of its environment's `uv.lock`, $p_s$ its parameters, $\sigma_0$ the recipe's master seed, $\sigma_s$ the
derived stage seed, $\{h_{\text{in}}\}$ the digests of its inputs, $H$ a hash, and $\operatorname{canon}$ canonical
JSON (sorted keys, fixed number format). A key that exists in the store is a **hit**: the outputs are materialised
without running. Changing a parameter of `st50_physics` therefore re-runs it and everything downstream of it, but not
the terrain or design stages. Large outputs are hashed with `hashlib.file_digest`, which can bypass Python's I/O [6].

The **store** lives at `PITSTUDIO_STORE` (default `C:\ps` on Windows: short, to stay clear of path-length limits):

```text
PITSTUDIO_STORE/
  cas/sha256/ab/…            immutable stage outputs, by content hash
  runs/<run_id>/             manifest.json · events.jsonl · telemetry.parquet · logs/ · tmp/
  views/<recipe>/<stage>/    human-readable views (hardlinks on NTFS)
  queue.db                   the job queue (SQLite, WAL)
```

Writes are atomic: a stage writes into `runs/<run_id>/tmp/`, its outputs are validated against their schema, and only
then promoted by rename. `studio gc` is a mark-and-sweep from pinned manifests (recipes on the main branch, release
bundles), with per-class disk quotas and a low-disk alarm. A Windows Dev Drive would add block cloning but needs admin
rights and policy, so it is optional; the store works on plain NTFS [7].

## Queue, workers and locks

- **One worker** per machine owns the queue (`queue.db`, SQLite in WAL mode). `studio run` enqueues; `studio status`
  shows progress.
- **Each stage runs as** `uv run --project <env> --frozen …` ([Environments](environments.md)) inside a **Windows job
  object** with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`: "closing the last job object handle terminates all associated
  processes" [8]. Kit and Isaac Sim spawn children, so a crashed or cancelled stage leaves no orphan holding the GPU. On
  Linux the same role falls to a process group; `psutil` inspects and kills trees.
- **GPU locks** are files in a **machine-wide** directory, `GPU_LOCK_DIR` (default: `gpu-locks` in the system temp
  folder), because every project on the machine shares the GPU:

  | Lock file | Meaning |
  |---|---|
  | `gpu0.compute` | exclusive: one heavy GPU job (render, physics, training, SDG) at a time |
  | `gpu0.nvenc` | the encoder slot: an encode may overlap CPU stages but not another encode |
  | `gpu0.hold` | if this file exists, **no GPU work starts at all**; its text says why (for example while a hardware fault is investigated) |

  Locks are named per device (`gpuN.*`) from the start, so a multi-GPU host needs no redesign. They use `filelock`
  4.0.10, which on Windows takes "LockFileEx on a byte range. Enforced by the kernel" [9]; if a process dies holding a
  lock, the operating system releases it [10].
- **Keep-awake:** while the queue is non-empty the worker sets `ES_SYSTEM_REQUIRED | ES_CONTINUOUS`. It cannot stop a
  lid close or the power button, so overnight runs need the lid open on AC power [11].

## Guards

Before a GPU stage starts:

- free device VRAM (NVML) ≥ the stage's estimate plus a margin — per-process VRAM is not observable under Windows WDDM,
  so the guard is device-level [12];
- GPU temperature below a cool-down threshold;
- free disk ≥ the stage's estimate plus a margin;
- every capability the stage declares is present in `studio/capabilities.json` (for example the NVENC driver gate, or
  the Isaac Sim Compatibility Checker result); otherwise the stage fails fast.

The bench already applies the first two with fixed thresholds (≥ 4,096 MB free VRAM, ≤ 80 °C at start). During a run,
PyTorch stages cap their allocator with `set_per_process_memory_fraction`, which raises an out-of-memory error instead
of starving other work [13]; Kit stages lower the texture-streaming budget. All thresholds are fixed in the
specification's thresholds file.

## Telemetry, retries and resume

- **Telemetry.** A background sampler reads NVML at 1–4 Hz, with NVTX ranges per stage, into `telemetry.parquet`. The
  manifest gets peak device VRAM, mean and peak power, energy, and the fraction of time in each throttle state
  (`SwPowerCap`, `SwThermalSlowdown`, `HwThermalSlowdown`) [14] — without those fractions, stage timings on a
  power-limited laptop are not comparable ([Nsight / NVML](../frameworks/nsight-nvml.md)).
- **Classified retries.** Only transient failures retry: a CUDA out-of-memory error retries with the stage's declared
  fallback (smaller batch or shard); a first-run shader-cache warm-up timeout retries once. Deterministic failures fail
  fast with the log tail in the manifest.
- **Resume.** Long stages (training, synthetic data, physics) checkpoint and accept `--resume`. Shardable stages resume
  per shard, because each shard is its own cache entry; an interrupted run resumes by its `run_id`.

## Determinism

Each stage declares a determinism class, and tests check it:

| Class | Stages | Check |
|---|---|---|
| `bitwise` | scene authoring; Warp kernels in deterministic mode | build twice or re-run one shard, compare SHA-256 |
| `statistical` | implicit MPM, RTX renders and synthetic data, training | re-run one shard, compare observables within the thresholds file |
| `none` | documented exceptions | — |

Seeds derive from the master seed as above. Replicator uses `rep.set_global_seed` [15]; PyTorch evaluation sets
`use_deterministic_algorithms(True)` and `cudnn.benchmark = False`, while PyTorch warns that full reproducibility is not
guaranteed across releases or platforms [16]; Warp reference runs use its deterministic atomic mode (since 1.15) [17].

## Manifests and publication

Every stage writes `runs/<run_id>/manifest.json`, validated by `contracts/manifest.schema.json`: runner version, cache
key, versions read from the lock (never typed by hand), seeds, determinism class, telemetry summary, retries, exit
status, encoder record for videos, licence class and the `performance: local-only` marker for stages of NVIDIA
runtimes whose licences forbid publishing performance data ([Manifest](../data-contract/manifest.md)). A manifest holds
no host name, user name or absolute path; GPU model, driver and power limit only. `events.jsonl` feeds the
[Console](console.md). `studio publish <run_id>` bakes a run into web artefacts plus a run card for `/studio/runs`.

## Command line

The commands below are specified now and implemented in the build phase:

| Command | Purpose |
|---|---|
| `studio plan <recipe>` | dry run: the DAG, cache hits and misses, VRAM and disk estimates |
| `studio run <recipe> [--stage …] [--force]` | run a recipe or selected stages |
| `studio queue ls` / `studio queue cancel` | inspect or cancel queued jobs |
| `studio worker` | the single queue worker |
| `studio status` | current state |
| `studio gc --keep-pinned --keep-last N` | garbage collection |
| `studio publish <run_id>` | bake a run into web artefacts and a run card |
| `studio bench env` | the capability probe |
| `studio profile` | `torch.profiler` / Warp timing; prints the Nsight command for the maintainer |

```bash run deferred=P6
uv run studio plan studio/recipes/cases/c2.yaml --profile laptop-rtx5000ada
uv run studio run studio/recipes/cases/c2.yaml --profile laptop-rtx5000ada
uv run studio status
uv run studio publish <run-id>
```

Full reference: [CLI](../reference/cli.md).

## Assumptions and limits

- **A runner, not a framework:** no plugins, no UI, no remote workers. Past about 1,500 lines, doit is re-assessed as
  the DAG core.
- First runs of Kit and Isaac Sim spend minutes compiling shaders; stage timeouts allow for it, and only the first
  timeout retries.
- A lid close or power-button sleep stops the run; resume picks it up from the last finished shard.
- Under `gpu0.hold`, no GPU stage starts; `studio plan` still works, because planning never touches the GPU.

## In PitStudio

- Status: **planned.** Specified in the specification phase; built test-first (cache keys, locks, guards, resume,
  out-of-memory fallback, job-object clean-up) against a fake GPU backend in the build phase.
- Exists today: the bench's lock, hold and start guards in `studio/bench/run_bench.py`.

## References

1. Prefect. *Settings reference* (ephemeral server; in-memory SQLite). https://docs.prefect.io/v3/api-ref/settings-ref
2. Snakemake. *Installation*. https://snakemake.readthedocs.io/en/stable/getting_started/installation.html
3. pydoit. *doit dependencies*. https://pydoit.org/dependencies.html
4. Python Package Index. *hydra-core*. https://pypi.org/pypi/hydra-core/json
5. Python Package Index. *luigi*. https://pypi.org/pypi/luigi/json
6. Python Software Foundation. *hashlib (3.14)*. https://docs.python.org/3.14/library/hashlib.html
7. Microsoft. *Dev Drive*. https://learn.microsoft.com/en-us/windows/dev-drive/
8. Microsoft. *Job objects*. https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
9. tox-dev. *filelock documentation*. https://py-filelock.readthedocs.io/en/latest/
10. Microsoft. *LockFileEx*. https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex
11. Microsoft. *SetThreadExecutionState*. https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
12. NVIDIA. *nvidia-smi documentation*. https://docs.nvidia.com/deploy/nvidia-smi/index.html
13. PyTorch. *set_per_process_memory_fraction (2.14)*. https://docs.pytorch.org/docs/2.14/generated/torch.cuda.memory.set_per_process_memory_fraction.html
14. NVIDIA. *NVML clocks event reasons*. https://docs.nvidia.com/deploy/nvml-api/latest/api/group__nvmlClocksEventReasons.html
15. NVIDIA. *Isaac Sim 6.0 Replicator snippets*. https://docs.isaacsim.omniverse.nvidia.com/6.0.0/replicator_tutorials/tutorial_replicator_isaac_snippets.html
16. PyTorch. *Reproducibility notes (source)*. https://raw.githubusercontent.com/pytorch/pytorch/main/docs/source/notes/randomness.md
17. NVIDIA. *Warp CHANGELOG*. https://raw.githubusercontent.com/NVIDIA/warp/main/CHANGELOG.md
