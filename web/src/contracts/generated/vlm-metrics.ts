/* Generated from contracts/vlm-metrics.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Metrics tables of the reason lane: footprint bench, agreement gate, tasks A-C and the optional real probe, written by the scoring stages (DC-015-05, spec 015-vlm).
 */
export type ReasonLaneMetrics = {
$schema?: string
schema_version: SchemaVersion
run_id: RunId
git_sha: GitSha
generated: Date
notices: Notices
bench: Bench
gate: Gate
task_a: TaskA
task_b: TaskB
task_c: TaskC
real_probe: RealProbe
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
 * via the `definition` "bench".
 */
export type Bench = {
status: ("measured" | "not_run")
reason?: Reason
performance: "public"
label: "our hardware, not a comparative benchmark"
n_queries: 200
/**
 * @maxItems 2
 */
paths: []|[BenchPath]|[BenchPath, BenchPath]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "reason".
 */
export type Reason = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "bench_path".
 */
export type BenchPath = {
path: ("q8_0" | "bf16")
status: ("measured" | "not_run")
reason?: Reason
context_tokens: number
vram_peak_bytes: (number | null)
prefill_tokens_per_s: (number | null)
decode_tokens_per_s: (number | null)
wall_s_per_query: ({
mean: number
p50: number
p95: number
} | null)
gpu: (Gpu | null)
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "gate".
 */
export type Gate = {
status: ("pass" | "fail" | "not_run")
reason?: Reason
n: 500
agree: (number | null)
agreement: (Fraction | null)
wilson95: ({
lo: Fraction
hi: Fraction
} | null)
threshold: 0.95
q8_0_path: ("accepted" | "rejected" | "not_run")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fraction".
 */
export type Fraction = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "task_a".
 */
export type TaskA = {
status: ("measured" | "not_run")
reason?: Reason
/**
 * @maxItems 128
 */
rows: RowA[]
/**
 * @maxItems 14
 */
mcnemar: []|[McnemarRow]|[McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]|[McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow, McnemarRow]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "row_a".
 */
export type RowA = {
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base" | "detector-rule" | "constant")
reasoning: boolean
type: number
status: ("measured" | "not_run" | "not_applicable" | "rejected")
reason?: Reason
n: number
balanced_accuracy: (Estimate | null)
f1: (Estimate | null)
unparseable_rate: (Fraction | null)
error_rate: (Fraction | null)
auroc: (Fraction | null)
/**
 * @maxItems 4
 */
by_condition: []|[{
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}]|[{
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}]|[{
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}]|[{
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}, {
condition: ("day" | "night" | "dust" | "rain")
n: number
balanced_accuracy: (Fraction | null)
}]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "mcnemar_row".
 */
export type McnemarRow = {
type: (number | "pooled-binary")
cosmos_arm: ("cosmos-q8_0" | "cosmos-bf16")
b: number
c: number
p: Fraction
chi2_cc: (number | null)
verdict: ("Cosmos beats Qwen base" | "no significant difference")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "task_b".
 */
export type TaskB = {
status: ("measured" | "not_run")
reason?: Reason
n_pairs: 100
/**
 * @maxItems 8
 */
rows: []|[RowB]|[RowB, RowB]|[RowB, RowB, RowB]|[RowB, RowB, RowB, RowB]|[RowB, RowB, RowB, RowB, RowB]|[RowB, RowB, RowB, RowB, RowB, RowB]|[RowB, RowB, RowB, RowB, RowB, RowB, RowB]|[RowB, RowB, RowB, RowB, RowB, RowB, RowB, RowB]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "row_b".
 */
export type RowB = {
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base" | "physics-check")
status: ("measured" | "not_run" | "rejected")
reason?: Reason
input_mode: ("native-video" | "frame-list-approximation" | "simulation-state")
n_pairs: number
accuracy: (TEstimate | null)
verdict: (("above chance" | "not above chance") | null)
position_bias: (Fraction | null)
single_clip_auroc: (Fraction | null)
detection_rate: ({
"gravity-x0.3": Fraction
"zero-friction": Fraction
"mass-injection": Fraction
"time-reversal": Fraction
interpenetration: Fraction
"frozen-particles": Fraction
} | null)
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "task_c".
 */
export type TaskC = {
status: ("measured" | "not_run")
reason?: Reason
/**
 * @maxItems 8
 */
rows: []|[RowC]|[RowC, RowC]|[RowC, RowC, RowC]|[RowC, RowC, RowC, RowC]|[RowC, RowC, RowC, RowC, RowC]|[RowC, RowC, RowC, RowC, RowC, RowC]|[RowC, RowC, RowC, RowC, RowC, RowC, RowC]|[RowC, RowC, RowC, RowC, RowC, RowC, RowC, RowC]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "row_c".
 */
export type RowC = {
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base" | "template-caption")
status: ("measured" | "not_run" | "rejected")
reason?: Reason
n_captions: number
chair_i: (Fraction | null)
chair_s: (Fraction | null)
recall: (Fraction | null)
no_object_rate: (Fraction | null)
condition_ba: ({
dust: (Fraction | null)
night: (Fraction | null)
rain: (Fraction | null)
} | null)
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "real_probe".
 */
export type RealProbe = {
status: ("measured" | "not_measured")
n_images: number
cohen_kappa: (number | null)
/**
 * @maxItems 64
 */
rows: RowA[]
}

export interface Notices {
cosmos: "Built on NVIDIA Cosmos"
honesty: "Zero-shot 2B VLM; not a safety system."
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "gpu".
 */
export interface Gpu {
name: string
driver: Driver
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "estimate".
 */
export interface Estimate {
value: Fraction
lo: Fraction
hi: Fraction
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "t_estimate".
 */
export interface TEstimate {
value: Fraction
lo: number
hi: number
}
