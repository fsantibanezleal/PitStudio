/* Generated from contracts/replay-shard.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Replay shard headers and replay manifests written by st50_physics, s60_export and studio publish (DC-018-03, spec 018-web-cases; also DC-005-04, spec 005-physics).
 */
export type PitStudioReplayShardHeaderAndReplayManifest = (ShardHeader | ReplayManifest)
/**
 * JSON header of one shard or field tile (DC-018-03)
 */
export type ShardHeader = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
document: "replay-shard-header"
schema_version: SchemaVersion
kind: ("pose" | "particle" | "point" | "field")
/**
 * raw16: little-endian 16-bit codes in frame, item, channel order; png16: 16-bit greyscale PNG tile; float32: little-endian Float32 tile
 */
encoding: ("raw16" | "png16" | "float32")
code_type?: CodeType
code_range?: CodeRange
fps: Fps
frames: FrameRange
/**
 * poses, particles, points or cells per frame
 */
items: number
/**
 * @minItems 1
 * @maxItems 16
 */
channels: [Channel]|[Channel, Channel]|[Channel, Channel, Channel]|[Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]|[Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel, Channel]
bbox_m: BboxM
/**
 * tile size in cells (field tiles only)
 */
grid?: {
width: number
height: number
}
payload: Payload
}
export type SchemaVersion = string
/**
 * integer type of the quantised codes; decoding maps the 65,536 codes affinely onto [min, max] of each channel
 */
export type CodeType = ("int16" | "uint16")
/**
 * frames per second
 */
export type Fps = number
export type Channel = ({
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
} & {
name: string
unit: ("m" | "m/s" | "m/s2" | "rad" | "s" | "1" | "ug/m3" | "kg/m3" | "kg/m2" | "Pa")
/**
 * value of the lowest code, in the channel unit
 */
min: number
/**
 * value of the highest code, in the channel unit
 */
max: number
})
export type Sha256 = string
export type Slug = string
export type Version = string

/**
 * smallest and largest code present in the payload; the reader rejects a shard with a code outside it (FR-018-45)
 */
export interface CodeRange {
min: number
max: number
}
export interface FrameRange {
start: number
count: number
}
/**
 * axis-aligned bounding box in metres (x, y, z)
 */
export interface BboxM {
/**
 * @minItems 3
 * @maxItems 3
 */
min: [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
max: [number, number, number]
}
export interface Payload {
/**
 * payload file, relative to the header's folder
 */
path: string
/**
 * payload size; shards and tiles are at most 10 MB (10^7 bytes)
 */
bytes: number
sha256: Sha256
}
/**
 * replay manifest listing the shards of one replay (FR-005-45)
 */
export interface ReplayManifest {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
document: "replay-manifest"
schema_version: SchemaVersion
kind: ("particle" | "pose" | "point")
/**
 * length unit of positions and of the bounding box
 */
units: "m"
bbox_m: BboxM
fps: Fps
/**
 * frame count
 */
frames: number
/**
 * particle (or pose, point) count per frame; one frame of three 16-bit channels fits one shard
 */
items: number
code_type: CodeType
solver: {
name: Slug
version: Version
}
seed: number
/**
 * @minItems 1
 * @maxItems 1000
 */
shards: [ShardEntry, ...(ShardEntry)[]]
}
export interface ShardEntry {
/**
 * shard header JSON, relative to the manifest's folder
 */
header: string
/**
 * shard payload, relative to the manifest's folder
 */
payload: string
bytes: number
/**
 * SHA-256 of the payload bytes
 */
sha256: string
frames: FrameRange
}
