/* Generated from contracts/dispatch-eval.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "seed".
 */
export type Seed = number
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "dispatcher".
 */
export type Dispatcher = ("fixed" | "nearest" | "sptf" | "sq" | "lp" | "ppo" | "attention")
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "comparison".
 */
export type Comparison = {
learned: ("ppo" | "attention")
baseline: ("fixed" | "nearest" | "sptf" | "sq" | "lp" | "ppo")
fleet_size: number
n_pairs: number
/**
 * @maxItems 1000
 */
differences: {
seed: Seed
diff_t_per_h: number
}[]
mean_diff_t_per_h: (number | null)
sd_diff_t_per_h: (number | null)
t_crit: (number | null)
ci95: (Ci95 | null)
verdict: ("learned-better" | "baseline-better" | "no-significant-difference" | "insufficient-evidence")
reason?: ("fewer-than-30-pairs" | "seed-sets-differ" | "non-finite-difference")
}

/**
 * Per-seed dispatcher KPIs and paired learned-versus-baseline verdicts written by s50_evaluate (DC-007-03, spec 007-haulage-dispatch).
 */
export interface PairedDispatchEvaluationTable {
$schema?: string
schema_version: SchemaVersion
id: Slug
recipe: Slug
engine: Engine
mode: "traffic"
variate_profile: "engine"
primary_metric: "production_t_per_h"
ci_method: "paired-t"
ci_level: 0.95
min_pairs: 30
/**
 * @minItems 1
 * @maxItems 64
 */
scenarios: [{
fleet_size: number
bundle_sha256: Sha256
}, ...({
fleet_size: number
bundle_sha256: Sha256
})[]]
/**
 * @minItems 1
 * @maxItems 1000
 */
test_seeds: [Seed, ...(Seed)[]]
/**
 * @minItems 1
 * @maxItems 20000
 */
rows: [Row, ...(Row)[]]
/**
 * @maxItems 512
 */
comparisons: Comparison[]
honesty: Honesty
}
export interface Engine {
package: "minehaulsim"
version: string
pin_sha256: string
}
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "row".
 */
export interface Row {
seed: Seed
dispatcher: Dispatcher
fleet_size: number
production_t_per_h: number
queue_time_mean_min: number
loader_utilisation_frac: number
match_factor: number
truck_hours_per_kt: number
loader_hours_per_kt: number
}
/**
 * This interface was referenced by `PairedDispatchEvaluationTable`'s JSON-Schema
 * via the `definition` "ci95".
 */
export interface Ci95 {
low_t_per_h: number
high_t_per_h: number
}
export interface Honesty {
label: "calibrated synthetic — not validated against real data"
bias_note: "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; no real haul telemetry exists to correct it."
}
