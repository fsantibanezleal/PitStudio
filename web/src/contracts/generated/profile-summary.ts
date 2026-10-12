/* Generated from contracts/profile-summary.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `KernelTimingTable`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `KernelTimingTable`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `KernelTimingTable`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * Top-20 kernel timing table and Chrome trace reference written by a profiled Warp-based studio stage (DC-006-03, spec 006-media-telemetry).
 */
export interface KernelTimingTable {
$schema?: string
kind: "profile-summary"
schema_version: SchemaVersion
run_id?: RunId
stage: StageKey
/**
 * Warp activity timing; never nsys or ncu (FR-006-20)
 */
method: "warp-activity-timing"
label: "kernel timing, no admin rights"
device: ("cpu" | "cuda")
trace: {
/**
 * Chrome trace in the stage's output folder
 */
file: string
format: "chrome-trace-json"
/**
 * tracing stops at 100,000,000 bytes (FR-006-21, NFR-006-03)
 */
bytes: number
}
/**
 * true when tracing stopped at the size cap (FR-006-21)
 */
truncated: boolean
/**
 * distinct kernels recorded
 */
kernels_total: number
/**
 * the kernels with the largest total time, largest first
 * 
 * @maxItems 20
 */
kernels: []|[Kernel]|[Kernel, Kernel]|[Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]|[Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel, Kernel]
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
/**
 * This interface was referenced by `KernelTimingTable`'s JSON-Schema
 * via the `definition` "kernel".
 */
export interface Kernel {
name: string
calls: number
total_ms: number
mean_ms: number
}
