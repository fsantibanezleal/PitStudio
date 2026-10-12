/* Generated from contracts/export-parity-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Parity report of one model variant at layer 1, 2 or 4 against the PyTorch fp32 golden outputs, written by s60_export and s64_bench (DC-016-03, spec 016-export-acceleration).
 */
export type ExportParityReport = {
$schema?: string
schema_version: SchemaVersion
run_id: RunId
git_sha: GitSha
layer: (1 | 2 | 4)
model: Slug
variant: ("deployed" | "parity")
precision: ("fp32" | "fp16" | "int8" | "fp8")
backend: ("ort-cpu" | "ort-cuda" | "ort-tensorrt" | "tensorrt")
tensorrt_version: (Version | null)
onnx_sha256: Sha256
engine_sha256: (Sha256 | null)
golden_set: GoldenSet
tolerances: {
rtol: Tolerance
atol: Tolerance
max_abs: Tolerance
metric_delta_pp_max: Tolerance
mask_iou_min: (Fraction | null)
}
max_abs_error: (number | null)
mismatch_fraction: (Fraction | null)
argmax: (Argmax | null)
metric: (Metric | null)
mask_iou: (Fraction | null)
verdict: ("pass" | "rejected")
reason?: string
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
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tolerance".
 */
export type Tolerance = (number | null)
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fraction".
 */
export type Fraction = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "golden_set".
 */
export interface GoldenSet {
id: Slug
split: ("validation" | "held-out")
/**
 * @minItems 200
 * @maxItems 5000
 */
inputs: [Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, Sha256, ...(Sha256)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "argmax".
 */
export interface Argmax {
output: string
gap_threshold: 0.0002
rows: number
rows_small_gap: number
agreement: Fraction
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "metric".
 */
export interface Metric {
id: ParamKey
unit: "pct"
fp32: number
variant: number
delta_pp: number
}
