/* Generated from contracts/accel-table.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "date".
 */
export type Date = string
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "row".
 */
export type Row = {
model: Slug
backend: ("pytorch" | "ort-cpu" | "ort-cuda" | "ort-tensorrt" | "tensorrt")
precision: ("fp32" | "fp16" | "int8" | "fp8")
tensorrt_version: (Version | null)
status: ("pass" | "rejected" | "build-failed" | "not_run")
reason?: string
performance: "public"
latency: ([LatencyEntry, LatencyEntry, LatencyEntry, LatencyEntry] | null)
throughput: ([ThroughputEntry, ThroughputEntry, ThroughputEntry]|[ThroughputEntry, ThroughputEntry, ThroughputEntry, ThroughputEntry] | null)
joules_per_inference: (number | null)
vram_peak_bytes: (number | null)
thermal_slowdown: (boolean | null)
camera_streams: (CameraStreams | null)
parity: (Parity | null)
power_limit_enforced_w: (number | null)
power_source: ("ac" | "battery")
tensorrt_licence_sha256: (Sha256 | null)
}
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
export type LatencyEntry = ({
regime: ("spaced" | "sustained")
scope: ("gpu-compute" | "end-to-end")
gap_ms: number
warmup_s: number
iterations: number
timed_s: number
p50: QuantileMs
p90: QuantileMs
p95: QuantileMs
p99: QuantileMs
bootstrap: {
resamples: 2000
seed: number
level: 0.95
}
} & {
regime: ("spaced" | "sustained")
scope: ("gpu-compute" | "end-to-end")
gap_ms: number
warmup_s: number
iterations: number
timed_s: number
p50: QuantileMs
p90: QuantileMs
p95: QuantileMs
p99: QuantileMs
bootstrap: {
resamples: 2000
seed: number
level: 0.95
}
} & {
regime: ("spaced" | "sustained")
scope: ("gpu-compute" | "end-to-end")
gap_ms: number
warmup_s: number
iterations: number
timed_s: number
p50: QuantileMs
p90: QuantileMs
p95: QuantileMs
p99: QuantileMs
bootstrap: {
resamples: 2000
seed: number
level: 0.95
}
} & {
regime: ("spaced" | "sustained")
scope: ("gpu-compute" | "end-to-end")
gap_ms: number
warmup_s: number
iterations: number
timed_s: number
p50: QuantileMs
p90: QuantileMs
p95: QuantileMs
p99: QuantileMs
bootstrap: {
resamples: 2000
seed: number
level: 0.95
}
})
export type ThroughputEntry = ({
sweep: ("batch" | "particles")
size: number
iterations: number
elapsed_s: number
samples_per_s: number
} & {
sweep: ("batch" | "particles")
size: number
iterations: number
elapsed_s: number
samples_per_s: number
} & {
sweep: ("batch" | "particles")
size: number
iterations: number
elapsed_s: number
samples_per_s: number
} & {
sweep: ("batch" | "particles")
size: number
iterations: number
elapsed_s: number
samples_per_s: number
})
/**
 * This interface was referenced by `AccelerationWebTable`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Acceleration table baked by s64_bench from the publishable bench records, with its one-machine caption and every rejected, build-failed or not-run cell (DC-016-05, spec 016-export-acceleration).
 */
export interface AccelerationWebTable {
$schema?: string
schema_version: SchemaVersion
generated: Date
git_sha: GitSha
caption: string
conditions: {
gpu_name: string
driver: Driver
}
/**
 * @minItems 1
 * @maxItems 512
 */
rows: [Row, ...(Row)[]]
}
export interface QuantileMs {
value_ms: number
lo_ms: number
hi_ms: number
}
export interface CameraStreams {
frame_w_px: 3840
frame_h_px: 2160
tile_px: 640
overlap_px: 64
n_tiles: 28
fps: 10
best_batch: (1 | 4 | 16 | 64)
tiles_per_s: number
streams: number
recall: number
recall_score_min: 0.5
recall_iou_min: 0.5
}
export interface Parity {
verdict: ("pass" | "rejected")
reference: "pytorch-fp32-golden"
rtol: (number | null)
atol: (number | null)
max_abs_error: (number | null)
mismatch_fraction: (number | null)
metric_delta_pp: (number | null)
mask_iou: (number | null)
tf32_cleared: true
}
