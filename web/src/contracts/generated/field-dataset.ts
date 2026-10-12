/* Generated from contracts/field-dataset.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Metadata of one Warp shallow-water or dust field run on a terrain patch written by st50_physics (DC-011-03, spec 011-surrogates).
 */
export type FNOFieldDatasetMetadata = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
model: ("tailings" | "dust")
patch_id: Slug
scenario_id: Slug
source_dem: {
source_id: Slug
sha256: Sha256
}
cell_size_m: number
grid: {
nx: (64 | 128)
ny: (64 | 128)
}
/**
 * true only for the 128 x 128 resolution-transfer runs (labelled not claimed)
 */
resolution_transfer: boolean
/**
 * payload channels in store order
 * 
 * @minItems 2
 * @maxItems 32
 */
channels: [{
name: ParamKey
role: ("input" | "output")
unit: Unit
}, {
name: ParamKey
role: ("input" | "output")
unit: Unit
}, ...({
name: ParamKey
role: ("input" | "output")
unit: Unit
})[]]
/**
 * scenario parameters drawn from the recipe ranges
 */
scenario: {
/**
 * grid cell index
 */
breach_row?: number
/**
 * grid cell index
 */
breach_col?: number
release_volume_m3?: number
/**
 * Bingham yield stress
 */
yield_stress_pa?: number
/**
 * Bingham plastic viscosity
 */
plastic_viscosity_pa_s?: number
density_kg_per_m3?: number
/**
 * grid cell index
 */
source_row_start?: number
/**
 * grid cell index
 */
source_col_start?: number
/**
 * grid cell index
 */
source_row_end?: number
/**
 * grid cell index
 */
source_col_end?: number
source_strength_kg_per_m2_s?: number
wind_speed_m_per_s?: number
/**
 * direction the wind blows from, clockwise from north
 */
wind_direction_deg?: number
}
t_end_s: number
/**
 * tailings: t_k = k T_end / 8, k = 1..8
 * 
 * @minItems 1
 * @maxItems 8
 */
output_times_s?: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]
/**
 * dust: start and end of the time average
 * 
 * @minItems 2
 * @maxItems 2
 */
averaging_window_s?: [number, number]
solver: ("warp-swe-bingham" | "warp-dust")
solver_version: Version
store: Store
label: "calibrated synthetic — not validated against real data"
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * physical unit ("1" = dimensionless, counts, indices and categories)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = ("1" | "m" | "mm" | "um" | "m^2" | "m^3" | "m^2/s" | "s" | "h" | "deg" | "rad" | "m/s" | "m/s^2" | "mm/h" | "h/mm" | "Pa" | "Pa.s" | "kg" | "kg/m^3" | "kg/m^2/s" | "ug/m^3" | "kW" | "kWh/t" | "t/h" | "USD/kg" | "USD/kWh" | "USD/t")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * payload store; sha256 of the file (Parquet) or of the sorted chunk-digest listing (Zarr)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "store".
 */
export interface Store {
format: "zarr"
path: Relpath
sha256: Sha256
}
