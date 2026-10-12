/* Generated from contracts/sdg-randomisation.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "seed".
 */
export type Seed = number
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Domain-randomisation config of the perception SDG (arms, counts, structured parameter sources, unstructured ranges, texture pool, drying time, oversize limit) read by the DR sampler and st55_sdg (DC-009-03, spec 009-perception).
 */
export interface SDGRandomisationConfig {
$schema?: string
schema_version: string
seed: Seed
x_os_m: number
drying_time_min: number
/**
 * @minItems 1
 * @maxItems 3
 */
arms: [Arm]|[Arm, Arm]|[Arm, Arm, Arm]
structured: Structured
unstructured: Unstructured
/**
 * @minItems 1
 * @maxItems 4096
 */
texture_pool: [Texture, ...(Texture)[]]
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "arm".
 */
export interface Arm {
family: ("pit" | "crusher")
arm: ("structured" | "unstructured")
image_count: number
seed_source: ("own" | "structured-pit-train")
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "structured".
 */
export interface Structured {
sun: {
source: "solar-position"
year: number
min_elevation_deg: 5
}
dust: {
source: "plume-field"
}
wet_roads: {
source: "watering-schedule"
}
placement: {
source: "pit-design"
max_base_offset_m: 0.05
}
rock_textures: {
source: "lithology-cc0"
lithologies: {
/**
 * @minItems 1
 * @maxItems 256
 */
[k: string]: [ArtefactId, ...(ArtefactId)[]] | undefined
}
}
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "unstructured".
 */
export interface Unstructured {
textures: "whole-pool-uniform"
light_intensity_factor: FactorRange
colour_temperature_k: KelvinRange
sun_direction: "upper-hemisphere-uniform"
object_positions: "visible-ground-uniform"
distractors: CountRange
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "factor_range".
 */
export interface FactorRange {
distribution: "log-uniform"
min: number
max: number
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "kelvin_range".
 */
export interface KelvinRange {
distribution: "uniform"
min: number
max: number
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "count_range".
 */
export interface CountRange {
distribution: "uniform-integer"
min: number
max: number
}
/**
 * This interface was referenced by `SDGRandomisationConfig`'s JSON-Schema
 * via the `definition` "texture".
 */
export interface Texture {
id: ArtefactId
source_id: Slug
sha256: Sha256
spdx: "CC0-1.0"
}
