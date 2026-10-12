/* Generated from contracts/recipe.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * recipe stage (data-model §3.2); `env` is bound to `id` (§3.3)
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "stage".
 */
export type Stage = {
id: StageId
variant?: Variant
env: Environment
tool: ToolId
entry: ModulePath
/**
 * @maxItems 32
 */
inputs: StageInput[]
params?: Params
resources: Resources
/**
 * @maxItems 16
 */
requires?: []|[Probe]|[Probe, Probe]|[Probe, Probe, Probe]|[Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]|[Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe, Probe]
/**
 * @maxItems 8
 */
binaries?: []|[{
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]|[{
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}, {
id: BinaryId
sha256: Sha256
}]
determinism: Determinism
retry?: {
/**
 * @minItems 1
 * @maxItems 4
 */
oom_fallback: [Params]|[Params, Params]|[Params, Params, Params]|[Params, Params, Params, Params]
}
timeout_s: number
/**
 * @minItems 1
 * @maxItems 64
 */
outputs: [{
path: Relpath
schema: ValidatorId
publish?: boolean
}, ...({
path: Relpath
schema: ValidatorId
publish?: boolean
})[]]
shardable?: {
shard_size: number
total: number
}
}
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "stage_id".
 */
export type StageId = ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "variant".
 */
export type Variant = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "environment".
 */
export type Environment = ("studio" | "isaac" | "rtx" | "isaaclab" | "kit" | "reason" | "pipeline" | "accel" | "external")
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "tool_id".
 */
export type ToolId = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "module_path".
 */
export type ModulePath = string
/**
 * a source (logical id + SHA-256) or an upstream stage; never a path
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "stage_input".
 */
export type StageInput = ({
id: Slug
sha256: Sha256
} | {
stage: StageId
variant?: Variant
output?: Relpath
})
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * a parameter value with at most 3 further level(s) of nesting
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "param_value_3".
 */
export type ParamValue_3 = (ParamValue_0 | ParamValue_2[] | {
[k: string]: ParamValue_2 | undefined
})
/**
 * a scalar parameter value (non-finite numbers are rejected by the loader)
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "param_value_0".
 */
export type ParamValue_0 = (string | number | boolean | null)
/**
 * a parameter value with at most 2 further level(s) of nesting
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "param_value_2".
 */
export type ParamValue_2 = (ParamValue_0 | ParamValue_1[] | {
[k: string]: ParamValue_1 | undefined
})
/**
 * a parameter value with at most 1 further level(s) of nesting
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "param_value_1".
 */
export type ParamValue_1 = (ParamValue_0 | ParamValue_0[] | {
[k: string]: ParamValue_0 | undefined
})
/**
 * estimates in GiB (2^30 B)
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "resources".
 */
export type Resources = {
gpu: ("exclusive" | "nvenc" | "none")
vram_gib_est?: number
disk_gib_est?: number
cpu?: number
}
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "probe".
 */
export type Probe = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "binary_id".
 */
export type BinaryId = string
/**
 * `bitwise` shorthand, or a class object
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "determinism".
 */
export type Determinism = ("bitwise" | {
class: "bitwise"
} | {
class: "statistical"
/**
 * observable -> tolerance
 */
observables: {
[k: string]: {
rtol: number
atol: number
} | undefined
}
} | {
class: "none"
reason: string
})
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "validator_id".
 */
export type ValidatorId = string
/**
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string

/**
 * Runner recipes and the console job request (DC-001-02, spec 001-contracts).
 */
export interface PitStudioRecipe {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
id: Slug
case: (CaseId | "bench")
seed: number
description?: string
/**
 * @minItems 1
 * @maxItems 64
 */
stages: [Stage, ...(Stage)[]]
}
/**
 * effective parameters; nesting depth <= 4 including this object
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "params".
 */
export interface Params {
[k: string]: ParamValue_3 | undefined
}
/**
 * stage id plus optional variant
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "stage_key".
 */
export interface StageKey {
id: StageId
variant?: Variant
}
/**
 * runner recipe (data-model §3.1)
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "recipe".
 */
export interface Recipe {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
id: Slug
case: (CaseId | "bench")
seed: number
description?: string
/**
 * @minItems 1
 * @maxItems 64
 */
stages: [Stage, ...(Stage)[]]
}
/**
 * body of the console's POST /jobs (data-model §3.5); never an inline recipe
 * 
 * This interface was referenced by `PitStudioRecipe`'s JSON-Schema
 * via the `definition` "job_request".
 */
export interface JobRequest {
recipe: Slug
/**
 * @minItems 1
 * @maxItems 64
 */
stages?: [StageKey, ...(StageKey)[]]
force?: boolean
rerun_check?: boolean
profile: Slug
}
