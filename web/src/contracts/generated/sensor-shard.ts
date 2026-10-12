/* Generated from contracts/sensor-shard.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Shard index of st53_sensors and st57_rain_lidar, with the lidar-return, radar-detection and image-index column sets as $defs (DC-013-03, spec 013-sensors).
 */
export type PitStudioSensorShardIndex = {
$schema?: string
schema_version: SchemaVersion
run_id: RunId
stage: ("st53_sensors" | "st57_rain_lidar")
scenario: ("S1" | "S2" | "S3" | "S4a" | "rain")
/**
 * fake: test backend only.
 */
backend: ("ovrtx" | "isaac" | "fake")
/**
 * Per-frame counts of every recorded lidar frame.
 * 
 * @minItems 0
 * @maxItems 20000
 */
frames: LidarFrame[]
/**
 * Every output file with its size and digest.
 * 
 * @minItems 1
 * @maxItems 10000
 */
files: [File, ...(File)[]]
}
/**
 * Contract version (major 1).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * One output file.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "file".
 */
export type File = {
path: Relpath
/**
 * File size (bytes), at most 10 MB.
 */
bytes: number
sha256: Sha256
/**
 * parquet: tables; zarr: Zarr v3 chunk or metadata file; png: LDR image.
 */
format: ("parquet" | "zarr" | "png")
/**
 * Column set or array held by the file.
 */
content: ("lidar-returns" | "radar-detections" | "image-index" | "hdr-color" | "distance" | "semantic" | "ldr-color")
/**
 * Rows of a Parquet file.
 */
rows?: number
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
 * Per-frame counts of one lidar frame (outputs, not performance data).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "lidar_frame".
 */
export interface LidarFrame {
/**
 * Sensor id, unique within one sensor block.
 */
sensor: string
/**
 * Recorded frame index (warm-up frames excluded).
 */
frame: number
/**
 * Beams emitted in the frame.
 */
beams_emitted: number
/**
 * Valid points (flag 0x40) of the clean frame; never 0 (point-count guard).
 */
valid_points: number
/**
 * Parquet shard holding the frame's returns.
 */
file: string
/**
 * Applied rain rate (rain arm only).
 */
rain_rate_mm_h?: number
}
/**
 * One row of the lidar-returns column set (Parquet).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "lidar_return".
 */
export interface LidarReturn {
frame: number
/**
 * Beam index within the frame (input of the beam hash).
 */
beam: number
/**
 * Return index within the beam.
 */
echo: number
/**
 * Sensor-frame x (m).
 */
x_m: number
/**
 * Sensor-frame y (m).
 */
y_m: number
/**
 * Sensor-frame z (m).
 */
z_m: number
/**
 * Range (m).
 */
range_m: number
/**
 * Clean return intensity I0 (normalised 0-1).
 */
intensity: number
/**
 * Renderer flags; 0x40 = valid.
 */
flags: number
/**
 * retro if the non-visual material is retroreflective.
 */
material_class: ("retro" | "diffuse")
/**
 * Scene label of the hit object; 0 = unlabelled.
 */
object_id: number
}
/**
 * One row of the radar-detections column set (Parquet).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "radar_detection".
 */
export interface RadarDetection {
frame: number
/**
 * Sensor-frame x (m).
 */
x_m: number
/**
 * Sensor-frame y (m).
 */
y_m: number
/**
 * Sensor-frame z (m).
 */
z_m: number
/**
 * Radar cross-section (dBsm).
 */
rcs_dbsm: number
/**
 * Radial velocity (m/s), positive = range increasing.
 */
radial_velocity_m_per_s: number
/**
 * Scene label of the object where available.
 */
object_id: (number | null)
}
/**
 * One row of the image-index column set (Parquet).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "image_record".
 */
export interface ImageRecord {
/**
 * Image index.
 */
image: number
/**
 * Sensor id, unique within one sensor block.
 */
sensor: string
/**
 * PNG file or Zarr array of the image.
 */
file: string
width_px: number
height_px: number
/**
 * K[0][0] (px).
 */
fx_px: number
/**
 * K[1][1] (px).
 */
fy_px: number
/**
 * K[0][2] (px).
 */
cx_px: number
/**
 * K[1][2] (px).
 */
cy_px: number
/**
 * World-from-camera pose, 4 x 4 row-major (translation in m).
 * 
 * @minItems 16
 * @maxItems 16
 */
world_from_camera: [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
/**
 * Ground-sampling distance p_x H_agl / f (m), S2 only.
 */
gsd_m?: number
/**
 * Height above ground (m), S2 only.
 */
h_agl_m?: number
}
