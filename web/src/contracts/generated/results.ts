/* Generated from contracts/results.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One published comparison web/public/results/<comparison-id>.json (DC-020-02, spec 020-web-knowledge).
 */
export type ResultsBundle = (ComparisonBundle | AccelerationBundle)
export type Slug = string
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
export type RunId = string
export type CriterionStatus = ({
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
} & {
requirement: string
status: ("pass" | "fail" | "not-run")
reason?: string
})
/**
 * Paired comparison; verdict by the decision rule of FR-020-22 on the oriented interval.
 */
export type PairedRow = {
kind: "paired"
group?: Slug
metric: Metric
challenger: Label
baseline: Label
pairing_unit: NameEnEs
n: number
interval: DiffInterval
verdict: ("challenger-better" | "baseline-better" | "no-significant-difference")
}
export type ParamKey = string
export type Label = string
/**
 * 95 % interval of the paired difference challenger - baseline, in the metric's unit.
 */
export type DiffInterval = {
lo: number
hi: number
level: 0.95
method: ("paired-t" | "paired-bootstrap")
resamples?: number
}
/**
 * Exact McNemar test; b = challenger right and baseline wrong, c = the reverse.
 */
export type McnemarRow = {
kind: "mcnemar"
group?: Slug
metric: Metric
challenger: Label
baseline: Label
pairing_unit: NameEnEs
n: number
b: number
c: number
p_value: number
verdict: ("challenger-better" | "baseline-better" | "no-significant-difference")
}
export type Driver = string
export type Version = string
export type AccelRow = ({
model: Slug
backend: ("pytorch" | "ort-cpu" | "ort-cuda" | "ort-tensorrt" | "tensorrt")
precision: ("fp32" | "fp16" | "int8" | "fp8")
status: ("accepted" | "rejected" | "build-failed" | "not-run")
reason?: string
latency_ms: (Latency | null)
throughput_items_per_s: (number | null)
energy_j_per_inference: (number | null)
accuracy_delta_pp: (number | null)
parity: ("pass" | "rejected" | "not-run")
tensorrt_licence_sha256?: Sha256
} & {
model: Slug
backend: ("pytorch" | "ort-cpu" | "ort-cuda" | "ort-tensorrt" | "tensorrt")
precision: ("fp32" | "fp16" | "int8" | "fp8")
status: ("accepted" | "rejected" | "build-failed" | "not-run")
reason?: string
latency_ms: (Latency | null)
throughput_items_per_s: (number | null)
energy_j_per_inference: (number | null)
accuracy_delta_pp: (number | null)
parity: ("pass" | "rejected" | "not-run")
tensorrt_licence_sha256?: Sha256
})
export type Sha256 = string

/**
 * Comparison rows shown together, never folded into a composite score (FR-020-21).
 */
export interface ComparisonBundle {
$schema?: string
schema_version: string
id: Slug
title: NameEnEs
/**
 * @minItems 1
 * @maxItems 12
 */
cases: [CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
/**
 * @minItems 1
 * @maxItems 32
 */
run_ids: [RunId, ...(RunId)[]]
/**
 * @minItems 0
 * @maxItems 8
 */
criteria: []|[CriterionStatus]|[CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]
kind: "comparison"
tab: ("learned-vs-classical" | "sim-to-real" | "dr-ablation" | "isaac-lab" | "cosmos")
/**
 * @minItems 1
 * @maxItems 64
 */
rows: [(PairedRow | McnemarRow | SingleEventRow | EstimateRow), ...((PairedRow | McnemarRow | SingleEventRow | EstimateRow))[]]
}
export interface NameEnEs {
en: string
es: string
}
export interface Metric {
id: ParamKey
name: NameEnEs
unit: string
orientation: ("higher-is-better" | "lower-is-better")
}
export interface SingleEventRow {
kind: "single-event"
group?: Slug
metric: Metric
challenger: Label
baseline: Label
n: 1
challenger_value: number
baseline_value: number
verdict: "single-real-event"
}
/**
 * One system's metric with its interval, optionally against a pre-registered threshold.
 */
export interface EstimateRow {
kind: "estimate"
group?: Slug
metric: Metric
system: Label
n: number
value: number
interval?: EstimateInterval
threshold?: {
comparator: ("ge" | "le")
value: number
}
}
export interface EstimateInterval {
lo: number
hi: number
level: 0.95
method: ("percentile-bootstrap" | "wilson" | "t")
}
export interface AccelerationBundle {
$schema?: string
schema_version: string
id: Slug
title: NameEnEs
/**
 * @minItems 1
 * @maxItems 12
 */
cases: [CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
/**
 * @minItems 1
 * @maxItems 32
 */
run_ids: [RunId, ...(RunId)[]]
/**
 * @minItems 0
 * @maxItems 8
 */
criteria: []|[CriterionStatus]|[CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]|[CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus, CriterionStatus]
kind: "acceleration"
tab: "acceleration"
conditions: Conditions
/**
 * @minItems 1
 * @maxItems 256
 */
rows: [AccelRow, ...(AccelRow)[]]
}
export interface Conditions {
gpu: string
driver: Driver
power_limit_enforced_w: (number | null)
throttle_frac: {
sw_power_cap: number
sw_thermal: number
hw_thermal: number
hw_slowdown: number
power_brake: number
}
versions?: {
[k: string]: Version | undefined
}
}
export interface Latency {
p50: number
p95: number
}
