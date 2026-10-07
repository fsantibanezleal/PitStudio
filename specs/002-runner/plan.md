# Plan 002 — Runner
Spec: ./spec.md

## Summary

`src/pitstudio/runner/` (root project, Python 3.14, extra `runner` = filelock, psutil, nvidia-ml-py) with a console
script `studio`. A recipe (spec 001) becomes a DAG of stage keys; each execution gets an RFC 8785 cache key over code,
lock, effective params, derived seed, input digests, binaries and shard (FR-002-08, -09). Hits are served from a
content-addressed store under `PITSTUDIO_STORE` (FR-002-10…14). GPU executions pass the hold check, the machine-wide
locks and the guards (FR-002-15…23), run as `uv run --project <env> --frozen python -m <entry>` inside a Windows job
object or a Linux process group, sampled by NVML at 1–4 Hz (FR-002-24…32), with classified retries, shards, resume and
re-run checks (FR-002-33…38). A single worker owns a SQLite queue (FR-002-39…43, -58); profiles hold every machine
fact (FR-002-44, -45); manifests, publication, gc, bench, profile and the fake backend complete it (FR-002-46…57).

## Technical context

Runtime: Python 3.14 (root `.venv`, extra `runner`: filelock 4.0.10, psutil 7.2.2, nvidia-ml-py 13.615.71); the stage
helper `pitstudio_stagekit` runs on Python ≥ 3.12 with the standard library only · uses spec 001's
`pitstudio.contracts` (loaders, validator, JCS, lane gate, licence lattice) · stdlib `sqlite3`, `hashlib`
(`file_digest`), `graphlib`, `ctypes` (Windows job objects, `SetThreadExecutionState`) · tests: pytest 9.1.1,
Hypothesis 6.168.3, networkx (test-only reference implementation, added to the `dev` group with `uv add --dev` in
T-002-001 after checking that it resolves on 3.14) · targets: Windows 11 (reference machine), Ubuntu CI runners, a
future Linux GPU host; no GPU in any CI job.

## Constitution check

| Principle | Pass? | Note / justification |
|---|---|---|
| 1. Real, not demo | yes | the runner drives the real stages; fake stages and the fake backend exist only to test it, and anything they produce is unpublishable (FR-002-56) |
| 2. Spec before code | yes | every module below maps to FR/P ids; the command line and file formats are fixed in D1–D7 |
| 3. Acceptance-test-first | yes | tasks.md pairs; the fake backend and fake stages are written in the `[red]` commits as test fixtures |
| 4. Independent oracles | yes | hand calculation (keys recomputed from the formula with `hashlib` on inputs where `json.dumps(sort_keys=True, separators=(",", ":"))` equals RFC 8785; seed vectors in FR-002-09); networkx for DAG order, cycles and descendants; Python `statistics.quantiles(method="inclusive")` (type 7) for percentiles; psutil for process trees; Python `jsonschema` against the schema files for every written document |
| 5. Determinism & explicit tolerances | yes | keys and seeds exact; P-002-08 tolerances justified below; fake clock for every timing requirement |
| 6. Neutral contracts | yes | profile, job spec, stage result, events and telemetry are JSON Schema files (DC-002-01…03) with generated types (spec 001) |
| 7. Static delivery | yes | the runner never runs in Pages; `studio publish` writes static files only |
| 8. Honesty | yes | local-only scrub at publish (FR-002-48); fake or dirty runs cannot be published (FR-002-49); unavailable telemetry is `null`, never 0 (FR-002-32) |
| 9. Licence hygiene | yes | performance marker from the tool registry (FR-002-47); licence class from the lattice (FR-002-48); binaries pinned by SHA-256 and never copied |
| 10. Simplicity | yes | one worker, one execution at a time; one backend protocol with two users (NVML, fake); no plugin system; LOC budget enforced (NFR-002-01) |

## Design

![Runner: recipe → plan → queue → guards and locks → workers → store → manifests](../../docs/assets/diagrams/runner-architecture.svg)

| Module (`src/pitstudio/runner/`) | Requirements | LOC budget |
|---|---|---|
| `cli.py` — argparse subcommands of D1, exit codes of D2 | FR-002-40…43, -53, -54, -58 | 120 |
| `recipe.py` — load recipe and profile, DAG (`graphlib`), plan, `--json` output | FR-002-01…06 | 140 |
| `cache.py` — code and lock digests, cache key, seed, store index, promotion, verification, quarantine | FR-002-08…14 | 140 |
| `locks.py` — lock directory, hold reader, `filelock` wrapper with polling | FR-002-15…18, -23 | 50 |
| `guards.py` — VRAM, temperature, disk, quota, capabilities | FR-002-19…22 | 70 |
| `gpu.py` — backend protocol, lazy NVML backend, fake backend | FR-002-22, -55…57 | 130 |
| `telemetry.py` — sampler thread, `telemetry.jsonl`, summary | FR-002-30…32 | 110 |
| `execute.py` — job spec, launcher, environment variables (incl. `PITSTUDIO_HELD_LOCKS`), timeouts, result parsing (incl. `not_run`), OOM classification, retries | FR-002-24, -25, -28, -33, -34, -60…62 | 180 |
| `oswin.py` — job objects, `SetThreadExecutionState` (ctypes); process groups on Linux | FR-002-27, -29 | 50 |
| `queue.py` — SQLite queue, job states, Python API | FR-002-39, -41 | 90 |
| `worker.py` — run loop, shards, resume, re-run check, manifest and events | FR-002-35…38, -46, -47 | 150 |
| `publish.py` — published manifest, copies, upload list, telemetry downsampling | FR-002-48…50 | 110 |
| `gc.py` — mark and sweep | FR-002-51, -52 | 60 |
| `stagekit/pitstudio_stagekit.py` — stage-side helper (stdlib only): `NotRun`, `held_locks()`, `require_lock()` | FR-002-26, -60, -62, -63 | 65 |
| **Total** | | **1,465** (≤ 1,500, NFR-002-01) |

Other files: `studio/recipes/_profiles/{laptop-rtx5000ada,linux-gpu}.yaml` (FR-002-44); `contracts/{profile,job,
events}.schema.json` (DC-002-01…03); `studio/containers/Dockerfile.open` (FR-002-07); CI jobs `runner-plan`,
`runner-container`, `runner-windows` in `.github/workflows/ci.yml` (FR-002-05, -07, -27); `pyproject.toml`
`[project.scripts] studio = "pitstudio.runner.cli:main"`.

### D1. Command line

| Command | Arguments |
|---|---|
| `studio plan <recipe>` | `--profile <id>` (required), `--json`, `--gpu-backend fake:<file>` |
| `studio run <recipe>` | `--profile <id>`, `--stage <key>` (repeatable; `id` or `id@variant`), `--force`, `--rerun-check`, `--detach`, `--resume <run_id>` (replaces `<recipe>`), `--gpu-backend fake:<file>` |
| `studio queue ls` / `studio queue cancel <job_id>` | `--json` (ls) |
| `studio worker` | `--gpu-backend fake:<file>` |
| `studio status` | `--json` |
| `studio gc` | `--keep-last N` (default 3), `--keep-pinned` (always on), `--dry-run`, `--verify` |
| `studio publish <run_id>` | `--release-tag assets-vX.YY.ZZZ` (required when an output ≥ 10 MiB is published) |
| `studio bench env [probe…]` | `--timeout S`, `--no-write` (passed to `run_bench.py`) |
| `studio profile <recipe>` | `--stage <key>` (required), `--profile <id>` |

Ids: `run_id` as spec 001 data-model §1.3; `job_id` = `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$`.

### D2. Exit codes

| Code | Meaning | Examples |
|---|---|---|
| 0 | success | plan printed; job succeeded; gc done |
| 1 | a stage failed | non-zero exit, invalid output, OOM after the last fallback |
| 2 | usage or validation error | unknown option, invalid recipe or profile, publish refused |
| 3 | a lock is held | GPU lock wait expired (`blocked`), worker or store lock held |
| 4 | GPU hold present | `gpu0.hold` exists (also passed through by `bench env`) |
| 5 | a pre-flight guard refused | `vram`, `temp`, `disk`, `quota`, `capability`, `capability-stale`, `no-gpu`, `does-not-fit`, `env-disabled` |
| 6 | cancelled or interrupted | `queue cancel`, Ctrl+C, worker restart |

### D3. Store, job states, validators and publication rule

```text
$PITSTUDIO_STORE/
  cas/sha256/<aa>/<digest>          immutable objects (name = SHA-256 of content)
  index/<aa>/<cache_key>.json       {stage key, outputs: [{name, sha256, bytes}], run_id, created}
  runs/<run_id>/                    manifest.json · events.jsonl · telemetry.jsonl · logs/ · tmp/ · PINNED (publish)
  views/<recipe>/<stage key>/       hard links to current outputs (copy when a link is not possible)
  quarantine/                       corrupted objects (FR-002-11)
  publish/<release tag>/            published files ≥ 10 MiB waiting for the asset release (FR-002-48)
  queue.db                          SQLite, WAL
  locks/worker.lock                 one worker per store
```

Job states: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `blocked`, `held`, `interrupted`.

Output validators: runner-side `file` (regular file, size > 0), `json` (spec 001 strict loader), `jsonl` (every line
strict JSON) and `contract-<stem>` (valid against `contracts/<stem>.schema.json`); any id starting with `stage-` is
stage-side and passes only when the stage's `result.json` reports `validated: true` for that output. Any other id is
unknown (FR-002-03).

Licence fields of a published artefact (FR-002-48), from c = `licence_class_of(inputs)` (spec 001):

| c | `licence_class` | `spdx` | `attribution` |
|---|---|---|---|
| public-domain, open-no-attribution, own | `own` | `Apache-2.0` for `onnx`, else `CC-BY-4.0` | optional |
| attribution | `attribution` | `Apache-2.0` for `onnx`; else `LicenseRef-Copernicus-CLMS` if any input has it, else `CC-BY-4.0` | inputs' attribution texts, deduplicated, joined by `; ` (≤ 1,000 characters, else publish fails) |
| share-alike | `share-alike` | the share-alike input's SPDX id | as above |
| display-only | `display-only` | `LicenseRef-NVIDIA-Open-Model` | `Built on NVIDIA Cosmos` + input texts |
| reference-only | — | — | publish refused |

### D4. Profile (`contracts/profile.schema.json`)

| Field | Type / constraint | `laptop-rtx5000ada` | `linux-gpu` |
|---|---|---|---|
| `id` | `slug` | `laptop-rtx5000ada` | `linux-gpu` |
| `os` | `windows` \| `linux` | windows | linux |
| `gpus` | array 0–16 of `{index, vram_bytes, power_class: laptop-power-limited\|desktop\|server}` | `[{0, 17179869184, laptop-power-limited}]` (nominal 16 GiB; live NVML value governs the guards) | `[]` (from the host; CI uses a fake device) |
| `store_default` | Windows `^[A-Z]:/[a-z0-9_-]{1,16}$` or POSIX `^/(srv\|data\|scratch)/[a-z0-9_-]{1,32}$`; used only when `PITSTUDIO_STORE` is unset | the documented short drive-root default | a `/srv/…` folder |
| `cpu_slots` | integer 1–256 | 8 | 8 |
| `envs_enabled` | array of recipe environments | all nine | `studio`, `pipeline`, `accel`, `external` |
| `process_control` | `job-object` (windows) \| `process-group` (linux) | job-object | process-group |
| `guards` | `{vram_margin_gib ≥ 1.5, disk_margin_gib ≥ 20, max_start_temp_c ≤ 80, cooldown_wait_s 0–3,600, lock_wait_s 0–86,400}` | 1.5 · 20 · 80 · 600 · 3,600 | 1.5 · 20 · 80 · 600 · 3,600 |
| `telemetry_hz` | number 1–4 | 2 | 2 |
| `keep_awake` | boolean (only `true` on windows) | true | false |
| `quotas` | map stage id → GiB (≤ 10,000) | `st55_sdg: 80`, `st50_physics: 30` | — |
| `binaries` | map `binary_id` → `env_var` naming the executable's path | `ffmpeg: PITSTUDIO_FFMPEG`, `llama-cpp: PITSTUDIO_LLAMA_CPP`, `colmap: PITSTUDIO_COLMAP`, `brush: PITSTUDIO_BRUSH`, `kit-app: PITSTUDIO_KIT_APP` | `ffmpeg: PITSTUDIO_FFMPEG` |

`$defs/fake_device`: `name`, `driver`, `vram_total_bytes`, `init_error` (boolean), `unsupported` (list of field names),
and `series`: per field (`free_bytes`, `temp_c`, `power_w`, `power_limit_w`, `util_pct`, `sm_clock_mhz`,
`clocks_event_mask`, `energy_mj_per_s`, `nvenc_util_pct`, `pcie_replays`) either a constant or a list of
`[t_s, value]` steps (≤ 10,000), all finite.

### D5. Job spec and stage result (`contracts/job.schema.json`)

`$defs/job_spec` (written by the runner, local only — it holds absolute local paths and is never published):
`schema_version`, `run_id`, `stage {id, variant?}`, `entry`, `params`, `seed`, `shard {index, size, total} | null`,
`inputs [{name, path, sha256}]`, `output_dir`, `scratch_dir`, `resume`, `rerun`, `profiling`, `profile {id,
cpu_slots}`, `vram_fraction` (0 < x ≤ 1, or `null`), `nvtx_range` (≤ 200 characters).

`$defs/stage_result` (written by the stage, ≤ 65,536 bytes): `schema_version`, `status: succeeded|failed|not_run`,
`error_class: oom|invalid-output|lock-not-held|unknown|null`, `reason` (1–300 characters; required iff `status:
not_run`, which also requires `error_class: null` and no outputs, FR-002-60, -61), `message` (≤ 300), `outputs [{path: relpath, validator?,
validated?: boolean, artefact?: {kind, media_type?, budget_class, cases?, lane_measurements?, encoder?}}]`,
`observables` (map ≤ 32 of finite numbers), `throughput {value, unit}?`, `checkpoint` (boolean).

### D6. Events, telemetry samples and NVML bits (`contracts/events.schema.json`)

`$defs/event` (one JSON line ≤ 16,384 bytes): `seq` (integer ≥ 1, strictly increasing per run), `t`
(`utc_timestamp`), `run_id`, `type` ∈ {`run-started`, `run-finished`, `stage-started`, `stage-finished`,
`stage-cache-hit`, `stage-retry`, `stage-skipped`, `stage-not-run`, `shard-finished`, `guard-refused`, `lock-waiting`, `lock-acquired`,
`hold-detected`, `store-corrupt`, `low-disk`, `cancelled`, `interrupted`}, `stage? {id, variant?}`, `shard?`,
`detail?` (≤ 300, scrubbed), `data?` (map ≤ 16 of scalars).

`$defs/telemetry_sample`: `t_s` (seconds since run start, ≥ 0), `run_id`, `stage`, `shard`, `gpu` (index), and
nullable `mem_used_bytes`, `mem_total_bytes`, `util_pct`, `power_w`, `power_limit_w`, `temp_c`, `sm_clock_mhz`,
`clocks_event_mask`, `energy_mj`, `nvenc_util_pct`, `pcie_replays`.

`$defs/published_telemetry` (`web/public/assets/runs/<run_id>/telemetry.json`, ≤ 200 KB): `run_id`, `stages` (≤ 64
of `{key {id, variant?}, performance: const public, bucket_s, points: ≤ 2,000 of {t_s, util_pct, power_w,
sm_clock_mhz, temp_c, mem_used_bytes, clocks_event_mask}}`), every numeric field nullable and finite.

`clocks_event_frac` keys ← NVML bits (`nvidia-ml-py` 13.615.71): `idle` 0x1, `sw_power_cap` 0x4, `hw_slowdown` 0x8,
`sw_thermal` 0x20, `hw_thermal` 0x40, `power_brake` 0x80.

### D7. Environments, launch projects and code roots

| `env` | `uv run --project` | Lock (`h_lock`) | Code roots (`h_code`) |
|---|---|---|---|
| `studio` | `studio` | `studio/uv.lock` | `studio/src` |
| `isaac` | `studio/isaac` | `studio/isaac/uv.lock` | `studio/isaac/src` |
| `rtx` | `studio/rtx` | `studio/rtx/uv.lock` | `studio/rtx/src` |
| `isaaclab` | `studio/isaaclab` | `studio/isaaclab/uv.lock` | `studio/isaaclab/src` |
| `pipeline` | `pipeline` | `pipeline/uv.lock` | `pipeline/src` |
| `accel` | `pipeline/accel` | `pipeline/accel/uv.lock` | `pipeline/accel/src` |
| `kit` | `studio` (launches the Kit app named in `binaries`) | `studio/uv.lock` | `studio/src`, `studio/kit` |
| `reason` | `studio` (launches llama.cpp) | `studio/uv.lock` | `studio/src`, `studio/reason` |
| `external` | `studio` (launches the pinned executable) | `studio/uv.lock` | `studio/src` |

`h_code` = SHA-256 of the RFC 8785 JSON list of `[POSIX relative path, SHA-256 of bytes]` for every regular file under
the code roots and under `src/pitstudio/runner/stagekit/`, sorted by path, excluding `__pycache__/`, `.venv/`,
`.pytest_cache/`, `*.egg-info/`, `node_modules/` and `*.pyc`. `.gitattributes` (`* text=auto eol=lf`) makes the bytes
equal on Windows and Linux checkouts.

### Proposed `thresholds.yaml` additions (proposed keys, pending maintainer approval)

```yaml
runner:
  loc_max: 1500                    # NFR-002-01 (= NFR-000-08)
  vram_margin_gib_min: 1.5         # FR-002-19
  disk_margin_gib_min: 20          # FR-002-20
  max_start_temp_c: 80             # FR-002-19 (= run_bench MAX_START_TEMP_C)
  telemetry_hz: [1, 4]             # FR-002-30
  lock_poll_s_max: 5               # FR-002-18
  kill_tree_s_max: 10              # FR-002-27, FR-002-28, FR-002-41
  thermal_flag_frac: 0.05          # FR-002-31
  power_at_limit_ratio: 0.95       # FR-002-31
  published_telemetry_points_max: 2000   # FR-002-50
  published_telemetry_kb_max: 200        # FR-002-50
  log_tail_lines: 50               # FR-002-34
  log_tail_chars_max: 4000
  plan_s_max: 5                    # NFR-002-02
  overhead_s_max: 1.0              # NFR-002-03
```

## Test strategy

| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-002-01 | unit | hand-derived topological order of fixture recipes; validity of the order checked with networkx (reference implementation) | pytest |
| FR-002-02 | unit | import blockers (`sys.modules["pynvml"] = None`, `filelock` likewise) and a `subprocess.Popen` that raises; store directory hash unchanged | pytest |
| FR-002-03 | unit (hostile) | hand-built hostile recipes; networkx `find_cycle` as reference for cycles | pytest |
| FR-002-04, P-002-12 | unit (hostile) / property | spec 001 data-model §1.5 patterns; `socket.gethostname()`, `getpass.getuser()`, `Path.home()` as reference strings | pytest, Hypothesis |
| FR-002-05, SC-002-01 | CI | every recipe's plan exits 0; leak scan as above | GitHub Actions `runner-plan` |
| FR-002-06 | unit | hand calculation of ⌈est × 2³⁰⌉ + margin vs device VRAM | pytest |
| FR-002-07 | CI | test suite result inside the container | GitHub Actions `runner-container` |
| FR-002-08, P-002-01…03 | unit + property | hand calculation: key recomputed with `hashlib.sha256` over `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` for inputs restricted to integers, ASCII strings, booleans and nested objects (where it equals RFC 8785) | pytest, Hypothesis |
| FR-002-09, P-002-05 | unit + property | the two vectors of FR-002-09 (computed from the formula with `hashlib` at specification) | pytest, Hypothesis |
| FR-002-10, FR-002-14 | unit | launcher spy counts; byte equality via `hashlib` | pytest |
| FR-002-11, FR-002-12, FR-002-13, P-002-06 | unit + property (hostile) | fault injection at each promotion step; `hashlib.sha256` of every `cas/` file vs its name | pytest, Hypothesis |
| FR-002-15, FR-002-18, FR-002-23, P-002-09 | unit + property | real `filelock` in a temporary lock directory; a second process holding the lock; interval-overlap check of recorded timestamps | pytest (multiprocessing) |
| FR-002-16, FR-002-17 | unit | hold files with text, empty, 1 MB of binary, a directory, a broken link; expected message and exit 4; import blockers as in the existing `tests/unit/test_run_bench_hold.py` | pytest |
| FR-002-19, FR-002-20, FR-002-22, P-002-10 | unit + property | hand calculation of each guard on fake-device and fake-disk values | pytest, Hypothesis |
| FR-002-21 | unit (hostile) | capability fixtures (missing file, invalid, `fail`, stale driver) | pytest |
| FR-002-24 | unit | expected argument list and environment written out literally | pytest |
| FR-002-25 | unit (hostile) | hostile `result.json` files (absent, invalid, 65,537 bytes, `succeeded` with exit 1) | pytest |
| FR-002-26 | unit | fake `nvtx` and `torch` modules on `sys.path` that record calls; stdlib-only import check (`python -I -S` with only the stagekit folder) on 3.12 and 3.14 | pytest |
| FR-002-60, FR-002-61 | unit (hostile for 61) | fake stages raising `NotRun` (expected manifest status, reason, event, skipped descendants with their reason, printed line, exit 0) and hand-written invalid `not_run` results (no reason, 301 characters, an output, an error class, exit 1) | pytest |
| FR-002-62, FR-002-63 | unit (hostile for 63) | launcher spy: expected `PITSTUDIO_HELD_LOCKS` per resource kind (`exclusive` → `gpu0.compute`, `nvenc` → `gpu0.nvenc`, `none` → empty); hand-written malformed values (unset, `gpu0.compute,gpu0.compute`, `GPU0.compute`, `gpu0.render`, 65 characters, 5 entries) → `LockNotHeldError` before a fake CUDA context is created | pytest |
| FR-002-27, FR-002-28, FR-002-41 | unit (Windows and Linux CI jobs) | psutil process enumeration (reference) of a fake stage that spawns a grandchild; elapsed time ≤ 10 s | pytest |
| FR-002-29 | unit | spy on the `SetThreadExecutionState` binding; expected call sequence `0x80000001`, then `0x80000000` | pytest |
| FR-002-30 | unit | fake clock: ⌊T × hz⌋ ± 1 samples; each line parses strictly | pytest |
| FR-002-31, P-002-08 | unit + property + metamorphic | hand calculation on fixed series; `statistics.quantiles(…, n=100, method="inclusive")` (type 7, reference implementation) for p5/p50/p95; analytical energy P × T | pytest, Hypothesis |
| FR-002-32 | unit (hostile) | fake device with unsupported fields and NaN/negative values → expected `null` and `unavailable` | pytest |
| FR-002-33, FR-002-34 | unit (hostile) | fake stages that exit with an OOM message, crash, or time out on the first attempt; expected attempts list | pytest |
| FR-002-35…38, P-002-07 | unit + property | fake stages that append to an execution ledger; expected ledger by hand; digests via `hashlib` | pytest, Hypothesis |
| FR-002-39, FR-002-40, FR-002-58 | unit | SQLite state after concurrent enqueues (K processes × M jobs → K × M distinct jobs); expected listing | pytest |
| FR-002-42, FR-002-43 | unit (hostile) | table of hostile arguments → expected exit 2 and unchanged store and repository | pytest |
| FR-002-44, FR-002-45 | contract (hostile) | Python `jsonschema` against `contracts/profile.schema.json`; hostile profiles | pytest |
| FR-002-46, FR-002-47 | contract | Python `jsonschema` against the manifest and events schemas (reference validator); lock fixtures with known versions | pytest |
| FR-002-48…50 | contract + unit (hostile) | expected file set and bytes by hand; spec 001 checker rules re-applied with Python `jsonschema`; downsampling hand calculation on a 4,001-sample series | pytest |
| FR-002-51, FR-002-52, P-002-11 | unit + property | reachability computed with networkx (reference) on the seeded store graph | pytest, Hypothesis |
| FR-002-53 | unit | spy on `run_bench.main`; exit codes 0–4 passed through; hold case with import blockers | pytest |
| FR-002-54 | unit | launcher spy: no spawned argument list contains `nsys`; printed command starts with `nsys profile --trace=cuda,nvtx` | pytest |
| FR-002-55…57 | unit (hostile) | fake device fixtures (valid, missing, invalid, NaN) | pytest |
| FR-002-59 | integration (gpu) | `nvidia-smi --query-gpu` output (reference implementation); name, driver and total memory exact; temperature ±3 °C because the two reads are up to 2 s apart on a GPU whose temperature moves ~1 °C/s under load; power limit ±1 W for the mW → W rounding of the two tools | pytest `-m gpu` (after the hold is lifted) |
| NFR-002-01 | CI | hand count on two fixture files fixes the counting rule; the count of `src/pitstudio/runner/` ≤ 1,500 | pytest |
| NFR-002-02, NFR-002-03 | unit | `time.perf_counter` on the fixtures | pytest |
| NFR-002-04 | unit | kill the holder process; acquire timing | pytest |
| NFR-002-05 | mutation | mutation score | mutmut (T-002-090) |

**Tolerances (P-002-08).** Means are float64 sums: for n ≤ 10⁴ non-negative terms the relative error of a recursive sum
is ≤ (n − 1)·u ≈ 1.1 × 10⁻¹² (u = 2⁻⁵³), and multiplying each term by c adds ≤ u per term, so reordering or scaling
changes a mean by far less than rtol 1e-9, which still detects any change of a single sample of a series with distinct
values above 1e-9 relative. Percentiles, maxima and fractions depend only on the sorted order or on comparisons, so they
are exact; for (b) the generator keeps every sample at least 10⁻⁹ relative away from 0.95 × limit, so scaling cannot
flip a comparison through rounding. Energy uses integer millijoules and is exact.

## Risks and complexity tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| ctypes bindings for job objects and keep-awake (≈ 50 LOC) | kill-on-close is the only reliable tree cleanup for Kit and Isaac Sim children on Windows; idle sleep would stop overnight runs | psutil-only tree kill misses children if the runner itself dies; pywin32 adds a large dependency for two calls |
| Fake GPU backend inside `src/` (counted in the LOC budget) | CI's `runner-plan` job and every runner test need it through the command line | a test-only fake cannot be selected by `studio plan` in a CI subprocess |
| Test launcher with the current interpreter (fake backend only) | CI syncs only the root environment; launching `uv run --project studio` would need every studio environment | installing all environments in CI is tens of GB and needs NVIDIA indices |
| `telemetry.jsonl` instead of Parquet | crash safety, streaming to the console, no Arrow dependency in the root extra | Parquet loses the whole file on a crash before its footer is written |

Other risks: the 1,500-line budget is tight (estimate 1,440): if T-002-002 measures more, the plan's rule applies
(re-assess doit as the DAG core) instead of raising the budget; Windows-only behaviour (job objects, keep-awake,
`LockFileEx`) is tested in a `runner-windows` CI job on a GitHub-hosted Windows runner, not only locally.
