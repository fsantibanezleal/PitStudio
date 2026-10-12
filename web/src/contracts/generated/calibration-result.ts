/* Generated from contracts/calibration-result.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One calibration trial or literature-target calibration of the Warp DEM written by the calibration driver (DC-011-04, spec 011-surrogates).
 */
export type DEMCalibrationResult = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
kind: ("synthetic-trial" | "literature-target")
arm: ("gradient" | "cma-es")
trial_id: Slug
solver: ("warp-dem" | "newton-mpm")
solver_version: Version
/**
 * true: (sliding, rolling) from repose and discharge
 */
secondary_arm: boolean
particle_count: number
/**
 * particle count halved once after out-of-memory
 */
oom_fallback: boolean
target: {
/**
 * target repose angle
 */
theta_deg: number
/**
 * secondary arm only
 */
discharge_rate_kg_per_s?: number
packing_seed?: Seed
material?: Slug
/**
 * knowledge-table row id or calibration trial id
 */
knowledge_row?: string
verification?: ("verified" | "UNVERIFIED")
}
/**
 * @minItems 1
 * @maxItems 2
 */
parameters: [ParameterResult]|[ParameterResult, ParameterResult]
loss: {
observable: "smooth-envelope"
softmax_beta_per_d: 10
bin_width_d: 2
bin_range_pct: [20,80]
/**
 * @minItems 1
 * @maxItems 2
 */
terms: [{
name: ("repose" | "discharge")
weight: number
value: number
}]|[{
name: ("repose" | "discharge")
weight: number
value: number
}, {
name: ("repose" | "discharge")
weight: number
value: number
}]
total: number
smooth_theta_deg: number
hard_theta_deg: number
}
/**
 * W, recorded steps
 */
window_steps: number
settling_steps: number
/**
 * S
 */
packing_seeds: number
/**
 * R
 */
interval_runs: number
/**
 * pairwise disjoint seed sets
 */
seeds: {
/**
 * @minItems 1
 * @maxItems 64
 */
target: [Seed, ...(Seed)[]]
/**
 * @minItems 1
 * @maxItems 64
 */
optimisation: [Seed, ...(Seed)[]]
/**
 * @minItems 1
 * @maxItems 64
 */
interval: [Seed, ...(Seed)[]]
/**
 * @maxItems 64
 */
gradient_check?: Seed[]
}
/**
 * forward-equivalent budget (one adjoint pass = 2)
 */
budget_simulations: number
simulations: number
interval_simulations: number
/**
 * gradient-check runs, outside the budget
 */
check_simulations: number
stop_reason: ("loss-tolerance" | "budget")
wall_time_s: number
deterministic_accumulation: boolean
/**
 * @minItems 2
 * @maxItems 4
 */
gradient_check?: [GradientCheck, GradientCheck]|[GradientCheck, GradientCheck, GradientCheck]|[GradientCheck, GradientCheck, GradientCheck, GradientCheck]
gradient_status?: ("reliable" | "unreliable")
cmaes?: {
sigma0: 0.1
population: number
cma_version?: Version
}
label: "calibrated synthetic — not validated against real data"
}
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
 * via the `definition` "seed".
 */
export type Seed = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "parameter_result".
 */
export type ParameterResult = {
name: ("sliding_friction" | "rolling_friction")
/**
 * synthetic truth (synthetic trials only)
 */
truth?: number
start: number
/**
 * lower, upper
 * 
 * @minItems 2
 * @maxItems 2
 */
bounds: [number, number]
estimate: number
/**
 * h = 0.05 x estimate
 */
fd_step: number
/**
 * seed-ensemble delta interval; bounds null when not identified
 */
interval: {
level: 0.95
lower: (number | null)
upper: (number | null)
/**
 * Student t 0.975 quantile with R - 1 degrees of freedom
 */
t_quantile: number
sigma_theta_deg: number
/**
 * central-difference slope of the seed means
 */
slope_deg_per_unit: number
/**
 * @minItems 2
 * @maxItems 2
 */
slope_interval_deg_per_unit: [number, number]
}
identification: ("identified" | "not-identified" | "weakly-identified")
covers_truth?: boolean
}
/**
 * tape gradient against the 4 + 4 run central finite difference
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "gradient_check".
 */
export type GradientCheck = {
iterate: ("first" | "final")
parameter: ("sliding_friction" | "rolling_friction")
mu: number
tape_gradient: number
fd_gradient: number
se_fd: number
runs_per_side: 4
dof: 6
trusted: boolean
failure: ("none" | "fd-not-significant" | "sign-mismatch" | "disagreement")
}
