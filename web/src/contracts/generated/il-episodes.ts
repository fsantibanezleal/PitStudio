/* Generated from contracts/il-episodes.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * JSON sidecar of an IL episode table, with the IL-1 and IL-2 / IL-3 row column sets as $defs (DC-014-04, spec 014-robot-learning).
 */
export type PitStudioILEpisodeTable = {
$schema?: string
schema_version: SchemaVersion
/**
 * Policy id.
 */
policy: ("IL-1" | "IL-2" | "IL-3")
/**
 * Arm of the paired comparison.
 */
arm: ("policy" | "baseline" | "twin" | "mpm")
run_id: RunId
/**
 * Controller that produced the episodes.
 */
controller: {
kind: ("policy" | "pure-pursuit-pid" | "scripted-dig")
/**
 * Checkpoint digest, or digest of the frozen baseline parameters.
 */
sha256: string
}
/**
 * Mean action, no sampling.
 */
deterministic_actions: true
/**
 * SHA-256 of the sorted seed list (pairing check).
 */
seed_set_sha256: string
column_set: ("il1-episode" | "dig-episode")
/**
 * Parquet episode table.
 */
table: {
path: Relpath
bytes: number
sha256: Sha256
/**
 * Episodes in the table.
 */
rows: number
}
}
/**
 * Contract version (major 1).
 * 
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
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * One row of an IL-1 episode table (Parquet).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "il1_episode".
 */
export interface Il1Episode {
/**
 * Episode seed.
 */
seed: number
/**
 * Light vehicles in the scenario.
 */
light_vehicles: number
termination: ("success" | "collision" | "lateral_error" | "time_limit" | "invalid_value")
/**
 * Reached L_route - 2 m without collision.
 */
success: boolean
collision: boolean
/**
 * Control steps.
 */
steps: number
/**
 * Sum of squared lateral errors over the steps (m2).
 */
sum_sq_lateral_error_m2: number
/**
 * Per-episode RMS lateral error (m).
 */
rms_lateral_error_m: number
/**
 * Per-episode maximum lateral error (m).
 */
max_lateral_error_m: number
/**
 * Minimum TTC (s); +inf (Parquet) when never closing.
 */
min_ttc_s: number
/**
 * Traction energy per gross tonne-kilometre (kWh/(t km)).
 */
energy_kwh_per_t_km: number
/**
 * Fraction of steps within v_lim.
 */
frac_within_v_lim: number
}
/**
 * One row of an IL-2 / IL-3 episode table (Parquet).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dig_episode".
 */
export interface DigEpisode {
/**
 * Episode seed.
 */
seed: number
termination: ("completed" | "time_limit" | "invalid_value")
/**
 * Fill factor k_f at dig completion or at the time limit (-).
 */
fill_factor: number
/**
 * Cycle time t_c (s); 30 if not completed.
 */
cycle_time_s: number
/**
 * Productivity P = k_f / t_c (1/s).
 */
productivity_per_s: number
/**
 * At least one stall event.
 */
stalled: boolean
/**
 * Bucket lifted >= 0.5 m above the local terrain after cutting.
 */
lift_off: boolean
}
