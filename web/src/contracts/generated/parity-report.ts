/* Generated from contracts/parity-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
/**
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "entry".
 */
export type Entry = {
/**
 * engine ids of the engine table (spec 018 section 7.1)
 */
engine: ("des" | "policies" | "haulage" | "lp" | "routing" | "il1-twin" | "il2-twin" | "granular" | "gns" | "traffic" | "dust-lidar" | "detector" | "geotech" | "forecasters" | "swe" | "fno" | "plume" | "dust-particles" | "blasting" | "watershed" | "unet" | "comminution" | "meta-model" | "mincut" | "volume")
engine_version: Semver
tolerance: Tolerance
fixtures: {
files: number
vectors: number
}
max_error?: MaxError
/**
 * @maxItems 3
 */
browsers: []|[("chromium" | "firefox" | "webkit")]|[("chromium" | "firefox" | "webkit"), ("chromium" | "firefox" | "webkit")]|[("chromium" | "firefox" | "webkit"), ("chromium" | "firefox" | "webkit"), ("chromium" | "firefox" | "webkit")]
verdict: ("pass" | "fail" | "not_run")
reason?: string
}
/**
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "semver".
 */
export type Semver = string
/**
 * parity class and its tolerance; each value is capped at the spec value, so a looser tolerance fails
 */
export type Tolerance = {
/**
 * system class of spec 018 section 7.2; hosted = an engine of specs 007, 013 or 014 judged by its own suite
 */
class: ("analytical-closed-form" | "analytical-iterative" | "monte-carlo-count" | "monte-carlo-binomial" | "exact-stream" | "min-cut" | "rigid-body-hash" | "label-map-exact" | "wgsl-kernel" | "wgsl-observables" | "ml-wasm-fp32" | "ml-webgpu-fp32" | "ml-fp16" | "detector-wasm" | "detector-webgpu" | "hosted")
/**
 * relative tolerance
 */
rtol?: number
/**
 * absolute tolerance as a multiple of the output unit scale s_y (DC-018-02)
 */
atol_scale?: number
/**
 * convergence tolerance of the reference solver; rtol = max(1e-9, 10 x solver_tol)
 */
solver_tol?: number
objective_rtol?: number
/**
 * maximum absolute difference (non-dimensional for WGSL kernels)
 */
max_abs?: number
/**
 * box tolerance in pixels
 */
max_abs_px?: number
top1_agreement_min?: number
/**
 * binomial bound in standard errors, plus 1/N
 */
sigma?: number
observables?: {
repose_deg?: number
runout_rel?: number
discharge_rel?: number
mass_drift_rel?: number
}
/**
 * requirement of the owning spec that fixes the class and tolerance
 */
defined_by?: ("FR-007-10" | "FR-007-15" | "FR-007-20" | "FR-007-32" | "FR-007-39" | "P-013-15" | "FR-014-42")
}
/**
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string

/**
 * Web engine parity report assets/parity-report.json of the built Pages artifact, written by the parity suite in CI (DC-018-05, spec 018-web-cases).
 */
export interface PitStudioWebEngineParityReport {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
/**
 * the built commit
 */
git_sha: string
generated: UtcTimestamp
/**
 * @minItems 1
 * @maxItems 128
 */
engines: [Entry, ...(Entry)[]]
}
/**
 * largest observed error over all vectors and browsers, in the metric of the class
 * 
 * This interface was referenced by `PitStudioWebEngineParityReport`'s JSON-Schema
 * via the `definition` "max_error".
 */
export interface MaxError {
abs?: number
rel?: number
abs_px?: number
objective_rel?: number
/**
 * binomial deviation in standard errors
 */
z?: number
/**
 * differing counts, labels, set members, words or hashes
 */
mismatches?: number
/**
 * lowest observed agreement
 */
top1_agreement?: number
observables?: {
repose_deg?: number
runout_rel?: number
discharge_rel?: number
mass_drift_rel?: number
}
}
