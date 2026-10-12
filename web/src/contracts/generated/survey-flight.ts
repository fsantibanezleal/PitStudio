/* Generated from contracts/survey-flight.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * One rendered drone flight and sensor-noise seed with exact intrinsics, poses and depth (DC-017-05, spec 017-planning-survey).
 */
export interface E2SurveyFlightRecord {
$schema?: string
schema_version: string
synthetic: true
flight: Slug
/**
 * Survey design of FR-017-36; overlap_pct is both the forward and the side overlap.
 */
design: {
gsd_cm_per_px: (2 | 4 | 8)
overlap_pct: (70 | 80)
sun_elevation_deg: (30 | 60)
}
seed: number
camera: Camera
/**
 * @minItems 1
 * @maxItems 20000
 */
images: [Image, ...(Image)[]]
scene: Scene
}
/**
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "camera".
 */
export interface Camera {
model: "pinhole"
distortion: "none"
width_px: number
height_px: number
fx_px: number
fy_px: number
cx_px: number
cy_px: number
}
/**
 * One rendered image with its exact pose and its planar z-depth map (metres).
 * 
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "image".
 */
export interface Image {
name: Relpath
sha256: Sha256
tilt_deg: (-30 | 0 | 30)
/**
 * Camera-to-world pose; camera axes x right, y down, z forward; unit quaternion.
 */
pose: {
/**
 * @minItems 3
 * @maxItems 3
 */
position_m: [number, number, number]
/**
 * @minItems 4
 * @maxItems 4
 */
rotation_wxyz: [number, number, number, number]
}
depth: FileRef
}
/**
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "file_ref".
 */
export interface FileRef {
name: Relpath
sha256: Sha256
}
/**
 * Known-volume scene of FR-017-35 with its exact closed-form volumes.
 * 
 * This interface was referenced by `E2SurveyFlightRecord`'s JSON-Schema
 * via the `definition` "scene".
 */
export interface Scene {
usd: FileRef
exact_surface: {
name: Relpath
sha256: Sha256
cell_m: 0.25
}
base_z_m: number
stockpile: {
shape: "conical-frustum"
/**
 * @minItems 2
 * @maxItems 2
 */
centre_m: [number, number]
radius_bottom_m: number
radius_top_m: number
height_m: number
volume_m3: number
}
cut: {
shape: "trapezoidal-prism"
/**
 * @minItems 2
 * @maxItems 2
 */
centre_m: [number, number]
length_m: number
depth_m: number
width_bottom_m: number
width_top_m: number
volume_m3: number
}
}
