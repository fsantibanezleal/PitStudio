/* Generated from contracts/slope-section.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "map_point_m".
 */
export type MapPointM = [number, number]
/**
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "point_xz_m".
 */
export type PointXzM = [CoordinateM, CoordinateM]
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "coordinate_m".
 */
export type CoordinateM = number
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "pof_seed".
 */
export type PofSeed = number
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "distribution".
 */
export type Distribution = {
material_id?: ParamKey
parameter: ("cohesion_kpa" | "friction_angle_deg" | "gsi" | "sigma_ci_mpa" | "m_i" | "disturbance_d" | "unit_weight_kn_per_m3" | "pore_pressure_ratio")
distribution: ("normal" | "lognormal" | "uniform")
mean?: number
sd?: number
cv?: number
truncate_lower?: number
truncate_upper?: number
lower?: number
upper?: number
}

/**
 * Two-dimensional C1 slope section (ground polyline, Mohr-Coulomb or Hoek-Brown materials, pore-pressure ratio, input distributions, search, slice and PoF settings, methods, source DEM digest) written by s10_preprocess and the web section editor (DC-010-01, spec 010-slope).
 */
export interface C1SlopeSection {
$schema?: string
schema_version: string
section_id: ArtefactId
source: Source
/**
 * @minItems 2
 * @maxItems 10000
 */
ground: [PointXzM, PointXzM, ...(PointXzM)[]]
crest_x_m: CoordinateM
toe_x_m: CoordinateM
/**
 * @minItems 1
 * @maxItems 8
 */
materials: [Material]|[Material, Material]|[Material, Material, Material]|[Material, Material, Material, Material]|[Material, Material, Material, Material, Material]|[Material, Material, Material, Material, Material, Material]|[Material, Material, Material, Material, Material, Material, Material]|[Material, Material, Material, Material, Material, Material, Material, Material]
pore_pressure_ratio: number
analysis: Analysis
}
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "source".
 */
export interface Source {
kind: ("dem" | "editor" | "fixture")
source_id?: Slug
dem_sha256?: Sha256
crs?: string
profile_start_m?: MapPointM
profile_end_m?: MapPointM
sample_spacing_m?: 1
simplify_tolerance_m?: 0.25
site_label?: string
}
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "material".
 */
export interface Material {
id: ParamKey
model: ("mohr-coulomb" | "hoek-brown")
unit_weight_kn_per_m3: number
cohesion_kpa?: number
friction_angle_deg?: number
gsi?: number
m_i?: number
sigma_ci_mpa?: number
disturbance_d?: number
bottom_z_m?: CoordinateM
}
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "analysis".
 */
export interface Analysis {
mode: ("live" | "baked")
/**
 * @minItems 1
 * @maxItems 2
 */
methods: [("bishop" | "spencer")]|[("bishop" | "spencer"), ("bishop" | "spencer")]
slices: number
search: Search
pof?: Pof
}
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "search".
 */
export interface Search {
entry_points: number
exit_points: number
radius_ratios: number
rho_min: number
rho_max: number
}
/**
 * This interface was referenced by `C1SlopeSection`'s JSON-Schema
 * via the `definition` "pof".
 */
export interface Pof {
samples: number
candidates: number
seed: PofSeed
/**
 * @minItems 1
 * @maxItems 32
 */
distributions: [Distribution, ...(Distribution)[]]
}
