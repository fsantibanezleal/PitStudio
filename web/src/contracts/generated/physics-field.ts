/* Generated from contracts/physics-field.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Root-group attributes of a Zarr v3 field store (grid, CRS record, time axis, variables with units) written by st50_physics or supplied as a wind field (DC-005-02, spec 005-physics).
 */
export type PhysicsFieldStoreMetadata = {
$schema?: string
kind: "physics-field"
schema_version: SchemaVersion
/**
 * shallow-water state, C2 maps (FR-005-30), dust concentration or deposition, wind field (FR-005-33), particle state
 */
field_set: ("swe-state" | "c2-maps" | "dust-concentration" | "dust-deposition" | "wind" | "particle-state")
scenario?: Slug
run_id?: RunId
/**
 * own Warp DEM, Newton implicit MPM, own explicit 2-D MLS-MPM twin, own shallow water, own Lagrangian dust, reduced-order vehicles, Newton rigid bodies
 */
solver?: ("dem" | "mpm-newton" | "mlsmpm2d" | "swe" | "dust" | "vehicles" | "rigid-newton")
solver_version?: Version
seed?: number
/**
 * origin of a supplied wind field
 */
source?: string
grid: Grid
crs: Crs
time: TimeAxis
/**
 * @minItems 1
 * @maxItems 32
 */
variables: [Variable, ...(Variable)[]]
/**
 * depth threshold of the C2 maps (FR-005-30, default 0.05 m)
 */
h_thr_m?: number
inundated_area_m2?: number
/**
 * @maxItems 8
 */
inputs?: []|[Input]|[Input, Input]|[Input, Input, Input]|[Input, Input, Input, Input]|[Input, Input, Input, Input, Input]|[Input, Input, Input, Input, Input, Input]|[Input, Input, Input, Input, Input, Input, Input]|[Input, Input, Input, Input, Input, Input, Input, Input]
stamp?: Stamp
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
 * via the `definition` "grid".
 */
export type Grid = {
kind: ("regular-2d" | "regular-3d" | "particles")
/**
 * spatial shape: (y, x), (z, y, x) or (particle)
 * 
 * @minItems 1
 * @maxItems 3
 */
shape: [number]|[number, number]|[number, number, number]
/**
 * horizontal cell size
 */
cell_size_m?: number
/**
 * vertical cell size of a 3-D grid
 */
cell_height_m?: number
/**
 * site-local (x, y) or (x, y, z) of the first cell centre
 * 
 * @minItems 2
 * @maxItems 3
 */
origin_m?: [number, number]|[number, number, number]
}
/**
 * site-local frame (x east, y north, z up, metres) relative to the site origin of the scene (DC-004-01, DC-004-03), or the local frame of a synthetic benchmark
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "crs".
 */
export type Crs = {
frame: ("site-enu" | "benchmark-local")
origin?: SiteOrigin
source?: CrsRecord
}
export type CrsRef = {
/**
 * EPSG code read from the file; null when none exists
 */
epsg: (number | null)
/**
 * WKT read from the file; required when no EPSG code exists
 */
wkt?: string
}
export type LinearUnit = {
name: ("metre" | "us-survey-foot" | "international-foot")
/**
 * factor applied to reach metres (FR-004-03)
 */
factor_to_m: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "time_axis".
 */
export type TimeAxis = {
/**
 * series: a time dimension; reduced: maps over [start_s, end_s]; static: time-invariant
 */
mode: ("series" | "reduced" | "static")
start_s?: number
end_s?: number
step_s?: number
count?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "variable".
 */
export type Variable = {
name: ("depth" | "momentum_x" | "momentum_y" | "velocity_x" | "velocity_y" | "velocity_z" | "bed_elevation" | "arrival_time" | "max_depth" | "max_speed" | "concentration" | "deposition" | "wind_u" | "wind_v" | "wind_w" | "position_x" | "position_y" | "position_z" | "radius" | "mass" | "particle_id")
/**
 * UCUM case-sensitive unit codes; 1 is dimensionless (also counts)
 */
unit: ("1" | "1/s" | "s" | "m" | "m2" | "m3" | "m/s" | "m/s2" | "m2/s" | "m3/s" | "kg" | "kg/s" | "kg/m2" | "kg/m3" | "Pa" | "Pa.s" | "N" | "N/m" | "N.m" | "W" | "J" | "deg" | "rad/s")
dtype: ("float32" | "float64" | "int32" | "int64" | "uint32" | "uint8")
/**
 * @minItems 1
 * @maxItems 4
 */
dims: [("time" | "z" | "y" | "x" | "particle")]|[("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle")]|[("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle")]|[("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle"), ("time" | "z" | "y" | "x" | "particle")]
/**
 * Zarr v3 JSON fill value; NaN marks never-reached cells of arrival_time
 */
fill_value?: (number | "NaN")
description?: string
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
 * site origin of the site-local frame (FR-004-02)
 */
export interface SiteOrigin {
/**
 * EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)
 */
epsg: number
easting_m: number
northing_m: number
/**
 * origin elevation z0 in the vertical datum of the inputs, m
 */
z0_m: number
}
/**
 * CRS record of the terrain inputs, copied from the terrain grid
 */
export interface CrsRecord {
horizontal: CrsRef
vertical: CrsRef
horizontal_unit: LinearUnit
vertical_unit: LinearUnit
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "input".
 */
export interface Input {
role: ("terrain-grid" | "wind-field" | "initial-state")
path: Relpath
sha256: Sha256
}
/**
 * the stamp every rollout output carries: the benchmark report of its solver version and its verdict (FR-005-47)
 */
export interface Stamp {
report_id: string
report_sha256: string
verdict: ("pass" | "fail" | "not run")
}
