/* Generated from contracts/web-cloud-shard.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Contract version (major 1).
 * 
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * Header of a quantised web point-cloud shard written by s60_export for the replay viewer (DC-013-04, spec 013-sensors).
 */
export interface PitStudioWebPointCloudShardHeader {
$schema?: string
schema_version: SchemaVersion
/**
 * Sensor frame the shard was converted from.
 */
source: {
run_id: RunId
scenario: ("S1" | "S4a" | "rain")
/**
 * Sensor id, unique within one sensor block.
 */
sensor: string
frame: number
}
/**
 * Points in the payload (8 bytes each).
 */
points: number
quantisation: Quantisation
/**
 * Fixed payload layout.
 */
encoding: {
position: "uint16"
intensity: "uint8"
class: "uint8"
byte_order: "little"
/**
 * x[], y[], z[], intensity[], class[] in this order.
 */
layout: "planar"
}
/**
 * Linear map of the uint8 intensity channel to its quantity.
 */
intensity_map: {
quantity: ("lidar-intensity" | "radar-rcs-dbsm" | "radar-radial-velocity-m-per-s")
/**
 * Value of uint8 code 0.
 */
low: number
/**
 * Value of uint8 code 255.
 */
high: number
}
classes: Classes
payload: Payload
}
/**
 * Dequantised coordinate = offset_m + scale_m * q, q the uint16 value.
 * 
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "quantisation".
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
 * Class code (uint8, decimal string) to label.
 * 
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "classes".
 */
export interface Classes {
[k: string]: Slug | undefined
}
/**
 * Binary payload of a web shard.
 * 
 * This interface was referenced by `PitStudioWebPointCloudShardHeader`'s JSON-Schema
 * via the `definition` "payload".
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
sha256: Sha256
}
