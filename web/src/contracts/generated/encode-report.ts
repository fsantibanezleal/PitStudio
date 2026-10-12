/* Generated from contracts/encode-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "clip".
 */
export type Clip = {
clip: Slug
source_frames_sha256: Sha256
frames: number
fps: (24 | 25 | 30 | 50 | 60)
variants: Variants
/**
 * bytes(AV1) + bytes(H.264) (FR-006-03, NFR-000-07)
 */
pair_bytes: number
poster: Poster
relaxation: (Relaxation | null)
}
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * a relaxation declared by the recipe for this clip (FR-006-04)
 * 
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "relaxation".
 */
export type Relaxation = {
kind: ("lower-target" | "shorter-duration" | "crop")
reason: string
vmaf_mean_min?: number
vmaf_p5_min?: number
}

/**
 * Per-clip VMAF search trace, chosen settings, budgets and relaxation written by st56_encode (DC-006-02, spec 006-media-telemetry).
 */
export interface EncodeReport {
$schema?: string
kind: "encode-report"
schema_version: SchemaVersion
run_id: RunId
stage: (StageKey & {
id?: "st56_encode"
})
vmaf_model: "vmaf_v0.6.1"
/**
 * targets of FR-006-02 and budgets of FR-006-03
 */
targets: {
vmaf_mean_min: 93
vmaf_p5_min: 85
relaxed_vmaf_mean_floor: 80
pair_bytes_max: 25000000
poster_bytes_max: 150000
}
/**
 * @minItems 1
 * @maxItems 32
 */
clips: [Clip, ...(Clip)[]]
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "variants".
 */
export interface Variants {
av1: (EncodeVariant & {
record?: {
codec?: "av1"
width?: 1920
height?: 1080
}
})
h264: (EncodeVariant & {
cq_range?: {
min?: number
max?: number
}
trials?: (Trial & {
cq?: number
})[]
chosen_cq?: number
record?: {
codec?: "h264"
profile?: "high"
width?: 1280
height?: 720
}
})
}
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "encode_variant".
 */
export interface EncodeVariant {
file: Relpath
bytes: number
sha256: Sha256
cq_range: CqRange
/**
 * the bisection encodes, at most 8 per variant (FR-006-02)
 * 
 * @minItems 1
 * @maxItems 8
 */
trials: [Trial]|[Trial, Trial]|[Trial, Trial, Trial]|[Trial, Trial, Trial, Trial]|[Trial, Trial, Trial, Trial, Trial]|[Trial, Trial, Trial, Trial, Trial, Trial]|[Trial, Trial, Trial, Trial, Trial, Trial, Trial]|[Trial, Trial, Trial, Trial, Trial, Trial, Trial, Trial]
chosen_cq: number
/**
 * the encoder record of the chosen, re-measured setting, identical to the one attached to the stage result
 */
record: (Encoder & {
pix_fmt?: "yuv420p"
vmaf?: {
model?: "vmaf_v0.6.1"
}
})
}
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "cq_range".
 */
export interface CqRange {
min: number
max: number
}
/**
 * one measured encode of the search
 * 
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "trial".
 */
export interface Trial {
/**
 * NVENC constant-quality value (0, the automatic value, is excluded)
 */
cq: number
vmaf_mean: number
/**
 * 5th percentile of per-frame scores (Hyndman-Fan type 7)
 */
vmaf_p5: number
bytes: number
}
/**
 * encoder record of a video artefact (data-model §2.7)
 */
export interface Encoder {
codec: ("av1" | "h264")
profile: string
pix_fmt: string
width: number
height: number
fps: number
frames: number
duration_s: number
bitrate_kbps: number
vmaf: {
mean: number
p5: number
model: string
}
source_frames_sha256: string
encoder: {
ffmpeg_version: string
build_sha256: string
nvenc_api: (string | null)
/**
 * @maxItems 64
 */
args: string[]
}
encode_fps: (number | null)
}
/**
 * This interface was referenced by `EncodeReport`'s JSON-Schema
 * via the `definition` "poster".
 */
export interface Poster {
file: Relpath
sha256: Sha256
bytes: number
/**
 * WebP quality chosen to fit the cap
 */
quality: number
width: 1280
height: 720
/**
 * index of the poster frame in the sequence (poster_frame, default 0)
 */
frame: number
}
