# Data model 001 — Contracts
Spec: ./spec.md

This file is normative where `spec.md` refers to it ("data-model §n"). Field names, patterns, enums and caps below are
what the schemas must encode; the schemas themselves are written in task T-001-001. A "pattern" is a JSON Schema
`pattern` (anchored with `^…$`) in the portable regex subset of FR-001-03.

## 1. Common rules

### 1.1 Files and identifiers

| Schema file | `$id` | Documents it validates |
|---|---|---|
| `contracts/manifest.schema.json` | `https://fsantibanezleal.github.io/PitStudio/contracts/manifest.schema.json` | run manifests, published run manifests, `web/public/assets/manifest.json` |
| `contracts/recipe.schema.json` | `…/contracts/recipe.schema.json` | recipes; `$defs/job_request` (console) |
| `contracts/tools.schema.json` | `…/contracts/tools.schema.json` | `studio/tools.yaml` |
| `contracts/sources.schema.json` | `…/contracts/sources.schema.json` | `data/sources.yaml` |
| `contracts/capabilities.schema.json` | `…/contracts/capabilities.schema.json` (exists) | `studio/capabilities.json` |

Specs 002-runner and 003-console add `profile`, `job`, `events` and `console` schemas under the same rules. A schema may
`$ref` another file in `contracts/` by relative URI; remote `$ref` is not allowed (FR-001-46).

### 1.2 Closed objects

Every subschema with `"type": "object"` is one of:

1. a record: `"additionalProperties": false`;
2. a map: `"propertyNames": {"pattern": …}` and `"additionalProperties": <typed schema>`, plus `maxProperties`;
3. a composition: `allOf` / `oneOf` / `anyOf` branches with `"unevaluatedProperties": false` on the composing schema.

The only top-level property allowed beyond the record fields is `$schema` (string, ≤ 200 characters), so editors can
validate a file in place.

### 1.3 Shared patterns (`$defs` in each schema, identical text)

| Name | Pattern | maxLength | Notes |
|---|---|---|---|
| `slug` (recipe, source, profile ids) | `^[a-z0-9][a-z0-9-]{0,63}$` | 64 | no dot, slash, backslash or colon |
| `tool_id` | `^[a-z][a-z0-9-]{1,47}$` | 48 | |
| `artefact_id` | `^[a-z0-9][a-z0-9_-]{0,95}$` | 96 | never used as a path |
| `run_id` | `^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$` | 64 | UTC start stamp + recipe slug |
| `variant` | `^[a-z0-9][a-z0-9-]{0,31}$` | 32 | second instance of a stage in one recipe |
| `sha256` | `^[0-9a-f]{64}$` | 64 | lowercase only |
| `git_sha` | `^[0-9a-f]{40}$` | 40 | |
| `utc_timestamp` | `^[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])T([01][0-9]\|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?Z$` | 32 | calendar validity checked by `validate` |
| `date` | `^[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])$` | 10 | |
| `https_url` | `^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$` | 2048 | excludes user information; credential-named query keys checked by the checker |
| `release_tag` | `^assets-v[0-9]+\.[0-9]{2}\.[0-9]{3}$` | 32 | |
| `relpath` | `^SEG(/SEG){0,15}$` with `SEG` = `[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?` | 255 | no `.`/`..` segment, no leading `/`, no drive colon, no backslash, no space, no trailing dot |
| `relglob` | `^GSEG(/GSEG){0,15}$` with `GSEG` = `[A-Za-z0-9_*?]([A-Za-z0-9._*? -]{0,98}[A-Za-z0-9_*?])?` | 255 | archive member pattern of a source file (§5.1.1): `relpath` plus the wildcards `*` and `?` and spaces inside a segment (never at its start or end), because archive members carry them (e.g. `Research Data/Annotated data/…`); otherwise the same exclusions. Repository-relative paths (`relpath`) stay space-free |
| `module_path` | `^[a-z_][a-z0-9_]{0,63}(\.[a-z_][a-z0-9_]{0,63}){0,7}$` | 200 | `entry` of a stage |
| `semver` | `^[0-9]+\.[0-9]+\.[0-9]+$` | 32 | runner and console versions |
| `env_var` | `^[A-Z][A-Z0-9_]{2,63}$` | 64 | a variable *name*, never a value |
| `package` | `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` | 100 | lock package name |
| `version` | `^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$` | 64 | as read from a lock (e.g. `2.14.1+cu130`) |
| `python_version` | `^3\.[0-9]{1,2}(\.[0-9]{1,3})?$` | 10 | |
| `driver` | `^[0-9]+(\.[0-9]+)+$` | 32 | as in the capability schema |
| `param_key` | `^[a-z][a-z0-9_]{0,63}$` | 64 | |
| `probe` | `^[a-z][a-z0-9_]{0,31}$` | 32 | capability probe name |
| `binary_id` | `^[a-z][a-z0-9-]{1,31}$` | 32 | pinned external executable |
| `validator_id` | `^[a-z][a-z0-9-]{1,47}$` | 48 | output validator (spec 002) |

Rules `validate` adds after the schema (no portable regex can state them): a segment of a `relpath` or `relglob`
value (and of the `card` and `docs_page` paths) equal to a Windows device name (`CON`, `PRN`, `AUX`, `NUL`,
`COM1`–`COM9`, `LPT1`–`LPT9`, any case, with or without an extension) is rejected, and two paths of one document that
are equal after case folding are rejected (FR-001-56); every string whose schema has a `pattern` is rejected if it
contains a control character U+0000–U+001F, because Python `re`'s `$` matches before a final newline while the
ECMAScript and Rust engines do not (FR-001-57).

### 1.4 Size caps (bytes, checked by `load_json` / `load_yaml` before parsing)

| Document | Cap |
|---|---|
| recipe | 262,144 |
| job request (console body) | 65,536 |
| `studio/tools.yaml` | 262,144 |
| `data/sources.yaml` | 1,048,576 |
| `studio/capabilities.json` | 262,144 |
| run manifest (local or published) | 4,194,304 |
| `web/public/assets/manifest.json` | 8,388,608 |

Other limits: nesting depth ≤ 32 (JSON and YAML); recipe `params` depth ≤ 4, ≤ 64 keys per object, strings ≤ 1,024
characters, arrays ≤ 1,024 items, canonical size ≤ 65,536 bytes.

### 1.5 Absolute-path and identity patterns (privacy scan, FR-001-15)

Applied to every string value of every committed manifest:

| Rule | Pattern (Python `re`, searched anywhere in the string) |
|---|---|
| drive-letter path | `[A-Za-z]:[\\/]` |
| UNC path | `\\\\[A-Za-z0-9._$-]+\\` |
| POSIX absolute path | `(^\|[\s"'=(,:])/(home\|Users\|root\|tmp\|var\|mnt\|media\|opt\|srv\|private\|run)/` |
| file URL | `file:/` |
| machine identity | the host name, the user name and the home directory of the checking process, compared case-insensitively, each only when ≥ 3 characters |

Scrubbed forms are allowed: `<repo>/…` and `~/…`, as the capability bench writes them.

### 1.6 Constants

| Name | Value |
|---|---|
| `LOCAL_ONLY` | the string `measured locally, not published (licence)` (identical to `run_bench.LOCAL_ONLY`) |
| case ids | `A1`, `A2`, `A3`, `B1`, `B2`, `C1`, `C2`, `C3`, `D1`, `D2`, `E1`, `E2` |
| environments | `studio`, `isaac`, `rtx`, `isaaclab`, `kit`, `reason`, `pipeline`, `accel`, `external` (recipes); tools add `root`, `runner`, `web` |

### 1.7 Canonical JSON

Wherever a digest is computed over a JSON value (spec 002 cache keys and seeds; P-001-07 here), the bytes are the RFC 8785
JSON Canonicalization Scheme output in UTF-8: properties sorted by UTF-16 code units, ECMAScript number serialisation,
no whitespace, and an error on NaN or Infinity (RFC 8785 §3.2.2.3). Oracle vectors: the §3.2.4 example
(`{"numbers":[333333333.33333329,1E30,4.50,2e-3,0.000000000000000000000000001],…}` →
`{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],…}`) and the Appendix B number
samples (e.g. `0x4340000000000000` → `9007199254740992`, `0x44b52d02c7e14af6` → `1e+23`, `0x3eb0c6f7a0b5ed8d` →
`0.000001`, `0x0000000000000001` → `5e-324`).

## 2. Manifest (`manifest.schema.json`)

### 2.1 Run manifest (`kind: run`)

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `kind` | const `run` | yes | discriminator |
| `schema_version` | `^1\.[0-9]+$` | yes | contract version |
| `run_id` | `run_id` | yes | |
| `recipe` | `{id: slug, path: relpath under studio/recipes/, sha256}` | yes | recipe file and digest of its bytes |
| `git_sha`, `git_dirty` | `git_sha`; boolean | yes | code version; uncommitted changes present |
| `runner_version` | `semver` | yes | |
| `created` | `utc_timestamp` | yes | run start |
| `profile` | `slug` | yes | machine profile id (spec 002) |
| `seed` | integer 0 … 9,223,372,036,854,775,807 | yes | recipe master seed |
| `published` | boolean | yes | `true` only in files written by `studio publish` |
| `launcher` | enum `uv`, `test` | yes | `test` = the fake-backend test launcher of spec 002 |
| `gpu` | §2.2 or `null` | yes | `null` for CPU-only runs |
| `stages` | array 1–64 of §2.3 | yes | |
| `artefacts` | array 0–2,000 of §2.5 | yes | outputs offered for publication |
| `notes` | array ≤ 20 of strings ≤ 300 | no | scrubbed |

### 2.2 GPU record

| Field | Type / constraint | Req. |
|---|---|---|
| `backend` | enum `nvml`, `fake` | yes |
| `index` | integer 0–15 | yes |
| `name` | string 1–128 | yes |
| `driver` | `driver` | yes |
| `vram_total_bytes` | integer 0 … 2⁵³−1 | yes |
| `power_limit_enforced_w` | number ≥ 0 or `null` | yes |

### 2.3 Stage record

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `key` | `{id: stage id (§3.3), variant?: variant}` | yes | |
| `tool` | `tool_id` | yes | producer tool (registry id) |
| `env` | `{name: environment, python: python_version or null, lock_sha256: sha256, versions: map package → version (≤ 64 entries)}` | yes | versions read from the lock |
| `cache_key` | `sha256` | yes | spec 002 definition |
| `cache` | enum `hit`, `miss` | yes | |
| `status` | enum `succeeded`, `failed`, `skipped`, `cancelled`, `blocked`, `held`, `interrupted`, `env-disabled`, `not_run` | yes | `not_run`: the stage reported that it could not run (spec 002, FR-002-60) |
| `reason` | string 1–300 (scrubbed) | conditional | required iff `status: not_run`; allowed for `skipped` (e.g. `upstream not run: <stage key>`) |
| `exit_code` | integer −2³¹ … 2³¹−1 or `null` | yes | |
| `error_class` | enum `oom`, `timeout`, `warmup-timeout`, `invalid-output`, `invalid-result`, `nonzero-exit`, `guard`, `lock-timeout`, `lock-not-held`, `cancelled`, `interrupted`, `hold`, `unknown`, or `null` | yes | `null` iff `status: succeeded`, `skipped` or `not_run` |
| `attempts` | array 1–5 of `{n: 1–5, error_class (as above), fallback?: object of param overrides, duration_s?: number ≥ 0}` | yes | |
| `params` | object (effective parameters, §3.2 limits) | yes | |
| `seed` | integer 0 … 2⁶³−1 | yes | derived stage seed |
| `shards` | `{total: 1–10,000, done: 0–total}` | no | shardable stages; `done ≤ total` is a `validate` rule (FR-001-55) |
| `determinism` | `{class: bitwise\|statistical\|none, rerun_check: pending\|pass\|fail\|not-applicable, max_deviation?: number ≥ 0}` | yes | |
| `performance` | enum `public`, `local-only` | yes | copied from the tool registry |
| `wall_s` | number ≥ 0 | no | forbidden when published and local-only |
| `telemetry` | §2.4, `null`, or const `LOCAL_ONLY` | yes | `null` for CPU-only stages |
| `throughput` | `{value: number ≥ 0, unit: string 1–32}` | no | forbidden when published and local-only |
| `thermal_flag` | boolean | yes | `true` when `hw_thermal` or `hw_slowdown` fraction > 0.05 (spec 002) |
| `log_tail` | string ≤ 4,000 | no | failed stages only, scrubbed |
| `inputs` | array ≤ 32 of `{id: slug or artefact_id, sha256, kind: source\|artefact\|knowledge}` | yes | |
| `outputs` | array ≤ 64 of `{name: relpath, sha256, bytes: integer ≥ 0}` | yes | |

### 2.4 Telemetry summary (per stage)

All numbers finite; any field may be `null`, and then `unavailable` names it with a reason (≤ 120 characters).

| Field | Type | Definition |
|---|---|---|
| `sample_hz` | number 1–4 | sampling rate |
| `n_samples` | integer ≥ 0 | |
| `gpu_busy_pct` | `{mean, p50, p95}` in 0–100 | NVML utilisation (time-busy fraction); percentiles by linear interpolation (Hyndman–Fan type 7) |
| `mem_used_peak_bytes` | integer ≥ 0 | device-level peak |
| `power_w` | `{mean, p95, max}` ≥ 0 | board power |
| `power_at_limit_frac` | 0–1 | fraction of samples with power ≥ 0.95 × enforced limit |
| `energy_j` | number ≥ 0 | (last − first total-energy counter reading, mJ) / 1,000 |
| `sm_clock_mhz` | `{mean, p5}` ≥ 0 | |
| `temp_c_max` | number | |
| `clocks_event_frac` | `{sw_power_cap, sw_thermal, hw_thermal, hw_slowdown, power_brake, idle}` each 0–1 | fraction of samples with the bit set (bits in spec 002 data) |
| `nvenc_util_pct` | `{mean, max}` 0–100 | encode stages |
| `pcie_replays_delta` | integer | last − first counter |
| `unavailable` | map field name → reason | |

### 2.5 Artefact record (shared by both kinds)

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `id` | `artefact_id` | yes | unique within the document (FR-001-54) |
| `run_id`, `git_sha` | `run_id`; `git_sha` | yes | provenance |
| `path` | `relpath` | yes | git host: path under `web/public/`; release host: the asset file name |
| `bytes`, `sha256` | integer 0 … 2⁵³−1; `sha256` | yes | of the served file |
| `media_type` | `^[a-z]+/[a-z0-9.+-]{1,64}$` | no | |
| `kind` | enum `video`, `image`, `figure`, `point-cloud`, `mesh`, `tiles`, `splat`, `onnx`, `table`, `trace`, `shard`, `field`, `text`, `model-card`, `telemetry`, `usd` | yes | |
| `producer` | `{tool: tool_id, stage: {id, variant?}}` | yes | the web tool pages filter on `tool` |
| `inputs` | array ≤ 32 of `{id, sha256, kind: source\|artefact\|knowledge}` | yes | for the licence lattice |
| `cases` | array ≤ 12 of case ids, unique | no | |
| `lane` | enum `live`, `replay`, `static` | yes | measured (§2.6) |
| `lane_measurements` | §2.6 | conditional | |
| `licence_class` | enum of §5.4 | yes | |
| `spdx` | SPDX id from §5.2 | yes | |
| `attribution` | string 1–1,000 | conditional | required unless class `public-domain`, `open-no-attribution` or `own` |
| `asset_host` | enum `git`, `release` | yes | |
| `release_tag` | `release_tag` | conditional | required iff `release`; `git` requires `bytes` < 10,485,760 |
| `budget_class` | enum `videos`, `tiles-glb`, `shards-clouds`, `splats`, `onnx`, `runtimes`, `own-code`, `studio-showcase` | yes | the web budget class (docs `web/budgets.md`) |
| `encoder` | §2.7 | conditional | iff `kind: video` |

### 2.6 Lane measurements and the gate

| Field | Type | Meaning |
|---|---|---|
| `web_drivable` | boolean | needs no GPU runtime, proprietary engine or server |
| `max_asset_bytes` | integer ≥ 0 | largest file the browser must load for it |
| `interaction_ms` | number ≥ 0 or `null` | one interaction step on tier T2 |
| `run_ms_t2` | number ≥ 0 or `null` | one complete run on tier T2 |
| `trace_bytes` | integer ≥ 0 or `null` | largest streamed trace or shard (`null` = none) |
| `measured` | `{tier: const T2, date: date, browser: string 1–64}` | conditions |

Gate (thresholds: the `lane_gate.*` keys of `thresholds.yaml`; see plan.md):

```
live  ⇔  web_drivable
       ∧ max_asset_bytes ≤ 25,000,000
       ∧ ( (interaction_ms ≠ null ∧ interaction_ms ≤ 16) ∨ (run_ms_t2 ≠ null ∧ run_ms_t2 ≤ 1,000) )
       ∧ ( trace_bytes = null ∨ trace_bytes ≤ 10,000,000 )
otherwise replay
```

Static kinds (lane `static` allowed, `lane_measurements` forbidden): `image`, `figure`, `table`, `text`, `model-card`,
`usd`. Every other kind needs `lane_measurements` and a lane of `live` or `replay` equal to the gate.

### 2.7 Encoder record (`kind: video`)

| Field | Type / constraint |
|---|---|
| `codec` | enum `av1`, `h264` |
| `profile` | string 1–32 |
| `pix_fmt` | `^[a-z0-9]{2,16}$` |
| `width`, `height` | integer 16–8,192 |
| `fps` | number > 0 and ≤ 240 |
| `frames` | integer ≥ 1 |
| `duration_s` | number > 0 |
| `bitrate_kbps` | number > 0 |
| `vmaf` | `{mean: 0–100, p5: 0–100, model: string 1–64}` |
| `source_frames_sha256` | `sha256` |
| `encoder` | `{ffmpeg_version: ^n?[0-9]+(\.[0-9]+){0,3}$, build_sha256: sha256, nvenc_api: ^[0-9]+\.[0-9]+$ or null, args: array ≤ 64 of strings ≤ 200}` |
| `encode_fps` | number ≥ 0 or `null` |

Checker rule: `abs(duration_s − frames / fps) ≤ 1 / fps` (FR-001-17).

### 2.8 Web index (`kind: web-index`, `web/public/assets/manifest.json`)

| Field | Type / constraint | Req. |
|---|---|---|
| `kind` | const `web-index` | yes |
| `schema_version` | `^1\.[0-9]+$` | yes |
| `generated` | `date` | yes |
| `git_sha` | `git_sha` | yes |
| `runs` | array ≤ 500 of `{run_id, manifest: relpath under web/public/assets/runs/, sha256}` | yes |
| `artefacts` | array ≤ 2,000 of §2.5 | yes |

### 2.9 Conditional rules encoded in the schema (`if` / `then`)

1. `published: true` ⇒ `git_dirty: false`, `launcher: uv` and (`gpu: null` or `gpu.backend: nvml`).
2. `published: true` ∧ stage `performance: local-only` ⇒ stage `telemetry` = `LOCAL_ONLY`, and `wall_s`, `throughput`,
   `attempts[].duration_s` absent.
3. `asset_host: release` ⇒ `release_tag` required; `asset_host: git` ⇒ `release_tag` absent and `bytes` ≤ 10,485,759.
4. `kind: video` ⇔ `encoder` present.
5. `lane` ∈ {live, replay} ⇒ `lane_measurements` required; `lane: static` ⇒ `lane_measurements` absent and `kind` in
   the static kinds.
6. `licence_class` ∉ {public-domain, open-no-attribution, own} ⇒ `attribution` required.
7. `status` ∈ {succeeded, skipped, not_run} ⇔ `error_class: null`; `status: not_run` ⇔ `reason` present (allowed also for
   `skipped`); `status: not_run` ⇒ `outputs` empty.

Rules that need other files or other parts of the document (lane value vs gate, licence lattice, producer status,
registry and source references, digests of served files, privacy) are checker rules (§8.1).

## 3. Recipe (`recipe.schema.json`)

### 3.1 Recipe document

| Field | Type / constraint | Req. |
|---|---|---|
| `id` | `slug` | yes |
| `case` | case id or const `bench` | yes |
| `seed` | integer 0 … 2⁶³−1 (booleans and floats rejected) | yes |
| `description` | string ≤ 500 | no |
| `stages` | array 1–64 of §3.2 | yes |

### 3.2 Stage

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `id` | stage id, enum of §3.3 | yes | |
| `variant` | `variant` | no | (`id`, `variant`) is the stage key, unique in the recipe (spec 002) |
| `env` | environment bound to `id` (§3.3) | yes | |
| `tool` | `tool_id` | yes | producer tool; its registry entry gives `performance` |
| `entry` | `module_path` | yes | launched as `python -m <entry>` (spec 002) |
| `inputs` | array ≤ 32; each `{id: slug, sha256}` (a source) or `{stage: stage id, variant?, output?: relpath}` (an upstream stage) | yes (may be empty) | never a path |
| `params` | object, keys `param_key`, values JSON (finite numbers), limits of §1.4 | no | enters the cache key |
| `resources` | `{gpu: exclusive\|nvenc\|none, vram_gib_est?: number > 0 and ≤ 256, disk_gib_est?: number 0–10,000, cpu?: integer 1–256}` | yes | `exclusive` ⇒ `vram_gib_est` required; `none` ⇒ `vram_gib_est` absent |
| `requires` | array ≤ 16 unique of `probe` | no | capabilities the guard checks |
| `binaries` | array ≤ 8 of `{id: binary_id, sha256}` | no | pinned external executables; enter the cache key |
| `determinism` | `bitwise` (shorthand) or `{class: bitwise}` or `{class: statistical, observables: map name → {rtol: 0–1, atol: ≥ 0} (1–32 entries)}` or `{class: none, reason: string 10–300}` | yes | |
| `retry` | `{oom_fallback: array 1–4 of param-override objects}` | no | override keys must exist in `params` (checked by spec 002's planner) |
| `timeout_s` | integer 1–604,800 | yes | |
| `outputs` | array 1–64 of `{path: relpath, schema: validator_id, publish?: boolean}` | yes | |
| `shardable` | `{shard_size: integer 1–10,000,000, total: integer 1–1,000,000,000}`; ⌈total / shard_size⌉ ≤ 10,000 (validator rule) | no | |

### 3.3 Frozen stage ids and their environments

| Stage id | Allowed `env` | | Stage id | Allowed `env` |
|---|---|---|---|---|
| `s00_download` | pipeline | | `st45b_kit_validate` | kit |
| `s05_synthesize` | pipeline | | `st50_physics` | studio |
| `s10_preprocess` | pipeline | | `st52_rtx_render` | isaac |
| `s20_feature_extraction` | pipeline | | `st53_sensors` | rtx |
| `s30_train` | pipeline | | `st54_vehicles` | isaac |
| `s40_infer` | pipeline | | `st55_sdg` | isaac |
| `s50_evaluate` | pipeline | | `st56_encode` | studio |
| `s60_export` | pipeline | | `st57_rain_lidar` | isaac |
| `s62_accel` | accel | | `st58_kit_capture` | kit |
| `s64_bench` | accel, pipeline | | `st58b_capture_splat` | external |
| `st10_terrain` | studio | | `st59_reason_bench` | reason |
| `st20_pit_design` | studio | | `st59a_vqa` | reason |
| `st30_assets` | studio | | `st59b_plausibility` | reason |
| `st40_compose` | studio | | `st59c_captions` | reason |
| `st45_validate` | studio | | `st60_il_train` | isaaclab |
| | | | `st61_il_mpm_eval` | isaaclab |

Source: docs `pipelines/pipeline-stages.md`, `pipelines/studio-stages.md`, `reference/cli.md`. Adding a stage id is a
schema change.

### 3.4 Hostile recipe values (each has ≥ 1 invalid fixture)

| Class | Examples |
|---|---|
| unknown enum | stage `st99_magic`; env `docker`; case `Z9`; determinism `exact`; gpu `shared` |
| wrong binding | `st52_rtx_render` with `env: studio` |
| path traversal / injection | input id `../../etc/passwd`; output path `/abs/x`, `C:/x`, `..\\x`, `a/../b`, `con.txt`, `x.`; entry `os; rm -rf /`, `pkg.mod -c`, `Pkg.Mod`, `pkg/mod` |
| malformed digest | 63 or 65 hex chars, uppercase hex, `sha256:` prefix |
| wrong type / range | seed `-1`, `2**63`, `1.5`, `true`, `"42"`; `timeout_s` 0 or 604,801; `vram_gib_est` 0 or 300 |
| non-finite | `.nan`, `.inf` anywhere in params (loader) |
| inconsistent resources | `gpu: none` + `vram_gib_est: 4`; `gpu: exclusive` without `vram_gib_est` |
| incomplete determinism | `{class: statistical}` without observables; `{class: none}` without reason |
| oversized | 65 stages; params depth 5; a 1,025-character string; 1,025-item array; file > 262,144 B; 10,001 shards |
| unknown field | `profile: laptop-rtx5000ada` in the recipe; `stages[0].path: …` |
| YAML-specific | alias `*a`, anchor `&a`, `!!python/object`, two documents, duplicate key, `seed: yes` (string, then type error) |

### 3.5 Job request (`$defs/job_request`, body of the console's `POST /jobs`)

| Field | Type / constraint | Req. |
|---|---|---|
| `recipe` | `slug` (id of a committed recipe) | yes |
| `stages` | array 1–64 unique of `{id: stage id, variant?: variant}` | no (default: all) |
| `force` | boolean | no (default `false`) |
| `rerun_check` | boolean | no (default `false`) |
| `profile` | `slug` | yes |

No other field is allowed: a job request can never carry an inline recipe, an `entry`, an `env` or `params`.

## 4. Tool registry (`tools.schema.json`, `studio/tools.yaml`)

### 4.1 Document and entry

Document: `{ "$schema"?: string, "tools": array 1–64 of entries }`, ids unique (FR-001-54).

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `id` | `tool_id` | yes | used as `producer.tool` |
| `name` | string 1–64 | yes | display name |
| `category` | enum `studio-tool`, `component` | yes | the web tool map draws `studio-tool` only |
| `envs` | array 1–4 unique of `root`, `runner`, `studio`, `isaac`, `rtx`, `isaaclab`, `kit`, `reason`, `pipeline`, `accel`, `web`, `external` | yes | |
| `version` | one of §4.2 (never a literal string) | yes | |
| `spdx` | array 1–4 unique of SPDX ids from §5.2 | yes | |
| `osi` | boolean | yes | OSI-approved licence |
| `licence_class` | enum of §5.4 | yes | |
| `ring` | enum `Adopt`, `Trial`, `Assess`, `Hold` | yes | |
| `lane` | enum `live`, `replay`, `local-only` | yes | |
| `performance` | enum `public`, `local-only` | yes | `local-only` required when `spdx` meets §5.3 |
| `role` | string 1–300 | yes | mining role |
| `cases` | array ≤ 12 unique of case ids | yes | |
| `produces` | array ≤ 16 unique of artefact kinds (§2.5) | yes | |
| `status` | enum `not-yet-run`, `done`, `evaluated-not-adopted` | yes | |
| `reason` | string 20–600 | conditional | iff `evaluated-not-adopted` |
| `docs_page` | `^docs/frameworks/(not-adopted-)?[a-z0-9-]{1,64}\.md$` | conditional | required for `studio-tool`; equals `docs/frameworks/<id>.md`, or `docs/frameworks/not-adopted-<id>.md` for `evaluated-not-adopted` |
| `alternatives_rejected` | array ≤ 8 of `{name: 1–64, reason: 1–300}` | no | |
| `notice` | string ≤ 300 | no | trademark or licence notice |

### 4.2 Version references

| Form | Fields | Resolved by the checker against |
|---|---|---|
| lock | `{from_lock: one of uv.lock, studio/uv.lock, studio/isaac/uv.lock, studio/rtx/uv.lock, studio/isaaclab/uv.lock, pipeline/uv.lock, pipeline/accel/uv.lock, web/pnpm-lock.yaml; package: package}` | the `[[package]]` entry (uv) or the package key (pnpm) |
| pinned binary | `{from_binary: binary_id, release: version, sha256: sha256}` | the archive digest recorded at install (external tools only) |
| git tag | `{from_git_tag: version, repository: https_url}` | the tag string as pinned in the environment's project file |
| own | `{own: true}` | the repository `VERSION` |

### 4.3 The 20 `studio-tool` entries

| `id` | Status at first commit | | `id` | Status at first commit |
|---|---|---|---|---|
| `openusd` | not-yet-run | | `cosmos-reason-2` | not-yet-run |
| `warp` | not-yet-run | | `pytorch` | not-yet-run |
| `newton` | not-yet-run | | `onnx-runtime` | not-yet-run |
| `mujoco-warp` | not-yet-run | | `tensorrt` | not-yet-run |
| `physx-ovphysx` | not-yet-run | | `nvenc-ffmpeg` | not-yet-run |
| `ovrtx` | not-yet-run | | `nsight-nvml` | not-yet-run |
| `isaac-sim-replicator` | not-yet-run | | `threejs-r3f-3d-tiles` | not-yet-run |
| `isaac-lab` | not-yet-run | | `rapier-webgpu-pyodide` | not-yet-run |
| `kit-usd-composer-explorer` | not-yet-run | | `cuopt` | evaluated-not-adopted |
| | | | `physicsnemo` | evaluated-not-adopted |
| | | | `cosmos-predict-transfer` | evaluated-not-adopted |

Ids equal the stems of the existing pages in `docs/frameworks/`. Component entries at first commit: `pitstudio`
(own code), `minephys`, `minehaulsim`, `oreblocks`, `colmap`, `brush`.

## 5. Source registry (`sources.schema.json`, `data/sources.yaml`)

### 5.1 Document and entry

Document: `{ "$schema"?: string, "sources": array 0–256 of entries }`, ids unique.

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `id` | `slug` | yes | used by recipes and manifests |
| `kind` | enum `real`, `synthetic` | yes | |
| `title` | string 1–300 | yes | publisher's title |
| `landing_url` | `https_url` | yes | original publisher, preferably a DOI URL |
| `access` | enum `direct`, `api`, `account`, `manual` | yes | how `s00_download` (spec 008) reaches the files; `account` ⇔ `account.needed: true`; `manual` = the maintainer places the files under `external/<id>/` |
| `files` | array 0–512 of file records (§5.1.1) | yes | |
| `spdx` | SPDX id from §5.2 | yes | as stated by the original publisher |
| `licence_url` | `https_url` | yes | where that statement was read |
| `licence_class` | enum of §5.4, allowed for (`spdx`, `kind`) by §5.2 | yes | the most restrictive over per-file `spdx` overrides |
| `redistribution` | enum `redistributable`, `derived-only`, `no-redistribution` | yes | |
| `attribution` | string 1–1,000 | conditional | required for `attribution` and `share-alike` |
| `citation` | string 1–1,000 | yes | |
| `card` | `^data/cards/[a-z0-9-]{1,64}\.md$` | yes | dataset card |
| `account` | `{needed: boolean, env_var?: env_var, note?: string ≤ 300}` | yes | `needed` ⇒ `env_var` and `fallback` required; `env_var` is the *name* of the environment variable that holds the key, never a credential value |
| `fallback` | `{sources: array 0–8 of slug (unique, in order of preference), text: string 1–300}` | conditional | required when `account.needed`; every slug is another registry id; no `fallback` or `sources: []` = no substitute data, so dependent stages are not run (spec 008) |
| `optional` | boolean | no (default `false`) | |

### 5.1.1 File record

| Field | Type / constraint | Req. | Meaning |
|---|---|---|---|
| `url` | `https_url` | yes | |
| `sha256` | `sha256` or null | yes | `null` = not yet pinned |
| `bytes` | integer 1 … 68,719,476,736 (64 GiB) or null | yes | `null` = not yet known |
| `name` | `relpath` | no | local name, when the URL's last segment is not usable |
| `spdx` | SPDX id from §5.2 | no | per-file override of the entry's `spdx` |
| `kind` | enum `raster`, `point-cloud`, `vector`, `image-set`, `table`, `document`, `archive` | yes | selects the file-level validator of spec 008 |
| `publisher_checksum` | `^(md5:[0-9a-f]{32}\|sha256:[0-9a-f]{64})$`, maxLength 71 | no | the checksum the original publisher states (e.g. Zenodo MD5); checked before a SHA-256 pin is proposed; never replaces `sha256` |
| `uncompressed_bytes` | integer 1 … 68,719,476,736 | no | only when `kind: archive`; the extraction cap |
| `extract` | array 1–64 of `relglob` | no | only when `kind: archive`; the members to extract |

### 5.2 SPDX allowlist and allowed licence classes

| SPDX id | `real` sources | `synthetic` sources / our outputs | tools |
|---|---|---|---|
| `LicenseRef-USGov-PD` | public-domain | — | — |
| `CC0-1.0`, `DL-DE-ZERO-2.0` | open-no-attribution | — | — |
| `CC-BY-4.0` | attribution | own | — |
| `LicenseRef-Copernicus-CLMS` | attribution | — | — |
| `CC-BY-SA-3.0`, `CC-BY-SA-4.0` | share-alike | — | — |
| `Apache-2.0` | — | own | attribution (third-party tool) or own (`pitstudio` component) |
| `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `MPL-2.0`, `LGPL-2.1-or-later`, `LicenseRef-TOST-1.0` | — | — | attribution (notice retention) |
| `LicenseRef-NVIDIA-Open-Model` | — | display-only (outputs) | reference-only (weights) |
| `LicenseRef-NVIDIA-SLA`, `LicenseRef-NvidiaProprietary`, `LicenseRef-NVIDIA-Omniverse`, `LicenseRef-TensorRT-SLA`, `LicenseRef-TensorRT-RTX-SLA` | — | — | reference-only |

A tool entry whose `spdx` list mixes rows takes the highest-ranked allowed class (§5.4). Manifest artefacts use the
same allowlist; their class comes from the lattice (§5.4), not from this table.

### 5.3 Performance-restricted licences (FR-001-28)

`LicenseRef-NVIDIA-SLA` (Kit, Isaac Sim, Replicator), `LicenseRef-NvidiaProprietary` (ovrtx, ovstage package label),
`LicenseRef-NVIDIA-Omniverse` (ovphysx package label) and `LicenseRef-TensorRT-RTX-SLA`. Regular TensorRT
(`LicenseRef-TensorRT-SLA`) is not restricted (docs DEC-0005). A tool entry listing any restricted id must declare
`performance: local-only`.

### 5.4 Licence-class lattice (FR-001-18)

| Rank | Class | Derivatives we may publish |
|---|---|---|
| 0 | `public-domain` | yes |
| 1 | `open-no-attribution` | yes |
| 2 | `own` | yes |
| 3 | `attribution` | yes, with the attribution text |
| 4 | `share-alike` | yes, as a separate share-alike entry |
| 5 | `display-only` | text only, with its notice |
| 6 | `reference-only` | never |

`licence_class_of(inputs) = max_rank({own} ∪ {class(i) for i in inputs})`; the class of a source input comes from
`data/sources.yaml`, the class of an artefact input from its own record. An artefact whose computed class is
`reference-only` is never publishable (FR-001-19).

## 6. Capability report bounds (`capabilities.schema.json`, modified)

| Location | Added bound |
|---|---|
| `gpu` | `maxLength: 128` |
| `driver` | `maxLength: 32` |
| `probes` | `maxProperties: 64`; `propertyNames.pattern` `^[a-z][a-z0-9_]{0,31}$` |
| `probe.versions` | `maxProperties: 32`; names `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`; values `maxLength: 64` |
| `probe.metrics` (object branch) | `maxProperties: 64`; names `^[A-Za-z][A-Za-z0-9_]{0,63}$`; string values `maxLength: 200` |
| `probe.telemetry` | `maxProperties: 32`; names `^[a-z][a-z0-9_]{0,63}$` |
| `probe.notes` | `maxItems: 20`; items `maxLength: 300` |

Every value in the existing contract-test samples (e.g. metric `saxpy_16M_x20_s`, telemetry `pcie_replays_delta`)
stays valid.

## 7. Generators

### 7.1 Python (`tools/gen_types.py`, datamodel-code-generator 0.83.0)

One module per schema, `src/pitstudio/contracts/_generated/<stem>.py` (stem = file name before `.schema.json`, `-`
→ `_`), plus an `__init__.py` listing them. Options:

```
--input contracts/<file> --input-file-type jsonschema --schema-version 2020-12
--output-model-type pydantic_v2.BaseModel --target-python-version 3.12
--use-annotated --use-standard-collections --use-union-operator --field-constraints
--extra-fields forbid --enum-field-as-literal all --use-schema-description --disable-timestamp
--custom-file-header "# Generated from contracts/<file> by tools/gen_types.py. Do not edit."
```

followed by `ruff format` on the output. The input path is passed relative to the repository root so that no absolute
path reaches a header. The exact formatter flag (`--formatters ruff-format` or a separate `ruff format` call) is fixed
in T-001-002 by the proof of NFR-001-04.

### 7.2 TypeScript (`web/scripts/gen-types.mjs`, json-schema-to-typescript 16.0.0)

One module per schema, `web/src/contracts/generated/<stem>.ts`, plus `index.ts` re-exporting types with
`export type { … }`. Options: `bannerComment: "/* Generated from contracts/<file> by web/scripts/gen-types.mjs. Do not
edit. */"`, `additionalProperties: false`, `strictIndexSignatures: true`, `unreachableDefinitions: true`,
`declareExternallyReferenced: true`, `format: false`, `cwd: <repo>/contracts` (local `$ref` only). The folder is
excluded from Biome formatting and linting and included in `tsc`.

### 7.3 Trust boundaries that validate with the schema (FR-001-45)

1. The runner loading a recipe or a profile (spec 002).
2. The runner reading a stage's `result.json` (spec 002).
3. The console accepting `POST /jobs` (spec 003).
4. `tools/check_contracts.py` on every committed document.
5. `pages.yml` reading the web index and the release assets before upload.
6. `studio publish` writing a published manifest (spec 002).

The web app reads only files that boundary 5 validated; the one untrusted runtime input of the public site (the opt-in
console health response) is handled in spec 003.

## 8. Checker and conformance corpus

### 8.1 Documents the checker validates

| Glob | Schema | Cross-file rules |
|---|---|---|
| `studio/tools.yaml` | tools | FR-001-26, FR-001-53 |
| `data/sources.yaml` | sources | FR-001-32 (duplicates, secrets), FR-001-52 (fallback ids, mixed share-alike files) |
| `studio/recipes/cases/*.yaml`, `studio/recipes/_bench/*.yaml` | recipe | tool ids exist in the registry |
| `studio/recipes/_profiles/*.yaml` | profile (spec 002) | — |
| `studio/capabilities.json` | capabilities | — |
| `web/public/assets/manifest.json` | manifest (`web-index`) | FR-001-13, -15, -17, -18, -19, -20, -29, -33 |
| `web/public/assets/runs/*/manifest.json` | manifest (`run`, published) | FR-001-15, -16, -29, -33 |
| `web/public/assets/runs/*/telemetry.json` | events (`$defs/published_telemetry`, spec 002) | every stage listed is `performance: public` in the run's published manifest (FR-001-14) |
| `models/cards/*/manifest.json` | manifest (`run`, published) | same as published run manifests |

Any other file inside `contracts/`, `studio/recipes/` or `web/public/assets/runs/` that matches none of these globs is
a finding (FR-001-51).

### 8.2 Hostile-class matrix (NFR-001-03)

| Hostile class | run | web-index | recipe | job request | tools | sources | capabilities |
|---|---|---|---|---|---|---|---|
| non-finite number | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| wrong type | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| wrong unit / shape (array vs object, string number) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| empty (empty file, `{}`, empty required array) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| oversized (bytes, items, string length, depth) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| malformed syntax (truncated JSON/YAML, BOM, invalid UTF-8) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| unknown field | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| unknown enum | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| path traversal / absolute path | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ (notes) |
| injection-like string (shell metacharacters in `entry`, credential in URL) | — | — | ✓ | ✓ | — | ✓ | — |
| duplicate key / duplicate id | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| out-of-range number | ✓ | ✓ | ✓ | — | — | ✓ | — |
| inconsistent counts (`shards.done` > `shards.total`, FR-001-55) | ✓ | — | — | — | — | — | — |
| Windows device-name segment or case-folded duplicate path (FR-001-56) | ✓ | ✓ | ✓ | — | ✓ | ✓ | — |
| control character in a patterned string, trailing newline included (FR-001-57) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| YAML-specific (alias, tag, multi-document, implicit boolean) | — | — | ✓ | — | ✓ | ✓ | — |
| licence or honesty violation (local-only metric, wrong class, evaluated-not-adopted without reason) | ✓ | ✓ | — | — | ✓ | ✓ | ✓ |

### 8.3 Property-test strategies

Hypothesis strategies are written per document kind in `tests/contract/strategies.py` (shared by the property tests):
each draws only values inside the patterns and bounds above, so every drawn document must validate; mutation helpers
then break exactly one rule to produce a document that must fail with that rule. `property_tests.ci_examples_per_test`
(200) applies.

### 8.4 Corpus index

`tests/contract/fixtures/index.json` lists every fixture: `{file, schema, kind, valid, rule, pointer, keyword, tags}`,
where `rule` is the requirement id it exercises, `pointer`/`keyword` the expected first error, and `tags` any of
`loader`, `conditional`, `cross-file`. P-001-06 skips fixtures tagged `conditional` or `cross-file`.
