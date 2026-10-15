/* Generated from contracts/sensor-recipe.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * The params block of one st53_sensors or st57_rain_lidar stage, one renderer session (DC-013-01, spec 013-sensors).
 */
export type PitStudioSensorRecipeBlock = {
/**
 * Scenario rendered by this block (one renderer session).
 */
scenario: ("S1" | "S2" | "S3" | "S4a" | "rain")
/**
 * Sensor backend: ovrtx for S1-S4a, isaac for the rain arm.
 */
backend: ("ovrtx" | "isaac")
/**
 * Pose trajectory file (a declared stage input).
 */
poses: string
/**
 * Sensors of the session.
 * 
 * @minItems 1
 * @maxItems 8
 */
sensors: [(Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]|[(Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar), (Lidar | Camera | Radar)]
dust?: Dust
metrics?: Metrics
exposure?: Exposure
haze?: Haze
/**
 * Rain rates (mm/h); default 0, 2, 10, 50.
 * 
 * @minItems 1
 * @maxItems 8
 */
rain_rates_mm_h?: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]
}
/**
 * Sensor id, unique within one sensor block.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sensor_id".
 */
export type SensorId = string
/**
 * Lidar scan pattern.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "scan_type".
 */
export type ScanType = ("rotary" | "solid-state")
/**
 * Elevation fan [e_min, e_max] (deg), hard limit of +/-45 deg; e_min < e_max is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "elevation_fan_deg".
 */
export type ElevationFanDeg = [number, number]
/**
 * Azimuth fan [a_min, a_max] (deg); a_min < a_max is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "azimuth_fan_deg".
 */
export type AzimuthFanDeg = [number, number]
/**
 * Mount position x, y, z in the platform frame (m).
 * 
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "mount_position_m".
 */
export type MountPositionM = [number, number, number]
/**
 * Mount rotation about x, y, z (deg).
 * 
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "mount_rotation_deg".
 */
export type MountRotationDeg = [number, number, number]
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string

/**
 * Generic lidar authored from datasheet-style parameters (S1 and the rain arm); no vendor profile.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "lidar".
 */
export interface Lidar {
kind: "lidar"
id: SensorId
scan_type: ScanType
/**
 * Laser channels (beams per firing column).
 */
channels: number
elevation_fan_deg: ElevationFanDeg
azimuth_fan_deg: AzimuthFanDeg
/**
 * Azimuth step between firing columns (deg).
 */
horizontal_resolution_deg: number
/**
 * Minimum range (m).
 */
min_range_m: number
/**
 * Maximum range (m); min_range_m < max_range_m is a checker rule.
 */
max_range_m: number
/**
 * Gaussian range accuracy (m); the renderer's rangeAccuracyM.
 */
range_accuracy_m: number
/**
 * Returns per beam (multi-echo); the renderer's maxReturns.
 */
max_returns: number
/**
 * Scan rate (Hz).
 */
frame_rate_hz?: number
mount_position_m: MountPositionM
mount_rotation_deg: MountRotationDeg
}
/**
 * Ideal pinhole camera (S2 drone survey, S3 crusher camera).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "camera".
 */
export interface Camera {
kind: "camera"
id: SensorId
/**
 * Image width (px), at most 1920.
 */
width_px: number
/**
 * Image height (px), at most 1080.
 */
height_px: number
/**
 * Focal length f (m).
 */
focal_length_m: number
/**
 * Pixel pitch p_x (m).
 */
pixel_pitch_m: number
/**
 * Principal point [c_x, c_y] (px).
 * 
 * @minItems 2
 * @maxItems 2
 */
principal_point_px: [number, number]
/**
 * Camera render mode.
 */
render_mode: ("realtime-pathtracing" | "pathtracing" | "minimal")
/**
 * Render products of the camera.
 * 
 * @minItems 1
 * @maxItems 5
 */
outputs: [("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation")]|[("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation")]|[("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation")]|[("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation")]|[("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation"), ("LdrColor" | "HdrColor" | "DistanceToCameraSD" | "DistanceToImagePlaneSD" | "SemanticSegmentation")]
mount_position_m: MountPositionM
mount_rotation_deg: MountRotationDeg
}
/**
 * 77 GHz-class proximity radar (S4a).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "radar".
 */
export interface Radar {
kind: "radar"
id: SensorId
/**
 * Carrier wavelength (m): 3.70-3.95 mm (76-81 GHz).
 */
wavelength_m: number
/**
 * Motion BVH enabled (required for Doppler).
 */
motion_bvh: true
/**
 * Range resolution (m).
 */
range_resolution_m: number
/**
 * Radial-velocity resolution (m/s); the renderer's velResMps.
 */
velocity_resolution_m_per_s: number
/**
 * Boresight azimuth resolution (deg).
 */
azimuth_resolution_deg: number
/**
 * Boresight elevation resolution (deg).
 */
elevation_resolution_deg: number
/**
 * Maximum range (m).
 */
max_range_m: number
/**
 * Frame rate (Hz).
 */
frame_rate_hz?: number
mount_position_m: MountPositionM
mount_rotation_deg: MountRotationDeg
}
/**
 * Dust post-model settings read by s05_synthesize (S1).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dust".
 */
export interface Dust {
/**
 * One-way transmittance levels T1 of the uniform-layer sweep (pre-registered grid 1.0 ... 0.02).
 * 
 * @minItems 1
 * @maxItems 16
 */
transmittance_grid: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
/**
 * Sample spacing of the extinction profile along a beam (m), at most 0.5.
 */
beta_spacing_m: number
/**
 * Display intensity of injected dust returns (normalised 0-1; no physical claim).
 */
dust_return_intensity: number
/**
 * C3 extinction fields (declared stage inputs) for the field-driven runs.
 * 
 * @minItems 0
 * @maxItems 16
 */
extinction_fields?: []|[Relpath]|[Relpath, Relpath]|[Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]|[Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath, Relpath]
}
/**
 * S1 metric settings (FR-013-36).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "metrics".
 */
export interface Metrics {
/**
 * Target points needed for a detection (default 3).
 */
k_min: number
/**
 * Range-bin width (m), default 5.
 */
range_bin_m: number
/**
 * Truck speeds for the TTC margin (km/h), default 30, 40, 50.
 * 
 * @minItems 1
 * @maxItems 8
 */
speeds_km_h: [number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]
/**
 * Target ids as labelled in the scene.
 * 
 * @minItems 1
 * @maxItems 16
 */
targets: [Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
}
/**
 * S2 exposure and noise post-model settings (FR-013-18).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "exposure".
 */
export interface Exposure {
/**
 * Exposure time t_e (s).
 */
exposure_time_s: number
/**
 * Aperture f-number N (-).
 */
f_number: number
/**
 * Lumped signal constant kappa (electrons per W sr^-1 m^-2 s).
 */
kappa_e_m2_sr_per_w_s: number
/**
 * Conversion gain G (DN per electron).
 */
gain_dn_per_e: number
/**
 * Read noise sigma_read (electrons).
 */
read_noise_e: number
/**
 * Saturation level DN_max.
 */
dn_max: number
/**
 * Apply natural cos^4 vignetting.
 */
vignetting: boolean
}
/**
 * S3 haze and box post-model settings (FR-013-16, FR-013-17).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "haze".
 */
export interface Haze {
/**
 * Airlight A, linear RGB.
 * 
 * @minItems 3
 * @maxItems 3
 */
airlight_rgb: [number, number, number]
/**
 * Minimum semantic-component area for a box (px), default 16.
 */
min_box_area_px: number
/**
 * C3 extinction field (a declared stage input).
 */
extinction_field?: string
}
