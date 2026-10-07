# Spec 002 — Runner
Status: Clarified
Tier: M · Parent: 000-foundation · Approved: —
Supersedes/Modifies: (none)

## 1. Intent

The studio's GPU work (≈ 55–150 GPU-hours in 8–19 overnight slots on one 16 GB laptop GPU, across isolated
environments) needs one small, test-first job runner: `src/pitstudio/runner/`, invoked as `studio`. It turns YAML
recipes (spec 001-contracts) into a stage DAG, skips work whose code, lock, parameters, seed and inputs did not change
(content-addressed cache), never lets two heavy GPU jobs of any project on the machine overlap (machine-wide locks
`gpuN.compute` / `gpuN.nvenc` in `GPU_LOCK_DIR`), refuses all GPU work while `gpu0.hold` exists, checks VRAM, disk,
temperature and capabilities before a stage starts, records NVML telemetry and NVTX ranges, cleans up whole process
trees, retries only classified transient failures (CUDA out-of-memory → the declared fallback), resumes interrupted
runs per shard, garbage-collects from pinned manifests and publishes runs through the manifest contract. Recipes are
machine-independent; a profile (`laptop-rtx5000ada`, `linux-gpu`) is the only machine-specific input, and CI proves it
by planning every recipe for Linux against a fake GPU backend. It implements FR-000-13 and FR-000-16, produces the
manifests of FR-000-14/15 and respects NFR-000-08 (≤ 1,500 lines).

Who benefits: the maintainer (long runs survive crashes and never collide), developers (one command reproduces an
artefact), reviewers (every run leaves a manifest).

Out of scope: the stages' own science (specs 004–017), the media encode and VMAF search (spec 006-media-telemetry),
the console (spec 003-console), parallel execution of several stages by one worker, remote workers, any server or
database other than the local SQLite queue file, and running Nsight Systems (an elevated tool the maintainer runs).

## 2. User stories

### US-002-1 (P1) Plan anywhere, without the GPU
As the maintainer or a CI job, I want `studio plan <recipe> --profile <name>` to show the stage DAG, cache hits and
misses, the locks each stage would take and its VRAM and disk estimates, without touching the GPU, so that I can check
a recipe on any machine — including under a GPU hold and on a Linux runner. Independent test: plan every recipe with
the `linux-gpu` profile on a CPU-only Ubuntu runner with the fake backend; every plan exits 0 and leaks no OS or machine
detail.

### US-002-2 (P1) One heavy GPU job at a time, with guards
As the maintainer, I want every GPU stage to take the machine-wide lock, refuse to start under a hold, and check free
VRAM, disk, temperature and capabilities first, so that no two GPU jobs collide and no run starts on a hot, full or
incapable machine. Independent test: with the fake backend, concurrent runner processes never overlap inside a compute
stage, and each guard refuses with its reason code and exit code 5.

### US-002-3 (P1) Never redo finished work
As the maintainer, I want a stage whose code, environment lock, parameters, derived seed and inputs are unchanged to be
a cache hit served from a content-addressed store, so that re-runs are cheap and outputs are exactly the ones recorded.
Independent test: run a fake recipe twice; the second run launches 0 stage processes and materialises byte-identical
outputs.

### US-002-4 (P1) Survive interruptions
As the maintainer, I want out-of-memory failures retried with the declared fallback, killed or crashed stages to leave
no orphan process, and interrupted runs resumable shard by shard, so that a night's work is never lost. Independent
test: kill the worker during shard k of n; resume executes only the missing shards, and no process of the killed tree
survives.

### US-002-5 (P1) Evidence for every run
As a reviewer, I want each run to write a manifest with versions read from the locks, seeds, cache keys, telemetry
summaries, retries and licence-correct performance markers, and `studio publish` to turn a run into web artefacts
without leaking local-only metrics or machine details, so that every published number is traceable. Independent test:
publish a fake run with one local-only stage; the published manifest validates (spec 001) and contains no metric of
that stage.

### US-002-6 (P2) Maintenance commands
As the maintainer, I want `studio gc`, `studio bench env`, `studio profile`, `studio queue` and `studio status`, so
that the store stays within disk, the capability probe and profiling run through the same guards, and I can see and
cancel work. Independent test: `gc` on a seeded store deletes exactly the unreachable objects and nothing a kept
manifest needs.

Story index (for traceability):

| ID | Priority | Story |
|---|---|---|
| US-002-1 | P1 | Plan anywhere, without the GPU |
| US-002-2 | P1 | One heavy GPU job at a time, with guards |
| US-002-3 | P1 | Never redo finished work |
| US-002-4 | P1 | Survive interruptions |
| US-002-5 | P1 | Evidence for every run |
| US-002-6 | P2 | Maintenance commands |

## 3. Functional requirements (EARS)

Tables named "plan.md D1…D7" are normative parts of the requirements that cite them (command line, exit codes, store
layout, profile, job spec, events, code roots).

### 3.1 Recipes, DAG and plan

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-01 | Event | When `studio plan <recipe> --profile <id> [--json]` runs, the runner shall load and validate the recipe and profile (spec 001 loaders), build the DAG of stage keys (`id`, `variant`) and print, per stage in a deterministic topological order (ties broken by key), the key, environment, tool, lock to take, cache key or `pending`, `hit`/`miss`/`pending`/`env-disabled`/`does-not-fit`, VRAM and disk estimates and shard count, then exit 0 within 5 s for a 64-stage recipe. | unit |
| FR-002-02 | Ubiquitous | `studio plan` shall not import an NVML binding, acquire any lock, start any process or write to the store, so that it works while `gpu0.hold` exists. | unit (import and call spies) |
| FR-002-03 | Unwanted | If a recipe has a cycle, a reference to an unknown stage key or output, duplicate stage keys, an OOM-fallback key absent from `params`, a `requires` probe unknown to `studio/bench/run_bench.py`, a tool id absent from `studio/tools.yaml`, an output validator id that is neither a runner-side validator nor declared stage-side (plan.md D3), or more than 10,000 shards, then `studio plan` and `studio run` shall exit 2 naming every offending stage and shall queue nothing. | unit (hostile) |
| FR-002-04 | Ubiquitous | The `--json` plan shall be RFC 8785 canonical JSON containing no absolute path, drive letter, backslash, host name, user name or home directory (patterns of spec 001 data-model §1.5); the store is shown only as `$PITSTUDIO_STORE`. | unit (hostile) |
| FR-002-05 | Optional | Where the profile is `linux-gpu`, the CI job `runner-plan` shall run `studio plan --json` for every recipe under `studio/recipes/cases/` and `studio/recipes/_bench/` on an Ubuntu runner with the fake GPU backend, and shall fail if any plan exits non-zero or leaks (FR-002-04); stages whose environment the profile does not enable are reported `env-disabled`, not as errors (refines FR-000-16). | CI |
| FR-002-06 | Unwanted | If a stage's VRAM estimate plus margin exceeds the largest device VRAM known to the plan (profile `gpus`, or the fake device), or its environment is not enabled by the profile, then the plan shall mark it `does-not-fit` or `env-disabled`, and `studio run` shall refuse that stage with exit code 5 before taking any lock. | unit |
| FR-002-07 | Optional | Where a Linux host is used, the CI job `runner-container` shall build `studio/containers/Dockerfile.open` (uv's container pattern, base image pinned by SHA-256, `uv sync --locked`) and run the runner and contract tests marked `not gpu` inside it with 0 failures. | CI |

### 3.2 Cache and store

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-08 | Ubiquitous | The cache key of a stage execution shall be the lowercase hex SHA-256 of the RFC 8785 canonical JSON of `{"stage": {"id", "variant"}, "code": h_code, "lock": h_lock, "params": p, "seed": σ, "inputs": {name: sha256}, "binaries": {id: sha256}, "shard": {"index", "size", "total"} or null}`, where `h_code` is the code-root digest of plan.md D7, `h_lock` the SHA-256 of the environment's lock file bytes, `p` the effective parameters, `inputs` maps each source id to its pinned digest and each upstream `<stage key>/<output path>` to that output's SHA-256. | unit + property |
| FR-002-09 | Ubiquitous | The derived seed shall be σ = `int.from_bytes(SHA256(JCS([σ0, key, i]))[0:8], "big") & (2⁶³ − 1)`, where σ0 is the recipe seed, key the stage key string (`id` or `id@variant`) and i the shard index (0 for unsharded stages); e.g. σ0 = 20261004, `st50_physics`, i = 0 gives 2175241071291199046, and i = 1 gives 3347990621277448462. | unit |
| FR-002-10 | Event | When a stage's cache key has an index entry in the store and every referenced object exists with the recorded size (and, for objects ≤ 256 MiB, the recorded SHA-256), the runner shall materialise the outputs into the run without launching any process and record `cache: hit`. | unit (launcher spy) |
| FR-002-11 | Unwanted | If a store object's size or SHA-256 differs from its name or index record, then the runner shall treat the key as a miss, move the object to `quarantine/`, emit a `store-corrupt` event and never hand the corrupted bytes to a stage. | unit (hostile) |
| FR-002-12 | Ubiquitous | A stage shall write only into `runs/<run_id>/tmp/<stage key>/<shard>/`; after it exits 0 the runner shall check every declared output (exists, regular file, inside the folder, validator of plan.md D3 passes), hash it, and promote it to `cas/sha256/<first two hex>/<digest>` by `os.replace`, writing the index entry last, so that the store never holds a partial object or an index entry without its objects. | unit + property |
| FR-002-13 | Unwanted | If a declared output is missing, is a symbolic link, resolves outside the stage folder or fails its validator, then the stage shall fail with `error_class: invalid-output`, no output of that execution shall enter the store, and downstream stages shall be `skipped`. | unit (hostile) |
| FR-002-14 | Event | When `studio run --force` is given, the runner shall execute the selected stages even on a hit and shall replace the index entry only after the new outputs are promoted. | unit |

### 3.3 Locks, hold and guards

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-15 | Ubiquitous | A stage with `resources.gpu: exclusive` shall hold `GPU_LOCK_DIR/gpu<N>.compute`, and one with `gpu: nvenc` shall hold `gpu<N>.nvenc`, through `filelock` for the whole execution including retries, releasing it on every exit path (success, failure, timeout, cancel, exception); `GPU_LOCK_DIR` defaults to `gpu-locks` in the system temporary folder, exactly as `studio/bench/run_bench.py` (refines FR-000-13). | unit (fake GPU) |
| FR-002-16 | Unwanted | If `GPU_LOCK_DIR/gpu0.hold` exists (tested with `os.path.lexists`, so a directory or a broken link also counts) when a command that may run GPU work starts, then the runner shall print `GPU hold in <lock dir>/gpu0.hold: <reason> -- not starting`, where the reason is the first 4,096 bytes decoded as UTF-8 with replacement, stripped and cut to 300 characters (or `no reason given`), and exit 4 before importing an NVML binding or `filelock` (refines FR-000-13). | unit (import spy) |
| FR-002-17 | Event | When a GPU stage or GPU shard is about to start, the runner shall re-check the hold; if it exists, the runner shall start no further stage or shard, let nothing new begin on the GPU, set the job to `held` with the reason, keep the run resumable and exit 4. | unit |
| FR-002-18 | State | While another process holds the needed GPU lock, the runner shall poll at most every 5 s, re-check the hold on every poll, and after the profile's `lock_wait_s` set the job to `blocked` (`error_class: lock-timeout`) and exit 3 without starting the stage. | unit (fake clock) |
| FR-002-19 | Event | When a GPU stage is about to start, the runner shall require device free VRAM ≥ ⌈`vram_gib_est` × 2³⁰⌉ + `vram_margin_gib` × 2³⁰ (margin ≥ 1.5 GiB), and GPU temperature ≤ `max_start_temp_c` (≤ 80 °C) — polling every 10 s for up to `cooldown_wait_s` when hotter — and otherwise shall refuse the stage with reason `vram` or `temp` and exit 5. | unit (fake GPU) |
| FR-002-20 | Event | When any stage is about to start, the runner shall require free bytes on the store volume ≥ ⌈`disk_gib_est` × 2³⁰⌉ + `disk_margin_gib` × 2³⁰ (margin ≥ 20 GiB) and, where the profile sets a quota for the stage id, the stage's stored bytes plus its estimate ≤ that quota, and otherwise shall refuse with reason `disk` or `quota` and exit 5. | unit (fake disk) |
| FR-002-21 | Unwanted | If a stage lists `requires` probes and `studio/capabilities.json` is missing, invalid, lacks a listed probe, reports it with a status other than `pass`, or reports a `driver` different from the live (or fake) driver, then the runner shall refuse the stage with reason `capability` or `capability-stale` and exit 5, without crashing. | unit (hostile) |
| FR-002-22 | Unwanted | If the GPU backend cannot initialise (no driver, no device, NVML error), then GPU stages shall be refused with reason `no-gpu` (exit 5) and CPU stages (`gpu: none`) shall run normally. | unit (fake GPU) |
| FR-002-23 | Ubiquitous | CPU stages (`gpu: none`) shall take no GPU lock and shall not be blocked by another process's GPU lock; the hold stops GPU stages only. | unit |

### 3.4 Execution, process control and telemetry

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-24 | Ubiquitous | The runner shall launch each stage execution as the argument list `uv run --project <env dir> --frozen python -m <entry> --job <job.json>` (environment directories in plan.md D7; never through a shell), with a job spec valid against `contracts/job.schema.json` (plan.md D5) and the environment variables `PITSTUDIO_RUN_ID`, `PITSTUDIO_STAGE`, `PITSTUDIO_SHARD`, `PITSTUDIO_SEED`, `PITSTUDIO_NVTX_RANGE`, `PITSTUDIO_CPU_SLOTS`, `PITSTUDIO_VRAM_FRACTION` (GPU stages), `CUDA_VISIBLE_DEVICES` and a `PYTHONPATH` entry for the standard-library-only stage helper `pitstudio_stagekit`. | unit (launcher spy) |
| FR-002-25 | Unwanted | If a stage exits without a `result.json`, writes one that is invalid against `contracts/job.schema.json#/$defs/stage_result`, larger than 65,536 bytes, or inconsistent with its exit code, then the runner shall record `error_class: invalid-result` and treat the execution as failed. | unit (hostile) |
| FR-002-26 | Ubiquitous | The stage helper `pitstudio_stagekit` (Python ≥ 3.12, standard library only) shall read the job spec, open an NVTX range named `PITSTUDIO_NVTX_RANGE` where the `nvtx` module is importable, apply `torch.cuda.set_per_process_memory_fraction(PITSTUDIO_VRAM_FRACTION)` where `torch` with CUDA is importable, run the stage function, and always write `result.json` (an exception becomes `failed`, a CUDA out-of-memory exception `error_class: oom`). | unit (fake `nvtx`/`torch` modules) |
| FR-002-27 | Optional | Where the OS is Windows, the runner shall assign every stage process to a job object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, and where it is Linux, start it in a new process group; after a cancel, a timeout or the death of the runner process (Windows), every process of the tree shall be gone within 10 s. | unit (Windows CI job; Linux CI job) |
| FR-002-28 | Unwanted | If a stage execution exceeds `timeout_s`, then the runner shall end its process tree within 10 s, record `error_class: timeout` (or `warmup-timeout`, FR-002-33), release its locks and stop its telemetry. | unit (fake stage) |
| FR-002-29 | Optional | Where the OS is Windows and the profile sets `keep_awake: true`, the runner shall call `SetThreadExecutionState(ES_CONTINUOUS \| ES_SYSTEM_REQUIRED)` while the queue holds a queued or running job and `SetThreadExecutionState(ES_CONTINUOUS)` when it becomes empty and on every exit path, including exceptions. | unit (power-API spy) |
| FR-002-30 | State | While a GPU stage runs, the runner shall sample the GPU backend at the profile's `telemetry_hz` (1–4 Hz) into `runs/<run_id>/telemetry.jsonl` (one sample per line, flushed per line, fields of plan.md D6), yielding ⌊T × hz⌋ ± 1 samples over T seconds. | unit (fake GPU, fake clock) |
| FR-002-31 | Event | When a GPU stage ends, the runner shall write its telemetry summary to the manifest as defined in spec 001 data-model §2.4 (type-7 percentiles; `power_at_limit_frac` = share of samples with power ≥ 0.95 × enforced limit; `energy_j` = (last − first energy counter in mJ) / 1,000; `clocks_event_frac` from the NVML bits of plan.md D6), and set `thermal_flag` when the `hw_thermal` or `hw_slowdown` fraction exceeds 0.05. | unit + property |
| FR-002-32 | Unwanted | If the backend reports a field as unsupported, raises for it, or returns a non-finite or negative value, then the sample shall store `null` for that field, the summary shall use only the valid samples of that field and, when none remains, store `null` and name the field in `unavailable` with its reason and the count of invalid samples, and no value shall be guessed or set to 0. | unit (fake GPU, hostile) |
| FR-002-60 | Event | When a stage reports that it cannot run for a reason outside its control (a missing, unpinned or too-new external tool, a driver below the tool's floor, an unavailable proprietary runtime or optional input) — by raising `pitstudio_stagekit.NotRun(reason)`, which the stage helper turns into a stage result with `status: not_run`, a mandatory `reason` of 1–300 characters, no outputs and exit code 0 — the runner shall record the stage as `not_run` with that reason in the manifest and in a `stage-not-run` event, promote nothing, not retry it, mark every downstream stage `skipped` with the reason `upstream not run: <stage key>`, print one line `not run: <stage key>: <reason>`, never record it as `succeeded`, and end the job `succeeded` (exit 0) only if no other stage failed (honesty, FR-000-07). | unit (fake stage) |
| FR-002-61 | Unwanted | If a stage result has `status: not_run` with a missing or empty `reason`, a `reason` longer than 300 characters, any listed output, a non-null `error_class` or a non-zero process exit code, then the runner shall record `error_class: invalid-result`, treat the execution as failed (FR-002-25) and promote nothing. | unit (hostile) |
| FR-002-62 | Ubiquitous | The runner shall pass to every stage process the environment variable `PITSTUDIO_HELD_LOCKS`: the sorted, comma-separated names of the machine-wide locks it holds for that execution (for example `gpu0.compute`, or `gpu0.compute,gpu0.nvenc` should a stage hold both), or the empty string for a stage that holds none; and the stage helper shall expose it as `pitstudio_stagekit.held_locks()`, a frozen set of lock names. | unit (launcher spy) |
| FR-002-63 | Unwanted | If a stage is about to start GPU work — create a CUDA context, launch a GPU kernel or start an NVENC encode — and `PITSTUDIO_HELD_LOCKS` is unset, malformed (an entry not matching `^gpu[0-9]{1,2}\.(compute\|nvenc)$`, a duplicate entry, more than 4 entries or more than 64 characters) or does not list the lock that work needs (`gpu<N>.compute` for compute work, `gpu<N>.nvenc` for an encode), then the stage helper's guard `pitstudio_stagekit.require_lock(kind, device)` shall raise `LockNotHeldError` before any GPU work starts, and the stage result shall be `failed` with `error_class: lock-not-held` and a message naming the missing lock. | unit (hostile, fake GPU) |

### 3.5 Retries, resume and determinism

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-33 | Event | When an execution fails with `error_class: oom` (from `result.json`, or with no result when the last 200 log lines match `CUDA out of memory\|OutOfMemoryError\|cudaErrorMemoryAllocation\|CUDA_ERROR_OUT_OF_MEMORY`, case-insensitive), the runner shall retry with the next `oom_fallback` override merged into the effective parameters, at most once per declared step; and when the first attempt of a stage in env `isaac`, `rtx` or `kit` times out, it shall retry once with the same parameters (`warmup-timeout`). Each attempt is recorded in `attempts[]`, and the effective parameters enter the cache key. | unit (fake stage) |
| FR-002-34 | Unwanted | If an execution fails for any other reason, or with `oom` after the last fallback step, then the runner shall not retry, shall record the last 50 log lines (≤ 4,000 characters, paths scrubbed to `<repo>`/`~`/`$PITSTUDIO_STORE`) as `log_tail`, mark every downstream stage `skipped`, and exit 1. | unit (hostile) |
| FR-002-35 | Ubiquitous | A stage with `shardable` shall run as ⌈total / shard_size⌉ executions, each with its own seed, cache key and promotion, so that a completed shard is a cache hit for any later run. | unit |
| FR-002-36 | Event | When `studio run --resume <run_id>` is given for an interrupted, held, blocked or failed run, the runner shall reuse that `run_id` and its manifest, execute only executions without a promoted index entry, and append to `events.jsonl` and `telemetry.jsonl`. | unit (fake stage) |
| FR-002-37 | Event | When the worker starts and finds jobs in state `running` whose recorded process no longer exists, it shall set them to `interrupted` with reason `worker-restart` before taking any new job. | unit |
| FR-002-38 | Event | When `studio run --rerun-check` is given, the runner shall re-execute shard 0 of each `bitwise` and `statistical` stage into a scratch folder, bypassing the cache, and record `rerun_check: pass` iff all output SHA-256 values match (bitwise) or every declared observable satisfies \|a − b\| ≤ atol + rtol × \|b\| (statistical), with `max_deviation`; `none` stages get `not-applicable`. | unit (fake stage) |

### 3.6 Queue, command line and profiles

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-39 | Ubiquitous | The runner shall keep one queue per store in `queue.db` (SQLite, WAL mode, busy timeout ≥ 5 s) with the job states of plan.md D3, allow one worker per store through `locks/worker.lock`, and expose `enqueue(job_request) -> job_id`, `cancel(job_id)`, `jobs()` and `job(job_id)` as the Python API used by the command line and the console. | unit |
| FR-002-40 | Event | When `studio run <recipe> [--stage <key>…] [--force] [--rerun-check] [--detach] --profile <id>` is given, the runner shall enqueue one job and, unless `--detach` is given or another worker holds `locks/worker.lock`, run a foreground worker until that job ends, returning the job's exit code (plan.md D2). | unit |
| FR-002-41 | Event | When `studio queue cancel <job_id>` is given, a queued job shall become `cancelled` at once and a running job shall have its process tree ended within 10 s, its locks released and its state set to `cancelled` (exit 6 for the worker running it). | unit |
| FR-002-42 | Unwanted | If a command receives an unknown subcommand or option, a recipe path that is not a `.yaml` file inside the repository's `studio/recipes/` (after resolving links), an unknown profile, a stage key absent from the recipe, a malformed run or job id, a negative `--keep-last`, a relative, over-64-character (Windows), unwritable or in-repository `PITSTUDIO_STORE`, or a `GPU_LOCK_DIR` that is relative or not a directory, then it shall exit 2 with a one-line message and change nothing. | unit (hostile) |
| FR-002-43 | Ubiquitous | Every command shall use the exit codes of plan.md D2 (0 success, 1 stage failure, 2 usage or validation error, 3 lock held, 4 GPU hold, 5 guard refused, 6 cancelled or interrupted). | unit |
| FR-002-58 | Event | When `studio queue ls [--json]` or `studio status [--json]` is given, the runner shall print, within 1 s for a queue of 1,000 jobs, every job's id, recipe, state, run id, current stage and shard progress (status adds the active locks and the hold reason, if any), reading the queue without taking the worker lock; and when `studio worker` is given, it shall take `locks/worker.lock` (exit 3 if held) and run jobs until the queue is empty. | unit |
| FR-002-44 | Ubiquitous | The repository shall hold `studio/recipes/_profiles/laptop-rtx5000ada.yaml` and `linux-gpu.yaml`, valid against `contracts/profile.schema.json` (plan.md D4), and no recipe shall contain machine-specific data. | contract |
| FR-002-45 | Unwanted | If a profile sets a guard below its floor (VRAM margin < 1.5 GiB, disk margin < 20 GiB, start temperature > 80 °C), `telemetry_hz` outside 1–4, a process control that does not match its OS, an unknown environment, or a store default that is not a short machine-neutral absolute path (plan.md D4), then loading it shall fail with exit 2. | unit (hostile) |

### 3.7 Manifests and publication

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-46 | Ubiquitous | Every run shall maintain `runs/<run_id>/manifest.json` (spec 001 `kind: run`, `published: false`), rewritten atomically at each stage end, and `runs/<run_id>/events.jsonl` valid line by line against `contracts/events.schema.json` (plan.md D6), with a strictly increasing `seq`. | contract |
| FR-002-47 | Ubiquitous | `env.versions` of each stage shall be read from the environment's lock file for the packages of its tool's registry entry and the stage helper (never typed), `performance` shall be copied from the tool's registry entry, and `gpu.backend` shall record `nvml` or `fake`. | unit (lock fixtures) |
| FR-002-48 | Event | When `studio publish <run_id> [--release-tag <tag>]` is given, the runner shall write `web/public/assets/runs/<run_id>/manifest.json` (`published: true`, local-only stages scrubbed, `log_tail` removed), copy each output marked `publish: true` that is < 10 MiB under `web/public/assets/<run_id>/` (`asset_host: git`), place larger ones under `$PITSTUDIO_STORE/publish/<release tag>/` for the asset release (`asset_host: release`), add the artefact records (lane computed by spec 001's `lane_of`, licence class by `licence_class_of`, `spdx`/`attribution` by the rule of plan.md D3) to `web/public/assets/manifest.json`, write downsampled telemetry of public stages only to `web/public/assets/runs/<run_id>/telemetry.json` (`contracts/events.schema.json#/$defs/published_telemetry`), pin the run, and validate everything with spec 001's checks before any file is replaced. | contract + unit |
| FR-002-49 | Unwanted | If the run is unknown, not finished, from a dirty tree, from the fake backend or the test launcher, has a published output from a non-succeeded stage, uses an unpinned source, needs a release tag that was not given or is malformed, or any spec 001 check fails, then `studio publish` shall exit 2 naming the reason and leave every repository file unchanged. | unit (hostile) |
| FR-002-50 | Ubiquitous | Published telemetry shall have ≤ 2,000 points per stage (equal-time buckets: mean of utilisation, power and clock; maximum of temperature and memory; bitwise OR of clock-event masks) and ≤ 200 KB per run, halving the bucket count deterministically until it fits. | unit |

### 3.8 Maintenance commands and the fake backend

| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-002-51 | Event | When `studio gc [--keep-last N] [--dry-run] [--verify]` is given, the runner shall keep every run that is pinned, referenced by `web/public/assets/manifest.json` or `models/cards/*/manifest.json`, queued or running, or among the newest N per recipe (default 3), delete store objects, index entries and run folders reachable from no kept run, and print the bytes freed; `--keep-pinned` is accepted and always in effect; `--verify` re-hashes every kept object and quarantines mismatches. | unit + property |
| FR-002-52 | Unwanted | If a worker holds `locks/worker.lock` when `studio gc` starts, then gc shall delete nothing and exit 3. | unit |
| FR-002-53 | Event | When `studio bench env [probe…] [--timeout S] [--no-write]` is given, the runner shall call `studio/bench/run_bench.py`'s `main` with the same arguments and return its exit code unchanged (0–4), so that under a hold it exits 4 without importing an NVML binding. | unit |
| FR-002-54 | Event | When `studio profile <recipe> --stage <key> --profile <id>` is given, the runner shall execute that stage once under the normal locks, hold check and guards with `PITSTUDIO_PROFILE=1`, uncached and unpublishable, collect the stage's profiler outputs in its run folder, and print an `nsys profile --trace=cuda,nvtx …` command for the maintainer without ever executing `nsys`. | unit (launcher spy) |
| FR-002-55 | Ubiquitous | A fake GPU backend, selected by `PITSTUDIO_GPU_BACKEND=fake:<device file>` or `--gpu-backend fake:<device file>`, shall answer every backend query (name, driver, total and free VRAM, temperature, power and enforced limit, utilisation, SM clock, clock-event mask, energy counter, encoder utilisation, PCIe replays, initialisation failure) from a device file valid against `contracts/profile.schema.json#/$defs/fake_device` with scripted time series, and every runner test of `tests/` shall run against it without a GPU. | unit |
| FR-002-56 | Unwanted | If the fake backend is selected, then the runner may use the current interpreter as a test launcher instead of `uv run`, shall record `gpu.backend: fake` and `launcher: test`, and `studio publish` shall refuse the run (FR-002-49). | unit |
| FR-002-57 | Unwanted | If the fake device file is missing, invalid, or scripts a non-finite value, then the command shall exit 2 naming the file and pointer. | unit (hostile) |
| FR-002-59 | Optional | Where an NVIDIA GPU, its driver and `nvidia-ml-py` are available and no hold exists, the NVML backend shall report the GPU name, driver version and total memory equal to `nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits`, temperature within ±3 °C and enforced power limit within ±1 W of the same query taken within 2 s; if any of them is unavailable, the test shall report "not run" with the reason. | integration (gpu) |

## 4. Correctness properties

| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-002-01 | Cache-key determinism: equal (stage key, code root, lock, effective params, seed, inputs, binaries, shard) give the same key in a new process, under a different working directory, store root, profile, host name or OS (refines P-000-01). | Hypothesis recipes × environment permutations | exact |
| P-002-02 | Cache-key sensitivity: changing exactly one of the components (one param value, one byte of one code file, one byte of the lock, the seed, one input digest, one binary digest, the shard index) changes the key. | Hypothesis single-component mutations | exact |
| P-002-03 | Syntax and order invariance: reformatting the recipe YAML (comments, key order, flow vs block, `4.50` vs `4.5`) and permuting its `inputs` list leave every cache key unchanged. | Hypothesis renderings of one recipe | exact |
| P-002-04 | Propagation: after changing one parameter of stage s, the plan shows s as `miss`, every DAG descendant of s as `pending` or `miss`, and every other stage with its previous key and status. | Hypothesis DAGs (2–64 nodes) | exact |
| P-002-05 | Seed derivation: the seed equals the FR-002-09 formula; over 10⁵ distinct (key, shard) pairs no two seeds collide. | Hypothesis keys and shard indices | exact |
| P-002-06 | Store integrity: for every interruption point of a promotion (fault injected before, between and after write, rename and index write), every file under `cas/` has a name equal to the SHA-256 of its content and every index entry references only existing objects. | fault-injection points × fake outputs | exact |
| P-002-07 | Resume equivalence: interrupting a sharded bitwise fake stage at any shard k of n and resuming yields the same set of shard output digests as an uninterrupted run, and each shard is executed exactly once after its last successful promotion. | k ∈ 0…n−1, n ∈ 1…20 | exact |
| P-002-08 | Telemetry-summary metamorphic relations: (a) permuting samples leaves means, percentiles, maxima and fractions unchanged; (b) multiplying power and enforced limit by c > 0 scales the power statistics by c and leaves `power_at_limit_frac` unchanged; (c) duplicating every sample leaves means, percentiles and fractions unchanged; (d) a constant power P over T s with a counter advancing P × 1,000 mJ/s gives `energy_j` = P × T. | Hypothesis series (1–10,000 samples, finite non-negative values; for (b) no sample within 10⁻⁹ relative of the 0.95 × limit boundary) | means rtol 1e-9; percentiles, maxima and fractions exact; (d) exact (integer mJ) — justification in plan.md |
| P-002-09 | Mutual exclusion: for K = 2…6 runner processes contending for `gpu0.compute` with fake compute stages, no two recorded [enter, exit] intervals inside a compute stage overlap. | process counts × stage durations | exact |
| P-002-10 | Guard monotonicity: more free VRAM or disk, or a lower temperature, never turns a pass into a refusal; a larger VRAM or disk estimate never turns a refusal into a pass. | Hypothesis guard inputs | exact |
| P-002-11 | GC safety: after `studio gc`, every kept run's outputs materialise with their recorded SHA-256; a second `gc` frees 0 bytes. | Hypothesis store states (runs, pins, shared objects) | exact |
| P-002-12 | Plan independence: the `--json` plan of one recipe and profile is byte-identical across working directories, store roots, host and user names and `sys.platform` values. | recipes × monkeypatched environments | exact |

## 5. Non-functional requirements and success criteria

| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-002-01 | Runner size: non-blank, non-comment-only lines of `src/pitstudio/runner/**/*.py` (docstrings counted; generated contract models excluded) (refines NFR-000-08) | ≤ 1,500 | CI line count (T-002-002) |
| NFR-002-02 | Plan latency for a 64-stage recipe with 10,000 shards, fake backend | ≤ 5 s | pytest timer |
| NFR-002-03 | Runner overhead per stage execution (launch, guards, promotion of 1 MB of outputs), excluding the stage's own run time | ≤ 1.0 s | pytest timer with a no-op fake stage |
| NFR-002-04 | Lock recovery after the holding process is killed | a new `acquire` succeeds within 10 s | unit (kill the holder) |
| NFR-002-05 | Mutation score of the cache key, seed, guard and telemetry-summary modules | ≥ 0.80 (`mutation.numerical_core_min`) | mutation run (T-002-090) |
| SC-002-01 | CI planning of every recipe with `linux-gpu` | 100 % exit 0, 0 leaks, on every push after the build phase | CI history |

## 6. Data contracts

| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-002-01 | machine profiles `studio/recipes/_profiles/*.yaml`; fake device files | `contracts/profile.schema.json` (`$defs/fake_device`) | maintainer, tests → runner |
| DC-002-02 | job spec `runs/<run_id>/tmp/<stage>/<shard>/job.json`; stage result `result.json` (status `succeeded`, `failed` or `not_run` with its reason) | `contracts/job.schema.json` (`$defs/job_spec`, `$defs/stage_result`) | runner → stage environment → runner |
| DC-002-03 | `runs/<run_id>/events.jsonl`, `runs/<run_id>/telemetry.jsonl`; published `web/public/assets/runs/<run_id>/telemetry.json` | `contracts/events.schema.json` (`$defs/event`, `$defs/telemetry_sample`, `$defs/published_telemetry`) | runner → console (spec 003), `studio publish` → web `/studio/runs`, `/studio/gpu` |
| DC-002-04 | run manifests and published run manifests | `contracts/manifest.schema.json` (spec 001, DC-001-01) | runner → web app, CI |
| DC-002-05 | recipes and job requests | `contracts/recipe.schema.json` (spec 001, DC-001-02) | maintainer, console → runner |
| DC-002-06 | capability report read by the guards | `contracts/capabilities.schema.json` (spec 001, DC-001-05) | `run_bench.py` → runner |

## 7. Edge cases and assumptions

- **No GPU work in this spec's tests.** Every requirement is tested against the fake backend and fake stages; the real
  NVML backend gets one smoke test marked `gpu` (T-002-075), run only after the machine's GPU hold is lifted. If the
  NVML binding or a GPU is unavailable, that test reports "not run" (skip with the reason), never a pass.
- **One stage at a time per worker.** The worker runs one execution at a time in topological order; overlap between an
  encode and other work happens only across processes and is governed by the locks. This keeps "one heavy GPU job at a
  time" trivially true inside a worker and the runner within its budget.
- **Lock release after a crash.** `filelock` uses `LockFileEx` on Windows, and the OS releases a dead process's locks,
  but Microsoft notes that the release time "depends upon available system resources"; NFR-002-04 bounds it at 10 s
  and the runner still releases explicitly.
- **Linux orphans.** A process group is killed on cancel or timeout; if the runner itself dies on Linux, children are
  not killed automatically (no kill-on-close equivalent). The next worker start marks the job `interrupted`
  (FR-002-37); GPU work of an orphan would still hold the GPU lock until it exits.
- **Keep-awake limits.** `SetThreadExecutionState` cannot stop a lid close or the power button; resume (FR-002-36)
  covers it.
- **Per-process VRAM.** Not observable under Windows WDDM; the VRAM guard is device-level (docs `studio/runner.md`).
- **NVML clock-event bits** (pinned from `nvidia-ml-py` 13.615.71, module `pynvml`): GpuIdle 0x1,
  ApplicationsClocksSetting 0x2, SwPowerCap 0x4, HwSlowdown 0x8, SyncBoost 0x10, SwThermalSlowdown 0x20,
  HwThermalSlowdown 0x40, HwPowerBrakeSlowdown 0x80, DisplayClockSetting 0x100. The NVML web page lists the names but
  not the values; the values come from the binding in the root lock.
- **Units.** VRAM and disk estimates are GiB (2³⁰ B); NVML and `psutil` report bytes.
- **Cache of upstream outputs.** A stage's key depends on its inputs' output digests, so a stage downstream of a miss is
  `pending` in the plan; a no-op upstream change that reproduces bit-identical outputs keeps downstream hits.
- **No UNVERIFIED constants.** Guard margins and the thermal-flag fraction are design values from the studio design
  (docs `studio/runner.md`, `data-contract/manifest.md`), not external measurements; they are proposed for
  `thresholds.yaml` (plan.md).

## 8. Clarifications log

- Resolved — **console location.** The studio design research put the console under the core package with an extra
  named `console`; plan §9 and §12 and docs DEC-0003 put it in `api/` with the root `api` extra. The plan wins (spec
  003-console).
- Resolved — **telemetry file format.** Docs `studio/runner.md` and `data-contract/manifest.md` name
  `telemetry.parquet`; the plan fixes no format. This spec uses `telemetry.jsonl`: append-only and flushed per sample,
  so a crash loses at most one sample (a Parquet file is unreadable until its footer is written at close), the console
  can stream it (spec 003), and the root runner extra needs no Arrow dependency. Published telemetry is JSON (FR-002-50).
  The two docs pages need the rename (reported to the coordinator).
- Resolved — **store variable.** Docs use `PITSTUDIO_STORE`; an earlier design note used another name. Docs and plan
  win: `PITSTUDIO_STORE`.
- Resolved — **command set.** Plan §9 lists `studio bench env`, `plan`, `run`, `publish`, `profile`, `gc`; docs DEC-0002
  and `studio/runner.md` add `queue`, `worker`, `status`. All are specified (plan.md D1). `studio bench <suite>` from the
  design notes is not a command; benchmark suites are recipes under `studio/recipes/_bench/`.
- Resolved — **`studio run` semantics.** Docs say "`studio run` enqueues" and "one worker owns the queue". FR-002-40:
  enqueue, then run a foreground worker unless one is already running or `--detach` is given.
- Resolved — **exit codes.** Extended from the bench's 0–4 (docs `reference/cli.md`) with 5 (guard refused) and 6
  (cancelled or interrupted); `studio bench env` passes the bench's codes through.
- Resolved — **thresholds.** Docs `studio/runner.md` says guard thresholds are fixed in the thresholds file, which the
  coordinator owns; this spec states them (1.5 GiB, 20 GiB, 80 °C, 1–4 Hz, 5 s, 10 s, 0.05) and plan.md proposes the
  `runner:` keys.
- Resolved — **plan and the GPU.** Docs say both "planning never touches the GPU" and "plan … against a fake GPU
  backend". FR-002-02: plan never uses the real NVML backend; device capacity comes from the profile's `gpus`, or from
  the fake backend when selected.
- Resolved — **gc pins.** Docs name "pinned manifests (recipes on the main branch, release bundles)". Pins are: runs
  published by `studio publish`, runs referenced by the committed web index or model cards, queued or running jobs, and
  the newest N runs per recipe (FR-002-51).
- Resolved — **NVTX.** NVTX ranges must be opened inside the process that launches GPU kernels; the runner passes the
  range name and the stage helper opens it (FR-002-24, FR-002-26).
- Resolved — **environments without their own Python project.** `kit`, `reason` and `external` stages are launched
  through the `studio` project, and their pinned executables enter the cache key through `binaries` (plan.md D7).
- Integration 2026-10-07: the stage result gains the status `not_run` with a mandatory `reason` (FR-002-60, hostile
  FR-002-61; plan.md D5, event `stage-not-run` in D6), so that a stage that cannot run says so honestly (FR-000-07)
  instead of failing with a `not-run:` message prefix (the workaround of specs 005 and 006, now struck there). The
  runner exports the locks it holds to each stage process as `PITSTUDIO_HELD_LOCKS` (FR-002-62), and the stage
  helper refuses GPU work whose lock is not listed (FR-002-63, error class `lock-not-held`), replacing the stages'
  own zero-timeout probes of the lock files. Spec 001's manifest stage record gains the status `not_run`, the
  `reason` field and the error class `lock-not-held` to match. Tasks T-002-047 and T-002-048.
- Integration 2026-10-07: every `thresholds.yaml` key this spec proposes is marked "proposed key, pending maintainer
  approval" and compiled with the other specs' proposals for the maintainer; lane-gate keys are consolidated as
  `lane_gate.*` and budget keys as `budgets.*`.

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
- FR-002-01 … FR-002-63, P-002-01 … P-002-12, NFR-002-01 … NFR-002-05, SC-002-01, DC-002-01 … DC-002-06.
### MODIFIED Requirements
- (none) — `studio/bench/run_bench.py` keeps its behaviour; `studio bench env` wraps it (FR-002-53).
### REMOVED Requirements
- (none)
