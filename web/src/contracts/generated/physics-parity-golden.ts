/* Generated from contracts/physics-parity-golden.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Initial state, scenario and golden observables of one browser-twin scenario, written by st50_physics in Warp's deterministic mode (DC-005-06, spec 005-physics).
 */
export type PhysicsParityGolden = {
$schema?: string
kind: "physics-parity-golden"
schema_version: SchemaVersion
golden_id: Slug
created: UtcTimestamp
git_sha: GitSha
run_id?: RunId
/**
 * browser-twin scenario of FR-005-22
 */
twin: ("dem-pile" | "mlsmpm2d-collapse" | "swe-dam-break" | "dust-release")
/**
 * web engine id of the twin (spec 018 engine table)
 */
engine: ("granular" | "swe" | "dust-particles")
/**
 * warp-lang version read from studio/uv.lock
 */
solver_version: string
/**
 * the scenario parameters (DC-005-01) the golden was produced with; seed and parameters live here
 */
scenario: ({
schema_version: ScenarioSchemaVersion
scenario: ScenarioSlug
description?: string
/**
 * benchmark run, browser-twin parity golden, or production rollout (any scenario that is not a benchmark)
 */
kind: ("benchmark" | "parity-golden" | "production")
solver: ScenarioSolver
/**
 * cpu hides CUDA from the process (FR-005-49)
 */
device: ("cpu" | "cuda")
seed: number
/**
 * Warp deterministic execution mode for atomic operations (FR-005-48)
 */
deterministic: boolean
/**
 * @maxItems 32
 */
benchmarks?: ScenarioBenchmarkId[]
twin?: ScenarioTwin
geometry: ScenarioGeometry
counts: ScenarioCounts
time_step: ScenarioTimeStep
output: ScenarioOutput
/**
 * @maxItems 16
 */
materials: []|[ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]|[ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard, ScenarioMaterialCard]
/**
 * @maxItems 16
 */
vehicle_cards?: []|[ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]|[ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard, ScenarioVehicleCard]
dem?: ScenarioDemBlock
mpm_newton?: ScenarioMpmNewtonBlock
mlsmpm2d?: ScenarioMlsmpm2DBlock
swe?: ScenarioSweBlock
dust?: ScenarioDustBlock
vehicles?: ScenarioVehiclesBlock
rigid_newton?: ScenarioRigidNewtonBlock
} & {
kind?: "parity-golden"
})
/**
 * SHA-256 of the RFC 8785 canonical JSON of scenario
 */
scenario_sha256: string
initial_state: InitialState
observables: Observables
/**
 * SHA-256 of the deterministic run's outputs (FR-005-22, FR-005-48)
 */
outputs_sha256: string
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
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_schema_version".
 */
export type ScenarioSchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_slug".
 */
export type ScenarioSlug = string
/**
 * own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_solver".
 */
export type ScenarioSolver = ("dem" | "mpm-newton" | "mlsmpm2d" | "swe" | "dust" | "vehicles" | "rigid-newton")
/**
 * physics benchmark ids; the prefix is the solver id
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_benchmark_id".
 */
export type ScenarioBenchmarkId = ("dem-contact-law" | "dem-impact" | "dem-restitution" | "dem-rolling" | "dem-slide-roll" | "dem-beverloo-silo" | "dem-beverloo-slot" | "dem-repose" | "dem-collapse-axi" | "dem-mass" | "mpm-newton-collapse-axi" | "mpm-newton-silo" | "mpm-newton-mass" | "mpm-newton-rerun" | "mlsmpm2d-p2g" | "mlsmpm2d-collapse-planar" | "mlsmpm2d-mass" | "swe-ritter" | "swe-stoker" | "swe-lake-at-rest" | "swe-volume" | "swe-bingham-sheet" | "swe-hydrograph" | "dust-stokes" | "dust-diffusion" | "dust-plume" | "dust-mass-budget" | "vehicles-steady-speed" | "vehicles-energy" | "rigid-newton-incline")
/**
 * browser-twin scenario of FR-005-22
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_twin".
 */
export type ScenarioTwin = ("dem-pile" | "mlsmpm2d-collapse" | "swe-dam-break" | "dust-release")
/**
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_vec3_m".
 */
export type ScenarioVec3M = [number, number, number]
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_time_step".
 */
export type ScenarioTimeStep = (ScenarioTimeStep1 & {
/**
 * fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)
 */
dt_s?: number
steps?: number
end_time_s?: number
})
export type ScenarioTimeStep1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_output".
 */
export type ScenarioOutput = {
every_steps: number
fields: boolean
replay: boolean
replay_fps?: number
/**
 * replay shard cap (FR-005-45)
 */
shard_bytes_max?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_material_card".
 */
export type ScenarioMaterialCard = {
id: ScenarioSlug
label?: string
model: ("dem-sphere" | "mpm-granular" | "mpm-drucker-prager-2d" | "bingham-tailings" | "dust-particle" | "air")
density_kg_m3?: (ScenarioQuantity & {
value?: number
})
youngs_modulus_pa?: (ScenarioQuantity & {
value?: number
})
youngs_modulus_real_pa?: (ScenarioQuantity & {
value?: number
})
poisson_ratio?: (ScenarioQuantity & {
value?: number
})
restitution?: (ScenarioQuantity & {
value?: number
})
friction_static?: (ScenarioQuantity & {
value?: number
})
friction_rolling?: (ScenarioQuantity & {
value?: number
})
diameter_m?: (ScenarioQuantity & {
value?: number
})
diameter_min_m?: (ScenarioQuantity & {
value?: number
})
diameter_max_m?: (ScenarioQuantity & {
value?: number
})
repose_target_deg?: (ScenarioQuantity & {
value?: number
})
repose_method?: ("lifted-cylinder" | "poured-cone")
friction_coefficient?: (ScenarioQuantity & {
value?: number
})
yield_pressure_pa?: (ScenarioQuantity & {
value?: number
})
viscosity_pa_s?: (ScenarioQuantity & {
value?: number
})
friction_angle_deg?: (ScenarioQuantity & {
value?: number
})
cohesion_pa?: (ScenarioQuantity & {
value?: number
})
yield_stress_pa?: (ScenarioQuantity & {
value?: number
})
bingham_viscosity_pa_s?: (ScenarioQuantity & {
value?: number
})
particle_radius_m?: (ScenarioQuantity & {
value?: number
})
dynamic_viscosity_pa_s?: (ScenarioQuantity & {
value?: number
})
}
/**
 * a material or vehicle value with its citation and verification status; the unit is the suffix of the field name
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_quantity".
 */
export type ScenarioQuantity = {
value: number
status: ScenarioStatus
/**
 * citation with table or page
 */
source?: string
url?: ScenarioHttpsUrl
note?: string
}
/**
 * verification status of a value: verified (primary source read), unverified (secondary or unreadable source), calibrated (fitted), reduced (deliberately lowered Young's modulus, FR-005-09), assumed (modelling choice)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_status".
 */
export type ScenarioStatus = ("verified" | "unverified" | "calibrated" | "reduced" | "assumed")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_https_url".
 */
export type ScenarioHttpsUrl = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_swe_block".
 */
export type ScenarioSweBlock = {
rheology: ("frictionless" | "bingham")
material?: ScenarioSlug
/**
 * C_CFL in (0, 0.5] (FR-005-23, default 0.45)
 */
cfl: number
h_dry_m: number
h_thr_m: number
boundary: ("closed" | "open")
initial: ("dam-break" | "lake-at-rest" | "dry" | "sheet-flow")
dam_x_m?: number
depth_left_m?: number
depth_right_m?: number
surface_z_m?: number
inflow_depth_m?: number
hydrograph?: {
volume_m3: number
peak_m3_s: number
peak_fraction: number
}
breach?: {
x_m: number
y_m: number
width_m: number
}
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_dust_block".
 */
export type ScenarioDustBlock = {
particle_material: ScenarioSlug
air_material: ScenarioSlug
/**
 * K >= 0 (FR-005-39)
 */
diffusivity_m2_s: number
settling: boolean
ground: ("terrain" | "reflecting" | "none")
wind: ("uniform" | "gridded")
/**
 * @minItems 3
 * @maxItems 3
 */
wind_m_s?: [number, number, number]
/**
 * @minItems 1
 * @maxItems 64
 */
sources: [ScenarioDustSource, ...(ScenarioDustSource)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_dust_source".
 */
export type ScenarioDustSource = {
mode: ("continuous" | "instantaneous")
x_m: number
y_m: number
z_m: number
rate_kg_s?: number
mass_kg?: number
start_s: number
end_s?: number
}
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
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_geometry".
 */
export interface ScenarioGeometry {
shape: ("two-body" | "plane" | "incline" | "silo-cylinder" | "slot-quasi2d" | "column-axisymmetric" | "column-planar" | "box" | "channel" | "benched-crop" | "terrain-crop" | "open-field" | "grade-segment" | "road-network")
domain_min_m: ScenarioVec3M
domain_max_m: ScenarioVec3M
diameter_m?: number
height_m?: number
width_m?: number
thickness_m?: number
length_m?: number
/**
 * @minItems 1
 * @maxItems 16
 */
orifice_m?: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
/**
 * @minItems 1
 * @maxItems 16
 */
aspect_ratios?: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
incline_deg?: number
bed_slope?: number
grade_pct?: number
/**
 * @maxItems 3
 */
periodic_axes?: []|[("x" | "y" | "z")]|[("x" | "y" | "z"), ("x" | "y" | "z")]|[("x" | "y" | "z"), ("x" | "y" | "z"), ("x" | "y" | "z")]
/**
 * @maxItems 7
 */
outflow?: []|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]|[("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice"), ("x-min" | "x-max" | "y-min" | "y-max" | "z-min" | "z-max" | "orifice")]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_counts".
 */
export interface ScenarioCounts {
particles?: number
cells_x?: number
cells_y?: number
cells_z?: number
vehicles?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_vehicle_card".
 */
export interface ScenarioVehicleCard {
id: ScenarioSlug
label?: string
mass_kg: (ScenarioQuantity & {
value?: number
})
power_w: (ScenarioQuantity & {
value?: number
})
efficiency: (ScenarioQuantity & {
value?: number
})
traction_coefficient: (ScenarioQuantity & {
value?: number
})
drive_weight_fraction: (ScenarioQuantity & {
value?: number
})
rolling_resistance_pct: (ScenarioQuantity & {
value?: number
})
retarder_power_w: (ScenarioQuantity & {
value?: number
})
retarder_efficiency: (ScenarioQuantity & {
value?: number
})
drag_coefficient: (ScenarioQuantity & {
value?: number
})
frontal_area_m2: (ScenarioQuantity & {
value?: number
})
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_dem_block".
 */
export interface ScenarioDemBlock {
material: ScenarioSlug
/**
 * per-particle contact-list capacity (FR-005-06, default 12)
 */
contact_capacity: number
/**
 * f_R of the time-step guard (FR-005-08, default 0.2)
 */
rayleigh_fraction: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_mpm_newton_block".
 */
export interface ScenarioMpmNewtonBlock {
material: ScenarioSlug
voxel_size_m: number
grid_type: ("sparse" | "fixed" | "dense")
max_iterations: number
tolerance: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_mlsmpm2d_block".
 */
export interface ScenarioMlsmpm2DBlock {
material: ScenarioSlug
/**
 * cells per axis of the square grid
 */
grid_cells: number
particles_per_cell: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_vehicles_block".
 */
export interface ScenarioVehiclesBlock {
/**
 * a constant-grade segment (geometry.grade_pct) or the road network (DC-004-06)
 */
road: ("grade-segment" | "network")
air_density_kg_m3: number
/**
 * @minItems 1
 * @maxItems 64
 */
fleet: [ScenarioSlug, ...(ScenarioSlug)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scenario_rigid_newton_block".
 */
export interface ScenarioRigidNewtonBlock {
friction_coefficient: number
mass_kg: number
/**
 * @minItems 3
 * @maxItems 3
 */
size_m: [number, number, number]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "initial_state".
 */
export interface InitialState {
file: Relpath
sha256: Sha256
bytes: number
/**
 * little-endian float32 arrays: particle positions and velocities (2-D or 3-D), or the depth and bed grids
 */
layout: ("particles-xyz-vxyz-f32le" | "particles-xy-vxy-f32le" | "grid-depth-bed-f32le")
/**
 * particles or cells (twin caps: 2 x 10^4 particles, 256 x 256 cells)
 */
items: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "observables".
 */
export interface Observables {
repose_deg?: number
runout_m?: number
discharge?: Series
/**
 * |total mass (or volume) at the end - initial| / initial; bounded by the loosest conservation requirement of the twin solvers (FR-005-28)
 */
mass_drift_rel: number
}
/**
 * Q(t)
 */
export interface Series {
unit: ("kg/s" | "m3/s")
/**
 * @minItems 2
 * @maxItems 1024
 */
t_s: [number, number, ...(number)[]]
/**
 * @minItems 2
 * @maxItems 1024
 */
values: [number, number, ...(number)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "series".
 */
export interface Series1 {
unit: ("kg/s" | "m3/s")
/**
 * @minItems 2
 * @maxItems 1024
 */
t_s: [number, number, ...(number)[]]
/**
 * @minItems 2
 * @maxItems 1024
 */
values: [number, number, ...(number)[]]
}
