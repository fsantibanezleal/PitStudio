/* Generated from contracts/physics-benchmark-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One row per physics benchmark with its oracle, tolerance and verdict, written by st50_physics (DC-005-05, spec 005-physics).
 */
export type PhysicsBenchmarkReport = {
$schema?: string
kind: "physics-benchmark-report"
schema_version: SchemaVersion
report_id: ArtefactId
created: UtcTimestamp
run_id: RunId
git_sha: GitSha
device: {
kind: ("cpu" | "cuda")
name: string
}
/**
 * @minItems 1
 * @maxItems 128
 */
rows: [Row, ...(Row)[]]
/**
 * run-time overhead factor of Warp's deterministic mode, once per Warp solver (FR-005-48, NFR-005-05)
 * 
 * @maxItems 5
 */
overhead: []|[Overhead]|[Overhead, Overhead]|[Overhead, Overhead, Overhead]|[Overhead, Overhead, Overhead, Overhead]|[Overhead, Overhead, Overhead, Overhead, Overhead]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
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
 * via the `definition` "row".
 */
export type Row = {
/**
 * physics benchmark ids; the prefix is the solver id
 */
benchmark: ("dem-contact-law" | "dem-impact" | "dem-restitution" | "dem-rolling" | "dem-slide-roll" | "dem-beverloo-silo" | "dem-beverloo-slot" | "dem-repose" | "dem-collapse-axi" | "dem-mass" | "mpm-newton-collapse-axi" | "mpm-newton-silo" | "mpm-newton-mass" | "mpm-newton-rerun" | "mlsmpm2d-p2g" | "mlsmpm2d-collapse-planar" | "mlsmpm2d-mass" | "swe-ritter" | "swe-stoker" | "swe-lake-at-rest" | "swe-volume" | "swe-bingham-sheet" | "swe-hydrograph" | "dust-stokes" | "dust-diffusion" | "dust-plume" | "dust-mass-budget" | "vehicles-steady-speed" | "vehicles-energy" | "rigid-newton-incline")
/**
 * own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies
 */
solver: ("dem" | "mpm-newton" | "mlsmpm2d" | "swe" | "dust" | "vehicles" | "rigid-newton")
solver_version: Version
material: (MaterialRef | null)
parameters: {
[k: string]: number | boolean | string | undefined
}
oracle: Oracle
/**
 * @maxItems 64
 */
checks: Check[]
verdict: Verdict
reason?: string
gpu_only: boolean
deterministic: boolean
/**
 * SHA-256 of the run's outputs, reproduced on a re-run in deterministic mode (FR-005-48)
 */
outputs_sha256?: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tolerance".
 */
export type Tolerance = {
/**
 * abs: |measured - oracle| <= value; rel: <= value x |oracle|; interval: lower <= measured <= upper; factor: lower <= measured / oracle <= upper
 */
kind: ("abs" | "rel" | "interval" | "factor")
value?: number
lower?: number
upper?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "verdict".
 */
export type Verdict = ("pass" | "fail" | "not run")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "material_ref".
 */
export interface MaterialRef {
id: Slug
/**
 * SHA-256 of the RFC 8785 canonical JSON of the material card
 */
card_sha256: string
youngs_modulus_pa?: number
youngs_modulus_real_pa?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "oracle".
 */
export interface Oracle {
kind: ("analytical" | "published" | "reference-implementation" | "hand-calculation" | "material-card")
/**
 * citation with section, table or page
 */
source: string
url?: HttpsUrl
/**
 * verification status of a value: verified (primary source read), unverified (secondary or unreadable source), calibrated (fitted), reduced (deliberately lowered Young's modulus, FR-005-09), assumed (modelling choice)
 */
status: ("verified" | "unverified" | "calibrated" | "reduced" | "assumed")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "check".
 */
export interface Check {
quantity: ParamKey
/**
 * UCUM case-sensitive unit codes; 1 is dimensionless (also counts)
 */
unit: ("1" | "1/s" | "s" | "m" | "m2" | "m3" | "m/s" | "m/s2" | "m2/s" | "m3/s" | "kg" | "kg/s" | "kg/m2" | "kg/m3" | "Pa" | "Pa.s" | "N" | "N/m" | "N.m" | "W" | "J" | "deg" | "rad/s")
measured: number
oracle: (number | null)
tolerance: Tolerance
pass: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "overhead".
 */
export interface Overhead {
solver: ("dem" | "mlsmpm2d" | "swe" | "dust" | "vehicles")
device: ("cpu" | "cuda")
/**
 * wall time in deterministic mode divided by wall time in the default mode
 */
factor: number
}
/**
 * the stamp every rollout output carries: the benchmark report of its solver version and its verdict (FR-005-47)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "stamp".
 */
export interface Stamp {
report_id: ArtefactId
report_sha256: Sha256
verdict: Verdict
}
