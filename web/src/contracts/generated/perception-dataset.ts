/* Generated from contracts/perception-dataset.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One dataset-index record per synthetic image (one JSON Lines line of the index) written by st55_sdg and the crusher handoff (DC-009-01, spec 009-perception).
 */
export type PerceptionDatasetIndexRecord = {
record_id: ArtefactId
synthetic: true
family: ("pit" | "crusher")
arm: ("structured" | "unstructured")
split: ("train" | "validation" | "test")
scenario_seed: Seed
layout_id: ArtefactId
image: ImageFile
coco: File
coco_image_id: number
semantic_mask: MaskFile
instance_mask?: MaskFile
depth: DepthFile
intrinsics: Intrinsics
frame_state?: File
instance_source: ("replicator" | "connected-components")
dr: (DrStructured | DrUnstructured)
licence: Licence
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "seed".
 */
export type Seed = number
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
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "size_bytes".
 */
export type SizeBytes = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "class_name".
 */
export type ClassName = ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "image_file".
 */
export interface ImageFile {
path: Relpath
sha256: Sha256
size_bytes: SizeBytes
width_px: number
height_px: number
format: "png"
colour_space: "srgb"
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "file".
 */
export interface File {
path: Relpath
sha256: Sha256
size_bytes: SizeBytes
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "mask_file".
 */
export interface MaskFile {
path: Relpath
sha256: Sha256
size_bytes: SizeBytes
width_px: number
height_px: number
format: "png"
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "depth_file".
 */
export interface DepthFile {
path: Relpath
sha256: Sha256
size_bytes: SizeBytes
width_px: number
height_px: number
format: "npy"
dtype: "float32"
unit: "m"
quantity: ("distance-to-image-plane" | "distance-to-camera")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "intrinsics".
 */
export interface Intrinsics {
model: "pinhole"
fx_px: number
fy_px: number
cx_px: number
cy_px: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dr_structured".
 */
export interface DrStructured {
sun_utc: UtcTimestamp
sun_elevation_deg: number
sun_azimuth_deg: number
dust_extinction_per_km: number
/**
 * @maxItems 1024
 */
wet_segments: WetSegment[]
/**
 * @minItems 1
 * @maxItems 64
 */
rock_texture_ids: [ArtefactId, ...(ArtefactId)[]]
/**
 * @maxItems 512
 */
placements: Placement[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "wet_segment".
 */
export interface WetSegment {
segment_id: ArtefactId
wet: boolean
minutes_since_watering?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "placement".
 */
export interface Placement {
class: ClassName
x_m: number
y_m: number
z_m: number
yaw_deg: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dr_unstructured".
 */
export interface DrUnstructured {
/**
 * @minItems 1
 * @maxItems 256
 */
texture_ids: [ArtefactId, ...(ArtefactId)[]]
light_intensity_factor: number
colour_temperature_k: number
sun_elevation_deg: number
sun_azimuth_deg: number
distractor_count: number
/**
 * @maxItems 512
 */
placements: Placement[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "licence".
 */
export interface Licence {
spdx: "CC-BY-4.0"
licence_class: "own"
}
