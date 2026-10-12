/* Generated from contracts/il-twin.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Web twin bundle written by s60_export: twin parameters, policy asset and golden sequences (DC-014-05, spec 014-robot-learning).
 */
export type PitStudioWebTwinBundle = (TruckTwin | ArmTwin)
/**
 * Contract version (major 1).
 */
export type SchemaVersion = string
export type ArtefactId = string
export type Relpath = string
export type Sha256 = string

/**
 * IL-1 truck twin bundle.
 */
export interface TruckTwin {
$schema?: string
schema_version: SchemaVersion
label: "sim-to-sim"
disclaimer: "simulation only — compared with a classical controller on the same simulator; no field claim"
policy_asset: PolicyAsset
/**
 * Isaac Lab rollouts shown as REPLAY and used as the fallback.
 */
replay: string
goldens: Goldens
policy: "IL-1"
twin: "dynamic-bicycle"
observation_size: 63
action_size: 2
/**
 * Dynamic-bicycle twin parameters (FR-014-40).
 */
parameters: {
/**
 * Machine parameter file the values were mapped from.
 */
machine: string
/**
 * Empty mass (kg).
 */
mass_kg: number
/**
 * Rated payload (kg).
 */
rated_payload_kg: number
/**
 * Yaw inertia (kg m2).
 */
yaw_inertia_kg_m2: number
/**
 * CG to front axle (m).
 */
cg_to_front_axle_m: number
/**
 * CG to rear axle (m).
 */
cg_to_rear_axle_m: number
/**
 * Front cornering stiffness (N/rad).
 */
cornering_stiffness_front_n_per_rad: number
/**
 * Rear cornering stiffness (N/rad).
 */
cornering_stiffness_rear_n_per_rad: number
/**
 * Maximum steering angle (deg).
 */
max_steer_deg: number
/**
 * Maximum steering rate (deg/s).
 */
max_steer_rate_deg_per_s: number
/**
 * Rimpull and retarder envelope samples by speed (increasing speed is a checker rule).
 * 
 * @minItems 2
 * @maxItems 64
 * 
 * Items: Envelope sample.
 */
envelope: [{
speed_m_per_s: number
rimpull_n: number
retarder_n: number
}, {
speed_m_per_s: number
rimpull_n: number
retarder_n: number
}, ...({
speed_m_per_s: number
rimpull_n: number
retarder_n: number
})[]]
/**
 * Semi-implicit Euler step (s).
 */
dt_s: 0.01
/**
 * Kinematic-bicycle switch speed (m/s).
 */
kinematic_below_m_per_s: 1
/**
 * Physics substeps per animation frame.
 */
substeps: 5
}
/**
 * Training ranges the panel clamps visitor inputs to.
 */
input_ranges: {
/**
 * Payload fraction clamp range [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
payload_fraction: [number, number]
/**
 * Light-vehicle speed clamp range (km/h) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
light_vehicle_speed_km_h: [number, number]
}
}
/**
 * Exported ONNX policy.
 */
export interface PolicyAsset {
id: ArtefactId
path: Relpath
sha256: Sha256
/**
 * ONNX size (bytes), below 1 MB.
 */
bytes: number
}
/**
 * Golden sequences from the Python reference twin (parity).
 */
export interface Goldens {
path: Relpath
sha256: Sha256
bytes: number
/**
 * Golden action sequences.
 */
sequences: number
/**
 * Steps per golden sequence.
 */
steps: 2000
/**
 * Closed-loop steps checked against ONNX Runtime CPU.
 */
policy_check_steps: 200
}
/**
 * IL-2 excavator twin bundle.
 */
export interface ArmTwin {
$schema?: string
schema_version: SchemaVersion
label: "sim-to-sim"
disclaimer: "simulation only — compared with a classical controller on the same simulator; no field claim"
policy_asset: PolicyAsset
/**
 * Isaac Lab rollouts shown as REPLAY and used as the fallback.
 */
replay: string
goldens: Goldens
policy: "IL-2"
twin: "planar-arm"
observation_size: 46
action_size: 4
/**
 * Planar arm twin parameters, swing fixed (FR-014-41).
 */
parameters: {
/**
 * Machine parameter file the values were mapped from.
 */
machine: string
/**
 * Boom pivot (x, z) (m).
 * 
 * @minItems 2
 * @maxItems 2
 */
boom_pivot_m: [number, number]
links: {
boom: {
/**
 * Link length (m).
 */
length_m: number
}
stick: {
/**
 * Link length (m).
 */
length_m: number
}
bucket: {
/**
 * Link length (m).
 */
length_m: number
}
}
joints: {
boom: Joint
stick: Joint
bucket: Joint
}
/**
 * Bucket width w (m).
 */
bucket_width_m: number
/**
 * Rated heaped volume V_h (m3).
 */
heaped_volume_m3: number
/**
 * Fill cap as a multiple of V_h.
 */
fill_cap: 1.15
gravity_m_per_s2: 9.81
/**
 * Twin step (s).
 */
dt_s: number
}
/**
 * Training ranges the panel clamps visitor inputs to.
 */
input_ranges: {
/**
 * Cohesion clamp range (kPa) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
cohesion_kpa: [number, number]
/**
 * Friction-angle clamp range (deg) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
friction_angle_deg: [number, number]
}
}
/**
 * Revolute joint.
 */
export interface Joint {
/**
 * Lower joint limit (deg); lower < upper is a checker rule.
 */
lower_deg: number
/**
 * Upper joint limit (deg).
 */
upper_deg: number
/**
 * Torque limit tau_max (N m), > 0.
 */
torque_max_n_m: number
/**
 * Maximum joint velocity (deg/s), > 0.
 */
velocity_max_deg_per_s: number
}
