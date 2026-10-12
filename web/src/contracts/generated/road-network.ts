/* Generated from contracts/road-network.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "node_id".
 */
export type NodeId = string
/**
 * [x, y, z] in the site frame, m
 * 
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "position".
 */
export type Position = [number, number, number]
/**
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "edge_id".
 */
export type EdgeId = string

/**
 * Haul-road graph written by st20_pit_design as a closed GeoJSON FeatureCollection subset in the site frame (DC-004-06, spec 004-scene-pipeline).
 */
export interface HaulRoadNetwork {
$schema?: string
type: "FeatureCollection"
schema_version: SchemaVersion
/**
 * coordinates are site-frame metres, not WGS 84 (foreign member)
 */
frame: "site-enu"
site_origin: SiteOrigin
provenance: "design-code"
exit_node: NodeId
/**
 * @minItems 3
 * @maxItems 10000
 */
features: [(Node | Edge), (Node | Edge), (Node | Edge), ...((Node | Edge))[]]
}
/**
 * site origin of the site-local frame (FR-004-02)
 */
export interface SiteOrigin {
/**
 * EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)
 */
epsg: number
easting_m: number
northing_m: number
/**
 * origin elevation z0 in the vertical datum of the inputs, m
 */
z0_m: number
}
/**
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "node".
 */
export interface Node {
type: "Feature"
id: NodeId
geometry: {
type: "Point"
coordinates: Position
}
properties: {
kind: "node"
role: ("exit" | "junction" | "end")
}
}
/**
 * This interface was referenced by `HaulRoadNetwork`'s JSON-Schema
 * via the `definition` "edge".
 */
export interface Edge {
type: "Feature"
id: EdgeId
geometry: {
type: "LineString"
/**
 * @minItems 2
 * @maxItems 20000
 */
coordinates: [Position, Position, ...(Position)[]]
}
properties: {
kind: "edge"
from: NodeId
to: NodeId
class: ("ramp" | "bench-road")
/**
 * 3-D length along the polyline
 */
length_m: number
/**
 * signed: rise from `from` to `to` over horizontal run x 100
 */
grade_mean_pct: number
/**
 * largest absolute grade over <= 1 m samples
 */
grade_max_pct: number
}
}
