# Tasks 002 — Runner
Format: `- [ ] T-NNN-xxx [US-NNN-x] (REQ IDs) description — test: <path::name>`
Rule: every task with requirement IDs is a `[red]`/`[green]` commit pair; each task's tests live in their own file(s)
and are locked after `[red]` (`python tools/lock_tests.py specs/002-runner/tests.lock <files>`). Every test runs
against the fake GPU backend and fake stages unless it is marked `gpu`.

## Phase 1 — Setup

- [ ] T-002-001 [US-002-1] (DC-002-01, DC-002-02, DC-002-03, FR-002-44, FR-002-45) schema + generated types: `contracts/profile.schema.json` (with `$defs/fake_device`), `contracts/job.schema.json` (`job_spec`, `stage_result`), `contracts/events.schema.json` (`event`, `telemetry_sample`) from plan.md D4–D6, generated through spec 001's generators; the two profiles of D4; dependency check before feature code (`uv add --dev networkx` resolves on 3.14; `[project.scripts] studio`); hostile profiles (margins below floors, `telemetry_hz` 0 or 5, wrong process control, unknown environment, user-specific store default) — test: tests/contract/test_t_002_001_runner_contracts.py
- [ ] T-002-002 (NFR-002-01) line-count rule (non-blank, non-comment-only lines of `src/pitstudio/runner/**/*.py`, docstrings counted) fixed by two hand-counted fixture files, then the budget assertion ≤ 1,500 on the real tree (runs on every push from the first runner commit) — test: tests/unit/test_t_002_002_loc_budget.py

## Phase 2 — US-002-1 (P1) Plan anywhere, without the GPU

- [ ] T-002-010 [US-002-1] (FR-002-01, FR-002-02, FR-002-03, FR-002-06, NFR-002-02) `studio plan`: DAG and deterministic order, statuses (`hit`, `miss`, `pending`, `env-disabled`, `does-not-fit`), no NVML import, no lock, no process, no store write, hostile recipes (cycle, unknown reference, duplicate key, unknown fallback key, probe, tool or validator, 10,001 shards), 64-stage / 10,000-shard timing — test: tests/unit/test_t_002_010_plan.py
- [ ] T-002-011 [US-002-1] (FR-002-04, P-002-12) canonical `--json` plan with no path, host, user or home leak, byte-identical across working directories, store roots, host and user names and `sys.platform` — test: tests/property/test_t_002_011_plan_independence.py
- [ ] T-002-012 [US-002-1] (FR-002-05, FR-002-07, SC-002-01, DC-002-05) `tools/plan_all_recipes.py --profile linux-gpu` (plans every recipe with the fake device `tests/fixtures/fake_gpu/linux-1x48gib.yaml`, fails on a non-zero exit or a leak), the CI jobs `runner-plan` and `runner-container`, and `studio/containers/Dockerfile.open` (pinned uv image and base digest) — test: tests/unit/test_t_002_012_plan_all_recipes.py

## Phase 3 — US-002-3 (P1) Never redo finished work

- [ ] T-002-020 [US-002-3] (FR-002-08, FR-002-09, P-002-01, P-002-02, P-002-03, P-002-05) cache key and derived seed: formula recomputed by hand, the two seed vectors, determinism across processes and environments, single-component sensitivity, YAML syntax and input-order invariance, no seed collisions over 10⁵ pairs — test: tests/property/test_t_002_020_cache_key.py
- [ ] T-002-021 [US-002-3] (FR-002-10, FR-002-11, FR-002-12, FR-002-13, FR-002-14, P-002-06) store: hits launch 0 processes, corruption → miss + quarantine, atomic promotion under injected faults, invalid outputs (missing, link, outside the folder, failing validator) never promoted, `--force` — test: tests/unit/test_t_002_021_store.py
- [ ] T-002-022 [US-002-3] (P-002-04) propagation of one parameter change through random DAGs, checked against networkx descendants — test: tests/property/test_t_002_022_propagation.py

## Phase 4 — US-002-2 (P1) One heavy GPU job at a time, with guards

- [ ] T-002-030 [US-002-2] (FR-002-15, FR-002-16, FR-002-17, FR-002-18, FR-002-23, P-002-09, NFR-002-04) machine-wide locks, hold before any GPU import (text, empty, binary, directory, broken link), hold appearing between shards, lock polling and `blocked`, CPU stages unaffected, mutual exclusion across 2–6 processes, lock recovery after the holder is killed — test: tests/unit/test_t_002_030_locks_hold.py
- [ ] T-002-031 [US-002-2] (FR-002-19, FR-002-20, FR-002-21, FR-002-22, P-002-10, DC-002-06) guards: VRAM, temperature with cool-down polling, disk and quota, capabilities (missing, invalid, failed, stale driver), no GPU; monotonicity — test: tests/unit/test_t_002_031_guards.py
- [ ] T-002-032 [US-002-2] (FR-002-55, FR-002-56, FR-002-57) fake GPU backend: every query from a device file, scripted series, initialisation failure, test launcher recorded as `launcher: test`, hostile device files — test: tests/unit/test_t_002_032_fake_backend.py

## Phase 5 — US-002-4 (P1) Survive interruptions

- [ ] T-002-040 [US-002-4] (FR-002-24, FR-002-25, NFR-002-03) launcher argument list and environment, job spec valid against its schema, hostile `result.json` files, per-execution overhead ≤ 1.0 s — test: tests/unit/test_t_002_040_launch.py
- [ ] T-002-041 [US-002-4] (FR-002-26) `pitstudio_stagekit`: standard-library-only import on 3.12 and 3.14, NVTX range and VRAM cap through fake `nvtx`/`torch` modules, exceptions and CUDA OOM become `result.json` — test: tests/unit/test_t_002_041_stagekit.py
- [ ] T-002-042 [US-002-4] (FR-002-27, FR-002-28) process-tree clean-up on cancel, timeout and runner death (job objects on Windows, process groups on Linux), ≤ 10 s, locks released; the CI job `runner-windows` — test: tests/unit/test_t_002_042_process_tree.py
- [ ] T-002-043 [US-002-4] (FR-002-29) keep-awake call sequence on queue non-empty, empty, normal exit and exception; no call on Linux — test: tests/unit/test_t_002_043_keep_awake.py
- [ ] T-002-044 [US-002-4] (FR-002-33, FR-002-34) classified retries: OOM from `result.json` and from log patterns, fallback steps merged into the key, warm-up timeout retried once for `isaac`/`rtx`/`kit`, everything else fails fast with a scrubbed log tail and skipped descendants — test: tests/unit/test_t_002_044_retries.py
- [ ] T-002-045 [US-002-4] (FR-002-35, FR-002-36, FR-002-37, P-002-07) shards as executions, `--resume` executing only missing shards, worker restart marking stale jobs `interrupted`, resume equivalence for every interruption point — test: tests/property/test_t_002_045_resume.py
- [ ] T-002-046 [US-002-4] (FR-002-38) `--rerun-check` for bitwise (SHA-256), statistical (observables with rtol/atol) and none stages — test: tests/unit/test_t_002_046_rerun_check.py
- [ ] T-002-047 [US-002-4] (FR-002-60, FR-002-61) `not_run` stage results: `NotRun(reason)` in the stage helper, manifest status and reason, `stage-not-run` event, skipped descendants, no retry, exit code; hostile `not_run` results — test: tests/unit/test_t_002_047_not_run.py
- [ ] T-002-048 [US-002-2] (FR-002-62, FR-002-63) `PITSTUDIO_HELD_LOCKS` exported per execution, `held_locks()` and `require_lock()` in the stage helper; GPU work refused with `lock-not-held` when the lock is not listed or the variable is malformed — test: tests/unit/test_t_002_048_held_locks.py

## Phase 6 — US-002-5 (P1) Evidence for every run

- [ ] T-002-050 [US-002-5] (FR-002-30, FR-002-31, FR-002-32, P-002-08) sampler rate with a fake clock, `telemetry.jsonl` lines, summary by hand and against `statistics.quantiles`, thermal flag, unsupported and invalid fields, the four metamorphic relations — test: tests/property/test_t_002_050_telemetry.py
- [ ] T-002-051 [US-002-5] (FR-002-46, FR-002-47, DC-002-04) run manifest and events valid against their schemas after every stage, strictly increasing `seq`, versions read from lock fixtures, `performance` from the registry, `gpu.backend` — test: tests/contract/test_t_002_051_run_manifest.py
- [ ] T-002-052 [US-002-5] (FR-002-48, FR-002-49, FR-002-50) `studio publish`: published manifest with local-only stages scrubbed, copies under 10 MiB, larger files staged under `$PITSTUDIO_STORE/publish/<release tag>/` with release-hosted index records, licence fields by plan.md D3, downsampled telemetry ≤ 2,000 points and ≤ 200 KB, pin; every refusal case leaves the repository unchanged — test: tests/contract/test_t_002_052_publish.py

## Phase 7 — US-002-2 / US-002-6 Queue and command line

- [ ] T-002-060 [US-002-6] (FR-002-39, FR-002-40, FR-002-41, FR-002-58) queue API and states, concurrent enqueues, `studio run` with and without `--detach` and a running worker, `queue cancel` of queued and running jobs, `queue ls`, `status`, `worker` — test: tests/unit/test_t_002_060_queue.py
- [ ] T-002-061 [US-002-6] (FR-002-42, FR-002-43) hostile command lines and environment variables (unknown options, recipe outside `studio/recipes/` or through a link, bad ids, negative `--keep-last`, bad `PITSTUDIO_STORE` and `GPU_LOCK_DIR`), exit codes of D2 — test: tests/unit/test_t_002_061_cli.py

## Phase 8 — US-002-6 (P2) Maintenance commands

- [ ] T-002-070 [US-002-6] (FR-002-51, FR-002-52, P-002-11) `studio gc`: pins, newest N per recipe, queued and running jobs kept, `--dry-run`, `--verify`, refusal while a worker runs, safety and idempotence against networkx reachability — test: tests/property/test_t_002_070_gc.py
- [ ] T-002-071 [US-002-6] (FR-002-53) `studio bench env` passes arguments and exit codes 0–4 through, and exits 4 under a hold with GPU libraries blocked — test: tests/unit/test_t_002_071_bench_env.py
- [ ] T-002-072 [US-002-6] (FR-002-54) `studio profile`: one uncached, unpublishable execution under locks and guards with `PITSTUDIO_PROFILE=1`, printed `nsys` command, `nsys` never spawned — test: tests/unit/test_t_002_072_profile_cmd.py
- [ ] T-002-075 [US-002-2] (FR-002-59) NVML backend smoke against `nvidia-smi` on the reference machine (marked `gpu`; reports "not run" when the GPU, driver or binding is unavailable; run only after the GPU hold is lifted) — test: tests/gpu/test_t_002_075_nvml_smoke.py

## Phase 9 — Polish and hostile review

- [ ] T-002-090 (NFR-002-05) mutation run on the cache-key, seed, guard and telemetry-summary modules; record the score and fail below 0.80 — test: tests/unit/test_t_002_090_mutation_score.py
- [ ] T-002-091 independent review of the diff against this spec (every FR/P has a locked test naming it; the LOC count; no GPU access outside `gpu` tests); append tasks for gaps
