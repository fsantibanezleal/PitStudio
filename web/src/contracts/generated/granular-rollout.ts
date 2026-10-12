/* Generated from contracts/granular-rollout.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Metadata of one 2-D granular rollout payload (Zarr or Parquet) written by st50_physics (DC-011-01, spec 011-surrogates).
 */
export type GranularRolloutMetadata = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
family: ("column-collapse" | "pile-formation" | "dump-over-crest")
geometry_id: Slug
/**
 * recorded geometry parameters of the family (spec §7)
 */
geometry: {
/**
 * column collapse: H0 / L0
 */
aspect_ratio?: number
/**
 * column collapse: L0
 */
column_width_m?: number
pour_point_x_m?: number
pour_height_m?: number
/**
 * 2-D area rate
 */
pour_rate_m2_per_s?: number
crest_x_m?: number
crest_height_m?: number
/**
 * 2-D area rate
 */
dump_rate_m2_per_s?: number
}
packing_seed: number
solver: ("warp-dem" | "newton-mpm")
solver_version: Version
dimensions: 2
/**
 * d
 */
particle_diameter_m: number
/**
 * R = 2.5 d
 */
connectivity_radius_m: number
/**
 * dataset frame interval
 */
frame_interval_s: number
/**
 * x_min, y_min, x_max, y_max
 * 
 * @minItems 4
 * @maxItems 4
 */
bounds_m: [number, number, number, number]
/**
 * strictly increasing
 * 
 * @minItems 2
 * @maxItems 20000
 */
frame_times_s: [number, number, ...(number)[]]
/**
 * constant over every frame
 */
particle_count: number
/**
 * type names in type-index order
 * 
 * @minItems 1
 * @maxItems 16
 */
particle_types: [Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
material: {
density_kg_per_m3: (MaterialValue & {
value?: number
})
sliding_friction: (MaterialValue & {
value?: number
})
rolling_friction?: (MaterialValue & {
value?: number
})
restitution?: (MaterialValue & {
value?: number
})
youngs_modulus_pa?: (MaterialValue & {
value?: number
})
poisson_ratio?: (MaterialValue & {
value?: number
})
friction_angle_deg?: (MaterialValue & {
value?: number
})
cohesion_pa?: (MaterialValue & {
value?: number
})
}
/**
 * T_end of the reference rollout
 */
rest_time_s: number
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
 * via the `definition` "version".
 */
export type Version = string
/**
 * one material parameter with its provenance
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "material_value".
 */
export type MaterialValue = {
value: number
source: ("knowledge-table" | "calibration" | "recipe")
/**
 * knowledge-table row id or calibration trial id
 */
ref?: string
verification?: ("verified" | "UNVERIFIED")
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
 * payload store; sha256 of the file (Parquet) or of the sorted chunk-digest listing (Zarr)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "store".
 */
export interface Store {
format: ("zarr" | "parquet")
path: Relpath
sha256: Sha256
}
