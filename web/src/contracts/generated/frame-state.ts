/* Generated from contracts/frame-state.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "location".
 */
export type Location = ("haul_road" | "bench" | "loading_area")
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "condition".
 */
export type Condition = ("day" | "night" | "dust" | "rain")
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "vec3_m".
 */
export type Vec3M = [CoordinateM, CoordinateM, CoordinateM]
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "coordinate_m".
 */
export type CoordinateM = number
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "prim_id".
 */
export type PrimId = string
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "object_class".
 */
export type ObjectClass = ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")
/**
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "vec2_m".
 */
export type Vec2M = [CoordinateM, CoordinateM]
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "visible_px".
 */
export type VisiblePx = number

/**
 * Per-frame scene state written by st55_sdg: transforms in metres, classes, footprints, visible pixels, depth and dust-field references, conditions (DC-015-01, spec 015-vlm).
 */
export interface FrameState {
$schema?: string
schema_version: SchemaVersion
frame_id: ArtefactId
run_id: RunId
synthetic: true
case: CaseId
location: Location
condition: Condition
metersPerUnit: number
upAxis: ("Y" | "Z")
image: Image
depth: FileRef
dust_field: (FileRef | null)
terrain: FileRef
camera: Camera
/**
 * @minItems 1
 * @maxItems 1024
 */
objects: [Object, ...(Object)[]]
/**
 * @maxItems 16
 */
bench_edges: []|[BenchEdge]|[BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]|[BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge, BenchEdge]
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "image".
 */
export interface Image {
path: Relpath
sha256: Sha256
width_px: number
height_px: number
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "file_ref".
 */
export interface FileRef {
path: Relpath
sha256: Sha256
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "camera".
 */
export interface Camera {
intrinsics: {
fx_px: number
fy_px: number
cx_px: number
cy_px: number
}
pose: Pose
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "pose".
 */
export interface Pose {
translation_m: Vec3M
/**
 * @minItems 4
 * @maxItems 4
 */
rotation_xyzw: [number, number, number, number]
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "object".
 */
export interface Object {
prim_id: PrimId
class: ObjectClass
asset_id?: ArtefactId
pose: Pose
footprint: Footprint
visible_px: VisiblePx
in_frustum: boolean
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "footprint".
 */
export interface Footprint {
centre_m: Vec2M
/**
 * @minItems 2
 * @maxItems 2
 */
half_extents_m: [number, number]
heading_deg: number
}
/**
 * This interface was referenced by `FrameState`'s JSON-Schema
 * via the `definition` "bench_edge".
 */
export interface BenchEdge {
edge_id: ArtefactId
berm_present: boolean
visible_px: VisiblePx
}
