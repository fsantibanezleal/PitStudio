/* Generated from contracts/dust-slider.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Contract version (major 1).
 * 
 * This interface was referenced by `PitStudioBakedDustSliderFrame`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioBakedDustSliderFrame`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string

/**
 * Header of a baked dust-slider frame written by s60_export for the web dust worker (DC-013-05, spec 013-sensors).
 */
export interface PitStudioBakedDustSliderFrame {
$schema?: string
schema_version: SchemaVersion
/**
 * Clean S1 frame that was baked.
 */
source: {
run_id: RunId
/**
 * Sensor id, unique within one sensor block.
 */
sensor: string
frame: number
}
/**
 * Baked returns, at most 150,000.
 */
returns: number
/**
 * Slider levels 0 ... 40.
 */
levels: 41
/**
 * Dust-load multiplier k_j of each level (tau = k_j * tau_unit).
 * 
 * @minItems 41
 * @maxItems 41
 */
k: [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]
/**
 * Optical depth of the reference target at unit dust load (-), > 0.
 */
tau_ref: number
/**
 * Detection-rule constants (FR-013-12).
 */
rule: {
/**
 * Onset optical depth (T1 = 0.725).
 */
tau_on: 0.3216
/**
 * Floor for retroreflective returns (T1 = 0.02).
 */
tau_floor_retro: 3.912
/**
 * Floor for diffuse returns (T1 = 0.06).
 */
tau_floor_diffuse: 2.8134
}
/**
 * Display intensity of dust returns (normalised 0-1).
 */
dust_return_intensity: number
/**
 * uint8 class codes of the payload's class channel.
 */
material_codes: {
retro: number
diffuse: number
dust: number
}
label: "own Beer–Lambert dust model"
quantisation: Quantisation
/**
 * Fixed payload layout (20 bytes per return).
 */
encoding: {
position: "uint16"
/**
 * I0 per return.
 */
intensity: "uint8"
class: "uint8"
/**
 * Optical depth at unit dust load per return.
 */
tau_unit: "float32"
/**
 * Leading edge of the dust cloud per return (m).
 */
r_edge_m: "float32"
/**
 * MurmurHash3 beam value h per return.
 */
hash: "uint32"
byte_order: "little"
/**
 * x[], y[], z[], intensity[], class[], tau_unit[], r_edge_m[], hash[].
 */
layout: "planar"
}
payload: Payload
}
/**
 * Dequantised coordinate = offset_m + scale_m * q, q the uint16 value.
 */
export interface Quantisation {
/**
 * Per-axis offset (m): the minimum of the shard's bounding box.
 * 
 * @minItems 3
 * @maxItems 3
 */
offset_m: [number, number, number]
/**
 * Per-axis scale (m per uint16 step) = extent / 65535; 1 for an axis of zero extent.
 * 
 * @minItems 3
 * @maxItems 3
 */
scale_m: [number, number, number]
}
/**
 * Binary payload of a web shard.
 */
export interface Payload {
/**
 * Binary payload next to the header.
 */
path: string
/**
 * Payload size (bytes), at most 10 MB.
 */
bytes: number
sha256: string
}
