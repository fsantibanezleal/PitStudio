/* Generated from contracts/il-task.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * The params block of an st60_il_train or st61_il_mpm_eval stage (DC-014-01, spec 014-robot-learning).
 */
export type PitStudioILTaskParameters = (HaulTruckTask | DigTask)
/**
 * IL-2 excavator / IL-3 loader dig task parameters.
 */
export type DigTask = {
policy: ("IL-2" | "IL-3")
task: ("Pit-Excavator-Dig-FEE" | "Pit-Loader-Dig-FEE")
stage: ("st60_il_train" | "st61_il_mpm_eval")
observation_size: 46
action_size: 4
/**
 * Policy rate (Hz).
 */
control_hz: number
/**
 * Observation layout in order; sizes sum to observation_size (checker rule).
 * 
 * @minItems 1
 * @maxItems 16
 * 
 * Items: One observation segment.
 */
observation_layout: [{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]|[{
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}, {
segment: ("joint_positions" | "joint_velocities" | "joint_torques" | "bucket_tip_pose" | "terrain_heights" | "fill_estimate")
size: number
}]
/**
 * Reward-term weights (terms are already signed).
 */
reward_weights: {
[k: string]: number | undefined
}
/**
 * IL-2 / IL-3 soil randomisation within the FR-014-19 limits.
 */
randomisation: {
/**
 * Bulk density (kg/m3) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
bulk_density_kg_m3: [number, number]
/**
 * Cohesion (kPa) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
cohesion_kpa: [number, number]
/**
 * Adhesion c_a as a fraction of c (-) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
adhesion_ratio: [number, number]
/**
 * Friction angle (deg) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
friction_angle_deg: [number, number]
/**
 * Soil-tool friction (deg); upper <= friction-angle lower is a checker rule [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
soil_tool_friction_deg: [number, number]
surcharge_kpa: 0
/**
 * Initial face height noise amplitude (m), at most 0.3.
 */
face_height_noise_m: number
}
seeds: Seeds
training?: Training
/**
 * Budgets (NFR-014-01, NFR-014-02).
 */
budget: {
/**
 * Device-peak VRAM budget (GB), at most 6.
 */
vram_gb: number
/**
 * GPU-time stop limit (h), at most 16 (2 x the upper estimate).
 */
gpu_hours: number
}
/**
 * IL-2 / IL-3 evaluation protocol (FR-014-32, FR-014-35).
 */
evaluation: {
episodes: 100
deterministic_actions: true
time_limit_s: 30
}
mpm?: Mpm
}

/**
 * IL-1 haul truck task parameters.
 */
export interface HaulTruckTask {
policy: "IL-1"
task: "Pit-HaulTruck-Ramp"
/**
 * IL-1 has no MPM tier.
 */
stage: "st60_il_train"
observation_size: 63
action_size: 2
control_hz: 20
/**
 * Observation layout in order; sizes sum to observation_size (checker rule).
 * 
 * @minItems 1
 * @maxItems 16
 * 
 * Items: One observation segment.
 */
observation_layout: [{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]|[{
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}, {
segment: ("speed_yaw_rate_pitch" | "lateral_heading_error" | "path_points" | "payload_fraction" | "ray_ranges" | "lv_relative_position" | "lv_relative_velocity" | "lv_ttc")
size: number
}]
/**
 * Reward-term weights (terms are already signed).
 */
reward_weights: {
[k: string]: number | undefined
}
/**
 * Site speed limit (km/h), default 40.
 */
site_speed_limit_km_h?: number
/**
 * IL-1 domain randomisation within the FR-014-13 limits.
 */
randomisation: {
/**
 * Payload fraction of rated [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
payload_fraction: [number, number]
/**
 * Rolling resistance (%) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
rolling_resistance_pct: [number, number]
/**
 * Dry tyre-road friction (-) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
friction_dry: [number, number]
/**
 * Wet tyre-road friction (-) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
friction_wet: [number, number]
wet_probability: 0.5
/**
 * Actuator delay (control steps) [low, high]; low <= high is a checker rule.
 * 
 * @minItems 2
 * @maxItems 2
 */
actuator_delay_steps: [number, number]
/**
 * Ray noise sigma constant term (m), at most 0.02.
 */
ray_noise_base_m: number
/**
 * Ray noise sigma per metre of range (-), at most 0.01.
 */
ray_noise_per_range: number
/**
 * Speed noise sigma (m/s), at most 0.1.
 */
speed_noise_sd_m_per_s: number
/**
 * Heading noise sigma (deg), at most 0.5.
 */
heading_noise_sd_deg: number
}
seeds: Seeds
training: Training
/**
 * Budgets (NFR-014-01, NFR-014-02).
 */
budget: {
/**
 * Device-peak VRAM budget (GB), at most 5.
 */
vram_gb: number
/**
 * GPU-time stop limit (h), at most 8 (2 x the upper estimate).
 */
gpu_hours: number
}
/**
 * IL-1 evaluation protocol (FR-014-14, FR-014-32).
 */
evaluation: {
episodes: 100
deterministic_actions: true
/**
 * Episodes with 0, 1, 2 and 3 light vehicles.
 */
light_vehicle_mix: [25,25,25,25]
}
}
/**
 * Seed ranges [start, start + count); pairwise disjointness is a checker rule.
 */
export interface Seeds {
/**
 * Training seed range.
 */
train: {
/**
 * Seed (unsigned 32-bit).
 */
start: number
count: number
}
/**
 * Baseline tuning seeds (20).
 */
tune?: {
/**
 * Seed (unsigned 32-bit).
 */
start: number
count: 20
}
/**
 * Evaluation seeds (100).
 */
eval: {
/**
 * Seed (unsigned 32-bit).
 */
start: number
count: 100
}
}
/**
 * rsl_rl PPO settings (FR-014-25).
 */
export interface Training {
/**
 * Parallel environments (from the bench measurement within the VRAM budget).
 */
num_envs: number
/**
 * PPO iterations.
 */
iterations: number
/**
 * Checkpoint cadence (iterations).
 */
checkpoint_every: 100
/**
 * Actor and critic MLP hidden layers.
 */
hidden_units: [256,256]
gamma: 0.99
gae_lambda: 0.95
clip_ratio: 0.2
/**
 * Steps per environment per update.
 */
steps_per_env: 24
}
/**
 * IL-2b MPM evaluation tier (FR-014-22).
 */
export interface Mpm {
/**
 * Paired MPM episodes n.
 */
episodes: number
/**
 * MPM environments.
 */
envs: number
/**
 * Dry-sand material of the DEM calibration artefact (spec 011).
 */
material: string
}
