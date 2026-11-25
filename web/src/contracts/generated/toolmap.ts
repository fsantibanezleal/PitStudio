/* Generated from contracts/toolmap.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `StudioToolMapSource`'s JSON-Schema
 * via the `definition` "band_id".
 */
export type BandId = ("scene" | "physics" | "sensors-synthetic-data" | "training" | "acceleration" | "encoding" | "web")
/**
 * This interface was referenced by `StudioToolMapSource`'s JSON-Schema
 * via the `definition` "tool_id".
 */
export type ToolId = string
/**
 * This interface was referenced by `StudioToolMapSource`'s JSON-Schema
 * via the `definition` "artefact_kind".
 */
export type ArtefactKind = ("video" | "image" | "figure" | "point-cloud" | "mesh" | "tiles" | "splat" | "onnx" | "table" | "trace" | "shard" | "field" | "text" | "model-card" | "telemetry" | "usd")

/**
 * Band order, tool order within each band and declared handoff edges of studio/toolmap.yaml (DC-019-02, spec 019-web-studio).
 */
export interface StudioToolMapSource {
$schema?: string
/**
 * @minItems 7
 * @maxItems 7
 */
bands: [Band, Band, Band, Band, Band, Band, Band]
/**
 * @minItems 0
 * @maxItems 128
 */
edges: Edge[]
}
/**
 * One band of the map; tools are listed in drawing order.
 * 
 * This interface was referenced by `StudioToolMapSource`'s JSON-Schema
 * via the `definition` "band".
 */
export interface Band {
id: BandId
/**
 * @minItems 1
 * @maxItems 32
 */
tools: [ToolId, ...(ToolId)[]]
}
/**
 * A declared file handoff from one tool to another, labelled with the artefact kind it carries.
 * 
 * This interface was referenced by `StudioToolMapSource`'s JSON-Schema
 * via the `definition` "edge".
 */
export interface Edge {
from: ToolId
to: ToolId
kind: ArtefactKind
}
