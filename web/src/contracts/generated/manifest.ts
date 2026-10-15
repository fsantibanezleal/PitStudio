/* Generated from contracts/manifest.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Run manifests, published run manifests and the web artefact index (DC-001-01, spec 001-contracts).
 */
export type PitStudioManifest = (Run | WebIndex)
/**
 * run manifest (data-model §2.1)
 */
export type Run = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
kind: "run"
schema_version: SchemaVersion
run_id: RunId
recipe: {
id: Slug
/**
 * relative to studio/recipes/
 */
path: Relpath
sha256: Sha256
}
git_sha: GitSha
git_dirty: boolean
runner_version: Semver
created: UtcTimestamp
profile: Slug
seed: number
published: boolean
launcher: ("uv" | "test")
gpu: (Gpu | null)
/**
 * @minItems 1
 * @maxItems 64
 */
stages: [Stage, ...(Stage)[]]
/**
 * @maxItems 2000
 */
artefacts: Artefact[]
/**
 * @maxItems 20
 */
notes?: []|[string]|[string, string]|[string, string, string]|[string, string, string, string]|[string, string, string, string, string]|[string, string, string, string, string, string]|[string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]
}
export type SchemaVersion = string
export type RunId = string
export type Slug = string
export type Relpath = string
export type Sha256 = string
export type GitSha = string
export type Semver = string
export type UtcTimestamp = string
export type Driver = string
/**
 * stage record (data-model §2.3)
 */
export type Stage = ({
key: StageKey
tool: ToolId
env: EnvRecord
cache_key: Sha256
cache: ("hit" | "miss")
status: ("succeeded" | "failed" | "skipped" | "cancelled" | "blocked" | "held" | "interrupted" | "env-disabled" | "not_run")
reason?: string
exit_code: (number | null)
error_class: ErrorClass
/**
 * @minItems 1
 * @maxItems 5
 */
attempts: [Attempt]|[Attempt, Attempt]|[Attempt, Attempt, Attempt]|[Attempt, Attempt, Attempt, Attempt]|[Attempt, Attempt, Attempt, Attempt, Attempt]
params: Params
seed: number
shards?: {
total: number
done: number
}
determinism: StageDeterminism
performance: ("public" | "local-only")
wall_s?: number
telemetry: (TelemetrySummary | null | LocalOnly)
throughput?: {
value: number
unit: string
}
thermal_flag: boolean
log_tail?: string
/**
 * @maxItems 32
 */
inputs: InputRef[]
/**
 * @maxItems 64
 */
outputs: OutputFile[]
} & {
key: StageKey
tool: ToolId
env: EnvRecord
cache_key: Sha256
cache: ("hit" | "miss")
status: ("succeeded" | "failed" | "skipped" | "cancelled" | "blocked" | "held" | "interrupted" | "env-disabled" | "not_run")
reason?: string
exit_code: (number | null)
error_class: ErrorClass
/**
 * @minItems 1
 * @maxItems 5
 */
attempts: [Attempt]|[Attempt, Attempt]|[Attempt, Attempt, Attempt]|[Attempt, Attempt, Attempt, Attempt]|[Attempt, Attempt, Attempt, Attempt, Attempt]
params: Params
seed: number
shards?: {
total: number
done: number
}
determinism: StageDeterminism
performance: ("public" | "local-only")
wall_s?: number
telemetry: (TelemetrySummary | null | LocalOnly)
throughput?: {
value: number
unit: string
}
thermal_flag: boolean
log_tail?: string
/**
 * @maxItems 32
 */
inputs: InputRef[]
/**
 * @maxItems 64
 */
outputs: OutputFile[]
})
export type StageId = ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
export type Variant = string
export type ToolId = string
export type Environment = ("studio" | "isaac" | "rtx" | "isaaclab" | "kit" | "reason" | "pipeline" | "accel" | "external")
export type PythonVersion = string
export type Version = string
export type ErrorClass = ("oom" | "timeout" | "warmup-timeout" | "invalid-output" | "invalid-result" | "nonzero-exit" | "guard" | "lock-timeout" | "lock-not-held" | "cancelled" | "interrupted" | "hold" | "unknown" | null)
/**
 * a parameter value with at most 3 further level(s) of nesting
 */
export type ParamValue_3 = (ParamValue_0 | ParamValue_2[] | {
[k: string]: ParamValue_2 | undefined
})
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 */
export type ParamValue_0 = (string | number | boolean | null)
/**
 * a parameter value with at most 2 further level(s) of nesting
 */
export type ParamValue_2 = (ParamValue_0 | ParamValue_1[] | {
[k: string]: ParamValue_1 | undefined
})
/**
 * a parameter value with at most 1 further level(s) of nesting
 */
export type ParamValue_1 = (ParamValue_0 | ParamValue_0[] | {
[k: string]: ParamValue_0 | undefined
})
/**
 * per-stage GPU telemetry summary (data-model §2.4); a null field is named in `unavailable`
 */
export type TelemetrySummary = {
sample_hz: (number | null)
n_samples: (number | null)
gpu_busy_pct: ({
mean: number
p50: number
p95: number
} | null)
mem_used_peak_bytes: (number | null)
power_w: ({
mean: number
p95: number
max: number
} | null)
power_at_limit_frac: (number | null)
energy_j: (number | null)
sm_clock_mhz: ({
mean: number
p5: number
} | null)
temp_c_max: (number | null)
clocks_event_frac: ({
sw_power_cap: number
sw_thermal: number
hw_thermal: number
hw_slowdown: number
power_brake: number
idle: number
} | null)
nvenc_util_pct?: ({
mean: number
max: number
} | null)
pcie_replays_delta: (number | null)
/**
 * field name -> reason it is null
 */
unavailable?: {
[k: string]: string | undefined
}
}
export type LocalOnly = "measured locally, not published (licence)"
/**
 * a source id, an artefact id of the same run, or a minephys knowledge-table row id
 */
export type InputRef = {
id: ArtefactId
sha256: Sha256
kind: ("source" | "artefact" | "knowledge")
}
export type ArtefactId = string
/**
 * artefact record (data-model §2.5); git host: `path` under web/public/; release host: the asset file name
 */
export type Artefact = {
id: ArtefactId
run_id: RunId
git_sha: GitSha
path: Relpath
bytes: number
sha256: Sha256
media_type?: string
kind: ArtefactKind
producer: {
tool: ToolId
stage: StageKey
}
/**
 * @maxItems 32
 */
inputs: InputRef[]
/**
 * @maxItems 12
 */
cases?: []|[CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
lane: ("live" | "replay" | "static")
lane_measurements?: LaneMeasurements
licence_class: LicenceClass
spdx: SpdxId
attribution?: string
asset_host: ("git" | "release")
release_tag?: ReleaseTag
budget_class: ("videos" | "tiles-glb" | "shards-clouds" | "splats" | "onnx" | "runtimes" | "own-code" | "studio-showcase")
encoder?: Encoder
}
export type ArtefactKind = ("video" | "image" | "figure" | "point-cloud" | "mesh" | "tiles" | "splat" | "onnx" | "table" | "trace" | "shard" | "field" | "text" | "model-card" | "telemetry" | "usd")
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
export type Date = string
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
export type ReleaseTag = string

/**
 * GPU record (data-model §2.2); null for CPU-only runs
 */
export interface Gpu {
backend: ("nvml" | "fake")
index: number
name: string
driver: Driver
vram_total_bytes: number
power_limit_enforced_w: (number | null)
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: StageId
variant?: Variant
}
export interface EnvRecord {
name: Environment
python: (PythonVersion | null)
lock_sha256: Sha256
/**
 * package -> version as read from the lock
 */
versions: {
[k: string]: Version | undefined
}
}
export interface Attempt {
n: number
error_class: ErrorClass
fallback?: Params
duration_s?: number
}
/**
 * effective parameters; nesting depth <= 4 including this object
 */
export interface Params {
[k: string]: ParamValue_3 | undefined
}
export interface StageDeterminism {
class: ("bitwise" | "statistical" | "none")
rerun_check: ("pending" | "pass" | "fail" | "not-applicable")
max_deviation?: number
}
export interface OutputFile {
name: Relpath
sha256: Sha256
bytes: number
}
/**
 * lane measurements (data-model §2.6); the lane value is checked against the gate by tools/check_contracts.py
 */
export interface LaneMeasurements {
web_drivable: boolean
max_asset_bytes: number
interaction_ms: (number | null)
run_ms_t2: (number | null)
trace_bytes: (number | null)
measured: {
tier: "T2"
date: Date
browser: string
}
}
/**
 * encoder record of a video artefact (data-model §2.7)
 */
export interface Encoder {
codec: ("av1" | "h264")
profile: string
pix_fmt: string
width: number
height: number
fps: number
frames: number
duration_s: number
bitrate_kbps: number
vmaf: {
mean: number
p5: number
model: string
}
source_frames_sha256: Sha256
encoder: {
ffmpeg_version: string
build_sha256: Sha256
nvenc_api: (string | null)
/**
 * @maxItems 64
 */
args: string[]
}
encode_fps: (number | null)
}
/**
 * published artefact index web/public/assets/manifest.json (data-model §2.8)
 */
export interface WebIndex {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
kind: "web-index"
schema_version: SchemaVersion
generated: Date
git_sha: GitSha
/**
 * @maxItems 500
 */
runs: {
run_id: RunId
/**
 * relative to web/public/assets/runs/
 */
manifest: Relpath
sha256: Sha256
}[]
/**
 * @maxItems 2000
 */
artefacts: Artefact[]
}
