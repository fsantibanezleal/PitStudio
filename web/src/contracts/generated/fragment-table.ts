/* Generated from contracts/fragment-table.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `MuckPileFragmentTable`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `MuckPileFragmentTable`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `MuckPileFragmentTable`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * JSON sidecar of the Parquet fragment table
 */
export interface MuckPileFragmentTable {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
synthetic: true
pile_seed: number
/**
 * target parameters of the pile
 */
generator: {
/**
 * Swebrec of minephys.blasting, truncated to [x_min, x_max]
 */
passing_function: "swebrec-truncated"
x50_m: number
x_max_m: number
x_min_m: number
b: number
/**
 * V
 */
target_volume_m3: number
size_classes: 20
density_kg_per_m3: number
minephys_version: Version
}
/**
 * exact realised PSD summary (the truth of the pile)
 */
realised: {
fragment_count: number
/**
 * V_real
 */
total_volume_m3: number
/**
 * v_max
 */
max_fragment_volume_m3: number
/**
 * volume-weighted quantile Q-1
 */
x50_m: number
/**
 * volume-weighted quantile Q-1
 */
x80_m: number
}
view_count: number
/**
 * the Parquet table whose rows follow $defs/row
 */
table: {
format: "parquet"
path: Relpath
sha256: Sha256
rows: number
}
}
/**
 * one Parquet row of the fragment table
 * 
 * This interface was referenced by `MuckPileFragmentTable`'s JSON-Schema
 * via the `definition` "row".
 */
export interface Row {
/**
 * equals the instance id in every render mask (0 = background)
 */
fragment_id: number
/**
 * volume-equivalent sphere diameter x
 */
size_m: number
/**
 * pi x^3 / 6
 */
volume_m3: number
mass_kg: number
/**
 * size class j of K = 20 log-spaced classes
 */
class_index: number
/**
 * seed of the fragment's procedural rock mesh
 */
seed: number
/**
 * visible pixels per view, in view order
 * 
 * @maxItems 64
 */
visible_px: number[]
}
