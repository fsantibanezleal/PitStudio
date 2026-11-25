/* Generated from contracts/d1-design-grid.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `D1BlastDesignGrid`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string

/**
 * Design grid of case D1 (x50, x80, oversize, PPV, flyrock radius) computed by minephys.blasting in the D1 recipe (DC-012-05, spec 012-fragmentation).
 */
export interface D1BlastDesignGrid {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
case_id: "D1"
minephys_version: Version
kuzram_variant: ("cunningham1983" | "cunningham2005")
distribution: ("kco-swebrec" | "rosin-rammler")
units: {
x50: "m"
x80: "m"
oversize: "%"
ppv: "m/s"
flyrock_radius: "m"
}
fixed_inputs: DesignInputs
/**
 * @minItems 1
 * @maxItems 4
 */
axes: [{
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}]|[{
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}]|[{
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}]|[{
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}, {
input: ("air_density_kg_per_m3" | "bench_height_m" | "beta" | "burden_m" | "charge_length_m" | "charge_per_delay_kg" | "distance_m" | "drag_coefficient" | "drilling_deviation_m" | "explosive_density_kg_per_m3" | "fragment_diameter_m" | "hole_diameter_m" | "k_site_m_per_s" | "launch_speed_m_per_s" | "oversize_limit_m" | "rock_density_kg_per_m3" | "rock_factor" | "rws" | "spacing_m" | "x_max_m")
/**
 * @minItems 1
 * @maxItems 64
 */
values: [number, ...(number)[]]
}]
/**
 * @minItems 1
 * @maxItems 4096
 */
points: [Point, ...(Point)[]]
}
/**
 * design inputs in SI units, as minephys.blasting takes them
 * 
 * This interface was referenced by `D1BlastDesignGrid`'s JSON-Schema
 * via the `definition` "design_inputs".
 */
export interface DesignInputs {
burden_m?: number
spacing_m?: number
bench_height_m?: number
/**
 * m, not mm
 */
hole_diameter_m?: number
charge_length_m?: number
drilling_deviation_m?: number
explosive_density_kg_per_m3?: number
/**
 * relative weight strength, ANFO = 100
 */
rws?: number
/**
 * Cunningham's range
 */
rock_factor?: number
x_max_m?: number
oversize_limit_m?: number
distance_m?: number
charge_per_delay_kg?: number
k_site_m_per_s?: number
beta?: number
launch_speed_m_per_s?: number
fragment_diameter_m?: number
rock_density_kg_per_m3?: number
drag_coefficient?: number
air_density_kg_per_m3?: number
}
/**
 * one grid point: the swept inputs and the model outputs
 * 
 * This interface was referenced by `D1BlastDesignGrid`'s JSON-Schema
 * via the `definition` "point".
 */
export interface Point {
inputs: DesignInputs
x50_m: number
x80_m: number
oversize_pct: number
ppv_m_per_s: number
flyrock_radius_m: number
}
