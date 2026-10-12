/* Generated from contracts/physics-scenario.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Physics scenario parameters that st50_physics reads from a recipe stage's params (DC-005-01, spec 005-physics).
 */
export type PhysicsScenario = {
schema_version: SchemaVersion
scenario: Slug
description?: string
/**
 * benchmark run, browser-twin parity golden, or production rollout (any scenario that is not a benchmark)
 */
kind: ("benchmark" | "parity-golden" | "production")
solver: Solver
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
benchmarks?: BenchmarkId[]
twin?: Twin
geometry: Geometry
counts: Counts
time_step: TimeStep
output: Output
/**
 * @maxItems 16
 */
materials: []|[MaterialCard]|[MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]|[MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard, MaterialCard]
/**
 * @maxItems 16
 */
vehicle_cards?: []|[VehicleCard]|[VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]|[VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard, VehicleCard]
dem?: DemBlock
mpm_newton?: MpmNewtonBlock
mlsmpm2d?: Mlsmpm2DBlock
swe?: SweBlock
dust?: DustBlock
vehicles?: VehiclesBlock
rigid_newton?: RigidNewtonBlock
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
 * own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "solver".
 */
export type Solver = ("dem" | "mpm-newton" | "mlsmpm2d" | "swe" | "dust" | "vehicles" | "rigid-newton")
/**
 * physics benchmark ids; the prefix is the solver id
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "benchmark_id".
 */
export type BenchmarkId = ("dem-contact-law" | "dem-impact" | "dem-restitution" | "dem-rolling" | "dem-slide-roll" | "dem-beverloo-silo" | "dem-beverloo-slot" | "dem-repose" | "dem-collapse-axi" | "dem-mass" | "mpm-newton-collapse-axi" | "mpm-newton-silo" | "mpm-newton-mass" | "mpm-newton-rerun" | "mlsmpm2d-p2g" | "mlsmpm2d-collapse-planar" | "mlsmpm2d-mass" | "swe-ritter" | "swe-stoker" | "swe-lake-at-rest" | "swe-volume" | "swe-bingham-sheet" | "swe-hydrograph" | "dust-stokes" | "dust-diffusion" | "dust-plume" | "dust-mass-budget" | "vehicles-steady-speed" | "vehicles-energy" | "rigid-newton-incline")
/**
 * browser-twin scenario of FR-005-22
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "twin".
 */
export type Twin = ("dem-pile" | "mlsmpm2d-collapse" | "swe-dam-break" | "dust-release")
/**
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "vec3_m".
 */
export type Vec3M = [number, number, number]
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "time_step".
 */
export type TimeStep = (TimeStep1 & {
/**
 * fixed step; the shallow-water solver uses the CFL step instead (FR-005-23)
 */
dt_s?: number
steps?: number
end_time_s?: number
})
export type TimeStep1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "output".
 */
export type Output = {
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
 * via the `definition` "material_card".
 */
export type MaterialCard = {
id: Slug
label?: string
model: ("dem-sphere" | "mpm-granular" | "mpm-drucker-prager-2d" | "bingham-tailings" | "dust-particle" | "air")
density_kg_m3?: (Quantity & {
value?: number
})
youngs_modulus_pa?: (Quantity & {
value?: number
})
youngs_modulus_real_pa?: (Quantity & {
value?: number
})
poisson_ratio?: (Quantity & {
value?: number
})
restitution?: (Quantity & {
value?: number
})
friction_static?: (Quantity & {
value?: number
})
friction_rolling?: (Quantity & {
value?: number
})
diameter_m?: (Quantity & {
value?: number
})
diameter_min_m?: (Quantity & {
value?: number
})
diameter_max_m?: (Quantity & {
value?: number
})
repose_target_deg?: (Quantity & {
value?: number
})
repose_method?: ("lifted-cylinder" | "poured-cone")
friction_coefficient?: (Quantity & {
value?: number
})
yield_pressure_pa?: (Quantity & {
value?: number
})
viscosity_pa_s?: (Quantity & {
value?: number
})
friction_angle_deg?: (Quantity & {
value?: number
})
cohesion_pa?: (Quantity & {
value?: number
})
yield_stress_pa?: (Quantity & {
value?: number
})
bingham_viscosity_pa_s?: (Quantity & {
value?: number
})
particle_radius_m?: (Quantity & {
value?: number
})
dynamic_viscosity_pa_s?: (Quantity & {
value?: number
})
}
/**
 * a material or vehicle value with its citation and verification status; the unit is the suffix of the field name
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "quantity".
 */
export type Quantity = {
value: number
status: Status
/**
 * citation with table or page
 */
source?: string
url?: HttpsUrl
note?: string
}
/**
 * verification status of a value: verified (primary source read), unverified (secondary or unreadable source), calibrated (fitted), reduced (deliberately lowered Young's modulus, FR-005-09), assumed (modelling choice)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "status".
 */
export type Status = ("verified" | "unverified" | "calibrated" | "reduced" | "assumed")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "swe_block".
 */
export type SweBlock = {
rheology: ("frictionless" | "bingham")
material?: Slug
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
 * via the `definition` "dust_block".
 */
export type DustBlock = {
particle_material: Slug
air_material: Slug
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
sources: [DustSource, ...(DustSource)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dust_source".
 */
export type DustSource = {
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
 * via the `definition` "geometry".
 */
export interface Geometry {
shape: ("two-body" | "plane" | "incline" | "silo-cylinder" | "slot-quasi2d" | "column-axisymmetric" | "column-planar" | "box" | "channel" | "benched-crop" | "terrain-crop" | "open-field" | "grade-segment" | "road-network")
domain_min_m: Vec3M
domain_max_m: Vec3M
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
 * via the `definition` "counts".
 */
export interface Counts {
particles?: number
cells_x?: number
cells_y?: number
cells_z?: number
vehicles?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "vehicle_card".
 */
export interface VehicleCard {
id: Slug
label?: string
mass_kg: (Quantity & {
value?: number
})
power_w: (Quantity & {
value?: number
})
efficiency: (Quantity & {
value?: number
})
traction_coefficient: (Quantity & {
value?: number
})
drive_weight_fraction: (Quantity & {
value?: number
})
rolling_resistance_pct: (Quantity & {
value?: number
})
retarder_power_w: (Quantity & {
value?: number
})
retarder_efficiency: (Quantity & {
value?: number
})
drag_coefficient: (Quantity & {
value?: number
})
frontal_area_m2: (Quantity & {
value?: number
})
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dem_block".
 */
export interface DemBlock {
material: Slug
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
 * via the `definition` "mpm_newton_block".
 */
export interface MpmNewtonBlock {
material: Slug
voxel_size_m: number
grid_type: ("sparse" | "fixed" | "dense")
max_iterations: number
tolerance: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "mlsmpm2d_block".
 */
export interface Mlsmpm2DBlock {
material: Slug
/**
 * cells per axis of the square grid
 */
grid_cells: number
particles_per_cell: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "vehicles_block".
 */
export interface VehiclesBlock {
/**
 * a constant-grade segment (geometry.grade_pct) or the road network (DC-004-06)
 */
road: ("grade-segment" | "network")
air_density_kg_m3: number
/**
 * @minItems 1
 * @maxItems 64
 */
fleet: [Slug, ...(Slug)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "rigid_newton_block".
 */
export interface RigidNewtonBlock {
friction_coefficient: number
mass_kg: number
/**
 * @minItems 3
 * @maxItems 3
 */
size_m: [number, number, number]
}
