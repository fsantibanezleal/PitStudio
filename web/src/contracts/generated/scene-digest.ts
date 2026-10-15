/* Generated from contracts/scene-digest.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * absolute USD prim path
 * 
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "prim_path".
 */
export type PrimPath = string

/**
 * Geometry prims of the flattened stage per lod variant, written by st40_compose for the export parity test (DC-004-08, spec 004-scene-pipeline). Version 1.1: optional `fixture` member.
 */
export interface SceneDigest {
$schema?: string
schema_version: SchemaVersion
kind: "scene-digest"
case: CaseId
manifest_id: Slug
params_sha256: Sha256
up_axis: "Z"
meters_per_unit: 1
kilograms_per_unit: 1
/**
 * @minItems 1
 * @maxItems 3
 */
lods: [LodDigest]|[LodDigest, LodDigest]|[LodDigest, LodDigest, LodDigest]
/**
 * True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false.
 */
fixture?: boolean
}
/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "lod_digest".
 */
export interface LodDigest {
/**
 * name of a `lod` variant; one per terrain LOD (FR-004-08)
 */
lod: ("lod0" | "lod1" | "lod2")
/**
 * @minItems 1
 * @maxItems 20000
 */
prims: [Prim, ...(Prim)[]]
}
/**
 * This interface was referenced by `SceneDigest`'s JSON-Schema
 * via the `definition` "prim".
 */
export interface Prim {
path: PrimPath
/**
 * world transform, row-major 4 x 4, float64 (USD row-vector convention: translation in 12-14)
 * 
 * @minItems 16
 * @maxItems 16
 */
transform: [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
vertices: number
faces: number
/**
 * closed class-label vocabulary (SemanticsLabelsAPI `class`, FR-004-25)
 */
class: ("terrain" | "bench" | "berm" | "ramp" | "windrow" | "haul_road" | "haul_truck" | "shovel" | "excavator" | "wheel_loader" | "water_truck" | "light_vehicle" | "crusher" | "person" | "boulder")
/**
 * closed part-label vocabulary for articulated sub-parts (FR-004-25)
 */
part?: ("chassis" | "cab" | "dump_body" | "wheel" | "axle" | "track" | "undercarriage" | "house" | "boom" | "stick" | "bucket" | "dipper" | "lift_arm" | "front_frame" | "rear_frame" | "tank" | "spray_bar" | "hopper")
}
