/* Generated from contracts/frame-manifest.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "tool_id".
 */
export type ToolId = string
/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `FrameManifest`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string

/**
 * Lossless PNG frame sequence handed by a render or replay stage to st56_encode (DC-006-01, spec 006-media-telemetry).
 */
export interface FrameManifest {
$schema?: string
kind: "frame-manifest"
schema_version: SchemaVersion
/**
 * clip name; outputs are <clip>.av1.mp4, <clip>.h264.mp4 and <clip>.webp (FR-006-13)
 */
clip: string
run_id?: RunId
producer: {
tool: ToolId
stage: StageKey
}
/**
 * performance class of the producer tool; local-only producers' timings never appear downstream (FR-006-14)
 */
performance: ("public" | "local-only")
/**
 * source frame rate (FR-006-12)
 */
fps: (24 | 25 | 30 | 50 | 60)
/**
 * frame count; at least 2 (FR-006-12); at most 10 minutes at 60 fps
 */
frames: number
width: number
height: number
bit_depth: (8 | 16)
/**
 * transfer and primaries of the RGB frames
 */
colour_space: ("srgb" | "bt709")
format: "png"
/**
 * folder of the frames inside the stage's input folder
 */
directory?: string
/**
 * printf-style frame file name, e.g. frame_%05d.png; never a path
 */
frame_pattern: string
first_index: number
/**
 * SHA-256 of the ordered list of per-frame SHA-256 digests (P-006-06)
 */
source_frames_sha256: string
/**
 * per-frame digests in frame order
 * 
 * @maxItems 36000
 */
frame_sha256?: Sha256[]
}
/**
 * stage id plus optional variant
 */
export interface StageKey {
id: ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
variant?: string
}
