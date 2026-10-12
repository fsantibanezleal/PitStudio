/* Generated from contracts/bench-record.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One s64_bench record per model, backend, precision and TensorRT version: timings with intervals, throughput, energy, VRAM, parity, status and the performance marker (DC-016-01, spec 016-export-acceleration).
 */
export type BenchRecord = {
$schema?: string
schema_version: SchemaVersion
run_id: RunId
git_sha: GitSha
date: Date
model: Slug
backend: Backend
precision: Precision
tensorrt_version: (Version | null)
status: Status
reason?: Reason
performance: ("public" | "local-only")
latency: ([LatencyEntry, LatencyEntry, LatencyEntry, LatencyEntry] | null | LocalOnly)
throughput: ([ThroughputEntry, ThroughputEntry, ThroughputEntry]|[ThroughputEntry, ThroughputEntry, ThroughputEntry, ThroughputEntry] | null | LocalOnly)
joules_per_inference: (number | null | LocalOnly)
energy_window_s: (number | null | LocalOnly)
energy_reason?: Reason
vram_peak_bytes: (number | null | LocalOnly)
thermal_slowdown: (boolean | null | LocalOnly)
telemetry_hz: 10
camera_streams: (CameraStreams | null | LocalOnly)
parity: (Parity | null)
fingerprint: Fingerprint
/**
 * @maxItems 8
 */
notes?: []|[string]|[string, string]|[string, string, string]|[string, string, string, string]|[string, string, string, string, string]|[string, string, string, string, string, string]|[string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "date".
 */
export type Date = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "backend".
 */
export type Backend = ("pytorch" | "ort-cpu" | "ort-cuda" | "ort-tensorrt" | "tensorrt" | "tensorrt-rtx")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "precision".
 */
export type Precision = ("fp32" | "fp16" | "int8" | "fp8")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "status".
 */
export type Status = ("pass" | "rejected" | "build-failed" | "not_run")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "reason".
 */
export type Reason = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "latency_entry".
 */
export type LatencyEntry = {
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
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "local_only".
 */
export type LocalOnly = "measured locally, not published (licence)"
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "throughput_entry".
 */
export type ThroughputEntry = {
sweep: ("batch" | "particles")
size: number
iterations: number
elapsed_s: number
samples_per_s: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fraction".
 */
export type Fraction = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "quantile_ms".
 */
export interface QuantileMs {
value_ms: number
lo_ms: number
hi_ms: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "camera_streams".
 */
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
recall: Fraction
recall_score_min: 0.5
recall_iou_min: 0.5
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "parity".
 */
export interface Parity {
verdict: ("pass" | "rejected")
reference: "pytorch-fp32-golden"
rtol: (number | null)
atol: (number | null)
max_abs_error: (number | null)
mismatch_fraction: (Fraction | null)
metric_delta_pp: (number | null)
mask_iou: (Fraction | null)
tf32_cleared: true
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fingerprint".
 */
export interface Fingerprint {
gpu_name: string
driver: Driver
ort_version: Version
torch_version: Version
onnx_sha256: Sha256
engine_sha256: (Sha256 | null)
power_limit_enforced_w: (number | null)
power_source: ("ac" | "battery")
os_power_mode: ("best-power-efficiency" | "balanced" | "best-performance")
tensorrt_licence_sha256: (Sha256 | null)
}
