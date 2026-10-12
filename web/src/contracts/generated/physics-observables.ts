/* Generated from contracts/physics-observables.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Description of a Parquet observables table written by st50_physics, stored as the file's key-value metadata (DC-005-03, spec 005-physics).
 */
export type PhysicsObservablesTableDescription = {
$schema?: string
kind: "physics-observables"
schema_version: SchemaVersion
scenario: Slug
run_id?: RunId
/**
 * own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies
 */
solver: ("dem" | "mpm-newton" | "mlsmpm2d" | "swe" | "dust" | "vehicles" | "rigid-newton")
/**
 * version of the solver package read from studio/uv.lock (warp-lang for own Warp solvers, newton for Newton solvers)
 */
solver_version: string
warp_version: Version
seed: number
device: ("cpu" | "cuda")
/**
 * fixed step, or the CFL step of the shallow-water solver (FR-005-23)
 */
dt_mode: ("fixed" | "cfl")
/**
 * the fixed step, or the smallest CFL step taken
 */
dt_s: number
/**
 * the largest CFL step taken
 */
dt_max_s?: number
/**
 * Rayleigh time step of the smallest particle (FR-005-08)
 */
rayleigh_dt_s?: number
rayleigh_fraction?: number
/**
 * both values when a reduced Young's modulus is used (FR-005-09)
 */
youngs_modulus?: {
used_pa: number
real_pa: number
}
/**
 * conserved quantity of the budget series (FR-005-15, FR-005-20, FR-005-28, FR-005-37, FR-005-42)
 */
budget: ("mass" | "volume" | "energy")
rows: number
/**
 * @minItems 1
 * @maxItems 128
 */
columns: [Column, ...(Column)[]]
stamp: Stamp
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "column".
 */
export type Column = {
name: ParamKey
unit: Unit
dtype: ("float32" | "float64" | "int32" | "int64" | "uint32" | "uint64" | "bool")
/**
 * time axis, step index, observable, budget series term, swept parameter
 */
role: ("time" | "step" | "observable" | "budget" | "parameter")
description?: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * UCUM case-sensitive unit codes; 1 is dimensionless (also counts)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = ("1" | "1/s" | "s" | "m" | "m2" | "m3" | "m/s" | "m/s2" | "m2/s" | "m3/s" | "kg" | "kg/s" | "kg/m2" | "kg/m3" | "Pa" | "Pa.s" | "N" | "N/m" | "N.m" | "W" | "J" | "deg" | "rad/s")

/**
 * the stamp every rollout output carries: the benchmark report of its solver version and its verdict (FR-005-47)
 */
export interface Stamp {
report_id: string
report_sha256: string
verdict: ("pass" | "fail" | "not run")
}
