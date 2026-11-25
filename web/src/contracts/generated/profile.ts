/* Generated from contracts/profile.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Machine profile studio/recipes/_profiles/<id>.yaml read by the runner, with $defs/fake_device for the fake GPU backend's device files (DC-002-01, spec 002-runner).
 */
export type PitStudioMachineProfile = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
id: Slug
os: ("windows" | "linux")
/**
 * @maxItems 16
 */
gpus: []|[Gpu]|[Gpu, Gpu]|[Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]|[Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu, Gpu]
store_default: StoreDefault
cpu_slots: number
/**
 * @minItems 1
 * @maxItems 9
 */
envs_enabled: [Environment]|[Environment, Environment]|[Environment, Environment, Environment]|[Environment, Environment, Environment, Environment]|[Environment, Environment, Environment, Environment, Environment]|[Environment, Environment, Environment, Environment, Environment, Environment]|[Environment, Environment, Environment, Environment, Environment, Environment, Environment]|[Environment, Environment, Environment, Environment, Environment, Environment, Environment, Environment]|[Environment, Environment, Environment, Environment, Environment, Environment, Environment, Environment, Environment]
process_control: ("job-object" | "process-group")
guards: Guards
telemetry_hz: number
keep_awake: boolean
/**
 * store quota per stage id, GiB (2^30 B); absent = no quota
 */
quotas?: {
[k: string]: number | undefined
}
/**
 * pinned executable id -> name of the environment variable holding its path (never the path)
 */
binaries?: {
[k: string]: EnvVar | undefined
}
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * short machine-neutral absolute store root, used only when PITSTUDIO_STORE is unset: a drive-root folder on Windows, a /srv, /data or /scratch folder on Linux (bound to `os` at the root)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "store_default".
 */
export type StoreDefault = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "environment".
 */
export type Environment = ("studio" | "isaac" | "rtx" | "isaaclab" | "kit" | "reason" | "pipeline" | "accel" | "external")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "env_var".
 */
export type EnvVar = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "binary_id".
 */
export type BinaryId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "stage_id".
 */
export type StageId = ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "series_field".
 */
export type SeriesField = ("free_bytes" | "temp_c" | "power_w" | "power_limit_w" | "util_pct" | "sm_clock_mhz" | "clocks_event_mask" | "energy_mj_per_s" | "nvenc_util_pct" | "pcie_replays")
/**
 * [t_s, value]: seconds since the backend started and the value from then on; per-field value ranges and ascending t_s are checked by the fake backend's loader (FR-002-57)
 * 
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "step".
 */
export type Step = [number, number]
/**
 * @minItems 1
 * @maxItems 10000
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "steps".
 */
export type Steps = [Step, ...(Step)[]]

/**
 * nominal device facts for planning; the live (or fake) backend value governs the guards
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "gpu".
 */
export interface Gpu {
index: number
vram_bytes: number
power_class: ("laptop-power-limited" | "desktop" | "server")
}
/**
 * pre-flight guard settings; margins in GiB (2^30 B), floors of FR-002-19 / FR-002-20
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "guards".
 */
export interface Guards {
vram_margin_gib: number
disk_margin_gib: number
max_start_temp_c: number
cooldown_wait_s: number
lock_wait_s: number
}
/**
 * scripted backend answers per field: a constant, or [t_s, value] steps
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fake_series".
 */
export interface FakeSeries {
free_bytes?: (number | Steps)
temp_c?: (number | Steps)
power_w?: (number | Steps)
power_limit_w?: (number | Steps)
util_pct?: (number | Steps)
sm_clock_mhz?: (number | Steps)
clocks_event_mask?: (number | Steps)
energy_mj_per_s?: (number | Steps)
nvenc_util_pct?: (number | Steps)
pcie_replays?: (number | Steps)
}
/**
 * device file of the fake GPU backend (PITSTUDIO_GPU_BACKEND=fake:<file>, FR-002-55); all values finite
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fake_device".
 */
export interface FakeDevice {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
name: string
driver: Driver
vram_total_bytes: number
init_error: boolean
/**
 * @maxItems 10
 */
unsupported?: []|[SeriesField]|[SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]|[SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField, SeriesField]
series: FakeSeries
}
