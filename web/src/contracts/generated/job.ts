/* Generated from contracts/job.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Job spec the runner hands to a stage process and the stage result it reads back (DC-002-02, spec 002-runner).
 */
export type PitStudioJobSpecAndStageResult = (JobSpec | StageResult)
export type SchemaVersion = string
export type RunId = string
export type ModulePath = string
/**
 * a source id, or <stage key>/<output path> of an upstream stage (the names of the cache key, FR-002-08)
 */
export type InputName = string
/**
 * absolute local path in forward-slash form (job specs are local only and never published): an optional drive, no empty, `.` or `..` segment, no backslash
 */
export type LocalPath = string
export type Sha256 = string
/**
 * the execution folder <store>/runs/<run_id>/tmp/<stage key>/<shard> (FR-002-12)
 */
export type StageDir = LocalPath
export type Slug = string
/**
 * stage result result.json written by the stage helper (plan.md D5); at most 65,536 bytes
 */
export type StageResult = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
status: ("succeeded" | "failed" | "not_run")
error_class: ResultErrorClass
reason?: Reason
message?: string
/**
 * @maxItems 64
 */
outputs: StageOutput[]
/**
 * observable -> value (finite)
 */
observables?: {
[k: string]: number | undefined
}
throughput?: Throughput
checkpoint: boolean
}
/**
 * error classes a stage may report itself; the runner assigns the others (data-model 001 section 2.3)
 */
export type ResultErrorClass = ("oom" | "invalid-output" | "lock-not-held" | "unknown" | null)
/**
 * why the stage could not run: one line, not blank
 */
export type Reason = string
/**
 * an output relative to the execution folder
 */
export type StageOutput = {
path: Relpath
validator?: ValidatorId
validated?: boolean
artefact?: OutputArtefact
}
export type Relpath = string
export type ValidatorId = string
/**
 * artefact facts the stage reports for an output offered for publication (manifest artefact rules 4 and 5)
 */
export type OutputArtefact = {
kind: ArtefactKind
media_type?: string
budget_class: ("videos" | "tiles-glb" | "shards-clouds" | "splats" | "onnx" | "runtimes" | "own-code" | "studio-showcase")
/**
 * @maxItems 12
 */
cases?: []|[CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
lane_measurements?: LaneMeasurements
encoder?: Encoder
}
export type ArtefactKind = ("video" | "image" | "figure" | "point-cloud" | "mesh" | "tiles" | "splat" | "onnx" | "table" | "trace" | "shard" | "field" | "text" | "model-card" | "telemetry" | "usd")
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")

/**
 * job spec runs/<run_id>/tmp/<stage key>/<shard>/job.json written by the runner (plan.md D5); local only
 */
export interface JobSpec {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
run_id: RunId
stage: StageKey
entry: ModulePath
params: Params
seed: number
shard: (Shard | null)
/**
 * @maxItems 32
 */
inputs: {
name: InputName
path: LocalPath
sha256: Sha256
}[]
output_dir: StageDir
scratch_dir: LocalPath
resume: boolean
rerun: boolean
profiling: boolean
profile: {
id: Slug
cpu_slots: number
}
vram_fraction: (number | null)
nvtx_range: string
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
/**
 * effective parameters; nesting depth <= 4 including this object
 */
export interface Params {
/**
 * a parameter value with at most 3 further level(s) of nesting
 */
[k: string]: string | number | boolean | null | ((string | number | boolean | null) | ((string | number | boolean | null) | (string | number | boolean | null)[] | {
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 */
[k: string]: string | number | boolean | null | undefined
})[] | {
/**
 * a parameter value with at most 1 further level(s) of nesting
 */
[k: string]: string | number | boolean | null | (string | number | boolean | null)[] | {
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 */
[k: string]: string | number | boolean | null | undefined
} | undefined
})[] | {
/**
 * a parameter value with at most 2 further level(s) of nesting
 */
[k: string]: string | number | boolean | null | ((string | number | boolean | null) | (string | number | boolean | null)[] | {
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 */
[k: string]: string | number | boolean | null | undefined
})[] | {
/**
 * a parameter value with at most 1 further level(s) of nesting
 */
[k: string]: string | number | boolean | null | (string | number | boolean | null)[] | {
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 */
[k: string]: string | number | boolean | null | undefined
} | undefined
} | undefined
} | undefined
}
/**
 * 0-based shard index; size = items per shard and total = items (the recipe's `shardable`)
 */
export interface Shard {
index: number
size: number
total: number
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
date: string
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
source_frames_sha256: string
encoder: {
ffmpeg_version: string
build_sha256: string
nvenc_api: (string | null)
/**
 * @maxItems 64
 */
args: string[]
}
encode_fps: (number | null)
}
export interface Throughput {
value: number
unit: string
}
