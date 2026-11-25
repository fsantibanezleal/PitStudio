/* Generated from contracts/events.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Run event lines, telemetry samples, published telemetry and the stream error payload (DC-002-03, spec 002-runner; SSE payloads DC-003-04).
 */
export type PitStudioRunEventsAndTelemetry = (Event | TelemetrySample | PublishedTelemetry | StreamError)
/**
 * one line of runs/<run_id>/events.jsonl (plan.md D6), at most 16,384 bytes; seq strictly increasing per run
 */
export type Event = {
seq: number
t: UtcTimestamp
run_id: RunId
type: ("run-started" | "run-finished" | "stage-started" | "stage-finished" | "stage-cache-hit" | "stage-retry" | "stage-skipped" | "stage-not-run" | "shard-finished" | "guard-refused" | "lock-waiting" | "lock-acquired" | "hold-detected" | "store-corrupt" | "low-disk" | "cancelled" | "interrupted")
stage?: StageKey
shard?: number
detail?: string
/**
 * scalar details of the event
 */
data?: {
[k: string]: string | number | boolean | null | undefined
}
}
export type UtcTimestamp = string
export type RunId = string

/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
/**
 * one line of runs/<run_id>/telemetry.jsonl (plan.md D6); an unsupported, failing, non-finite or negative reading is null (FR-002-32); shard 0 for unsharded stages
 */
export interface TelemetrySample {
t_s: number
run_id: RunId
stage: StageKey
shard: number
gpu: number
mem_used_bytes: (number | null)
mem_total_bytes: (number | null)
util_pct: (number | null)
power_w: (number | null)
power_limit_w: (number | null)
temp_c: (number | null)
sm_clock_mhz: (number | null)
clocks_event_mask: (number | null)
energy_mj: (number | null)
nvenc_util_pct: (number | null)
pcie_replays: (number | null)
}
/**
 * web/public/assets/runs/<run_id>/telemetry.json written by studio publish (FR-002-48, FR-002-50); public stages only, at most 200 KB
 */
export interface PublishedTelemetry {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
run_id: RunId
/**
 * @maxItems 64
 */
stages: PublishedStage[]
}
export interface PublishedStage {
key: StageKey
performance: "public"
bucket_s: number
/**
 * @maxItems 2000
 */
points: PublishedPoint[]
}
/**
 * one equal-time bucket: mean utilisation, power and clock; maximum temperature and memory; OR of the masks
 */
export interface PublishedPoint {
t_s: number
util_pct: (number | null)
power_w: (number | null)
sm_clock_mhz: (number | null)
temp_c: (number | null)
mem_used_bytes: (number | null)
clocks_event_mask: (number | null)
}
/**
 * data of the console's SSE `error` event: an events.jsonl line that is not a valid event (spec 003 plan.md D4)
 */
export interface StreamError {
line: number
message: string
}
