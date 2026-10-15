/* Generated from contracts/console.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Response bodies of the loopback console API (DC-003-01, spec 003-console).
 */
export type PitStudioConsoleResponseBodies = (Health | RecipeSummary | RecipeList | Job | JobList | JobCreated | RunSummary | RunList | Problem)
export type Semver = string
/**
 * a contract's schema_version, or its exact PitStudio $id
 */
export type ContractVersion = string
/**
 * one recipe file (FR-003-07); id and case are null when an invalid file does not yield them
 */
export type RecipeSummary = {
id: (Slug | null)
case: (CaseId | "bench" | null)
path: RecipePath
sha256: Sha256
stages: number
valid: boolean
/**
 * @maxItems 20
 */
errors: []|[ErrorItem]|[ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]|[ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem, ErrorItem]
}
export type Slug = string
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
export type RecipePath = string
export type Sha256 = string
/**
 * a runner job record (FR-003-08); exit_code is the runner exit code of spec 002 plan.md D2
 */
export type Job = {
job_id: JobId
recipe: Slug
state: JobState
run_id: (RunId | null)
created: UtcTimestamp
stage: (StageKey | null)
shards: ({
done: number
total: number
} | null)
exit_code: (number | null)
reason: (string | null)
}
export type JobId = string
/**
 * runner job states (spec 002 plan.md D3)
 */
export type JobState = ("queued" | "running" | "succeeded" | "failed" | "cancelled" | "blocked" | "held" | "interrupted")
export type RunId = string
export type UtcTimestamp = string
/**
 * one run of the store (FR-003-12); manifest fields are null when the manifest is invalid, state is null when no queue record exists
 */
export type RunSummary = {
run_id: RunId
recipe: (Slug | null)
created: (UtcTimestamp | null)
profile: (Slug | null)
state: (JobState | null)
stages: number
published: boolean
valid: boolean
}

/**
 * GET /health (FR-003-06): the only body readable from the public site, so no free text, path, host or user name
 */
export interface Health {
status: "ok"
console_version: Semver
runner_version: Semver
/**
 * schema stem -> contract version
 */
contracts: {
[k: string]: ContractVersion | undefined
}
}
/**
 * one validation error: instance JSON pointer, schema keyword or loader code, one-line message
 */
export interface ErrorItem {
pointer: string
keyword: string
message: string
}
/**
 * GET /recipes
 */
export interface RecipeList {
/**
 * @maxItems 256
 */
recipes: RecipeSummary[]
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
/**
 * GET /queue
 */
export interface JobList {
/**
 * @maxItems 1000
 */
jobs: Job[]
}
/**
 * 202 body of POST /jobs (FR-003-09); location equals the Location header
 */
export interface JobCreated {
job_id: JobId
location: string
}
/**
 * GET /runs
 */
export interface RunList {
/**
 * @maxItems 1000
 */
runs: RunSummary[]
}
/**
 * application/problem+json error body (RFC 9457, FR-003-22); one-line texts, no stack trace
 */
export interface Problem {
type: string
title: string
status: number
detail: string
/**
 * @maxItems 50
 */
errors?: ErrorItem[]
}
