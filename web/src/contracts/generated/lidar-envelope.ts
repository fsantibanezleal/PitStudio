/* Generated from contracts/lidar-envelope.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Contract version (major 1).
 * 
 * This interface was referenced by `PitStudioLidarEnvelope`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioLidarEnvelope`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * One probed lidar configuration.
 * 
 * This interface was referenced by `PitStudioLidarEnvelope`'s JSON-Schema
 * via the `definition` "configuration".
 */
export type Configuration = {
/**
 * Lidar scan pattern.
 */
scan_type: ("rotary" | "solid-state")
elevation_fan_deg: ElevationFanDeg
azimuth_fan_deg: AzimuthFanDeg
mount_rotation_deg: MountRotationDeg
/**
 * pass: more than 0 valid points on the probe scene.
 */
status: ("pass" | "fail")
/**
 * Valid points of the probe frame (a count, not performance data).
 */
valid_points: number
}
/**
 * Elevation fan [e_min, e_max] (deg), hard limit of +/-45 deg; e_min < e_max is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
export type ElevationFanDeg = [number, number]
/**
 * Azimuth fan [a_min, a_max] (deg); a_min < a_max is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
export type AzimuthFanDeg = [number, number]
/**
 * Mount rotation about x, y, z (deg).
 * 
 * @minItems 3
 * @maxItems 3
 */
export type MountRotationDeg = [number, number, number]
/**
 * This interface was referenced by `PitStudioLidarEnvelope`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string

/**
 * studio/rtx/lidar-envelope.json, written by the ovrtx probe and read by the st53_sensors guard (DC-013-02, spec 013-sensors).
 */
export interface PitStudioLidarEnvelope {
$schema?: string
schema_version: SchemaVersion
/**
 * When the probe wrote the file (UTC).
 */
generated: string
/**
 * Versions read from studio/rtx/uv.lock.
 */
versions: {
ovrtx: Version
ovstage: Version
}
/**
 * Probe scene: a ground plane and a 2 m cube at 20 m.
 */
probe_scene: {
cube_edge_m: 2
cube_range_m: 20
}
/**
 * Every lidar configuration referenced by the committed recipes.
 * 
 * @minItems 1
 * @maxItems 256
 */
configurations: [Configuration, ...(Configuration)[]]
}
