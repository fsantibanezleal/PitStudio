/* Generated from contracts/haul-scenario.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Scenario bundle read by the haulage adapter, the TypeScript twin and the vectorised environment (DC-007-01, spec 007-haulage-dispatch).
 */
export type HaulageScenarioBundle = {
$schema?: string
schema_version: SchemaVersion
id: Slug
description?: string
/**
 * Bundle offered to the live lane (fleet <= 40 trucks).
 */
live: boolean
mode: ("fast" | "traffic")
horizon_s: number
kpi_window: KpiWindow
network: Network
equipment: Equipment
/**
 * @minItems 1
 * @maxItems 400
 */
fleet: [Truck, ...(Truck)[]]
/**
 * @minItems 1
 * @maxItems 64
 */
loaders: [Loader, ...(Loader)[]]
/**
 * Dump node ids; the first is the default.
 * 
 * @minItems 1
 * @maxItems 32
 */
dumps: [NodeId, ...(NodeId)[]]
dispatcher: Dispatcher
variate_profile: VariateProfile
/**
 * @maxItems 32
 */
quantile_tables: QuantileTable[]
engine_constants: EngineConstants
failures: (Failures | null)
cost_rates?: CostRates
reference_only?: ReferenceOnly
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * Node id of the road network.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "node_id".
 */
export type NodeId = number
/**
 * World position (x, y, z) in metres.
 * 
 * @minItems 3
 * @maxItems 3
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "point3_m".
 */
export type Point3M = [number, number, number]
/**
 * Truck class of the pinned reference-engine catalog.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "truck_class_name".
 */
export type TruckClassName = ("CAT_777G" | "CAT_785D" | "CAT_793F" | "UG_TRUCK_50" | "UG_TRUCK_63")
/**
 * Loader class of the pinned reference-engine catalog.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "loader_class_name".
 */
export type LoaderClassName = ("SHOVEL_25" | "SHOVEL_45" | "WHEEL_LOADER_18" | "CHUTE" | "LHD_14_LOADING" | "LHD_18_LOADING")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dispatcher".
 */
export type Dispatcher = {
id: DispatcherId
lp?: LpConfig
policy?: PolicyRef
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dispatcher_id".
 */
export type DispatcherId = ("fixed" | "nearest" | "sptf" | "sq" | "random" | "min-idle" | "lp" | "ppo" | "attention")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "variate_profile".
 */
export type VariateProfile = ("engine" | "exponential" | "deterministic")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "quantile_table".
 */
export type QuantileTable = {
family: ("uniform" | "normal" | "exponential" | "lognormal-unit-mean")
sigma?: number
bins: 4096
encoding: "float64-le-base64"
/**
 * 4097 knots (float64, little-endian), base64.
 */
knots_f64le_b64: string
knots_sha256: Sha256
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "kpi_window".
 */
export interface KpiWindow {
warmup_s: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "network".
 */
export interface Network {
/**
 * @minItems 2
 * @maxItems 10000
 */
nodes: [Node, Node, ...(Node)[]]
/**
 * @minItems 1
 * @maxItems 10000
 */
segments: [Segment, ...(Segment)[]]
/**
 * @maxItems 256
 */
zones: Zone[]
/**
 * @maxItems 1024
 */
junctions: Junction[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "node".
 */
export interface Node {
id: NodeId
kind: ("face" | "dump" | "crusher" | "junction" | "portal" | "bay" | "chute" | "bin" | "waypoint")
pos_m: Point3M
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "segment".
 */
export interface Segment {
id: number
a: NodeId
b: NodeId
/**
 * @minItems 2
 * @maxItems 512
 */
polyline_m: [Point3M, Point3M, ...(Point3M)[]]
length_m: number
/**
 * Signed grade in the a -> b direction (%).
 */
grade_pct: number
width_class: (1 | 2)
one_way: boolean
speed_limit_kmh: number
rolling_resistance_pct: number
zone_id: (number | null)
single_lane_op: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "zone".
 */
export interface Zone {
id: number
/**
 * @minItems 1
 * @maxItems 256
 */
segment_ids: [number, ...(number)[]]
policy: ("lockout" | "loaded_priority" | "group_batching")
max_in_zone: number
batch_k: number
max_hold_s: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "junction".
 */
export interface Junction {
node: NodeId
capacity: number
cross_s: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "equipment".
 */
export interface Equipment {
/**
 * @minItems 1
 * @maxItems 8
 */
truck_classes: [TruckClass]|[TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass, TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass]|[TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass, TruckClass]
/**
 * @minItems 1
 * @maxItems 8
 */
loader_classes: [LoaderClass]|[LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass]|[LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass, LoaderClass]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "truck_class".
 */
export interface TruckClass {
name: TruckClassName
kind: ("rigid" | "articulated-ug")
payload_mean_t: number
payload_sd_t: number
empty_t: number
width_class: (1 | 2)
power_kw: number
max_speed_kmh: number
/**
 * @minItems 2
 * @maxItems 32
 */
rimpull_kn: [CurvePoint, CurvePoint, ...(CurvePoint)[]]
/**
 * @minItems 2
 * @maxItems 32
 */
retarder_kn: [CurvePoint, CurvePoint, ...(CurvePoint)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "curve_point".
 */
export interface CurvePoint {
speed_kmh: number
force_kn: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "loader_class".
 */
export interface LoaderClass {
name: LoaderClassName
pass_t: number
pass_time_s: number
time_cv: number
spot_time_s: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "truck".
 */
export interface Truck {
id: number
truck_class: TruckClassName
start_loader: NodeId
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "loader".
 */
export interface Loader {
node: NodeId
loader_class: LoaderClassName
n_spots: number
/**
 * Declared destination dump; absent = the first dump.
 */
destination_dump?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "lp_config".
 */
export interface LpConfig {
/**
 * @maxItems 16
 */
blend_floors: []|[BlendFloor]|[BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]|[BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor, BlendFloor]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "blend_floor".
 */
export interface BlendFloor {
/**
 * @minItems 1
 * @maxItems 64
 */
terms: [{
loader: NodeId
coef: number
}, ...({
loader: NodeId
coef: number
})[]]
min: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "policy_ref".
 */
export interface PolicyRef {
artefact_id: ArtefactId
onnx_sha256: Sha256
layout_version: 1
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "engine_constants".
 */
export interface EngineConstants {
stagger_window_s: number
dump_mean_s: number
dump_cv: number
closure_retry_s: number
headway_m: number
headway_s: number
payload_min_frac_of_mean: number
payload_max_t: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "failures".
 */
export interface Failures {
truck_mtbf_h: number
truck_repair_mean_s: number
truck_repair_cv: number
loader_mtbf_h: number
loader_repair_mean_s: number
loader_repair_cv: number
/**
 * @maxItems 256
 */
closures: Closure[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "closure".
 */
export interface Closure {
start_s: number
duration_s: number
/**
 * @minItems 1
 * @maxItems 256
 */
segment_ids: [number, ...(number)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "cost_rates".
 */
export interface CostRates {
truck_per_h: number
loader_per_h: number
currency: string
}
/**
 * Reference-engine features outside the twin's feature set (FR-007-12).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "reference_only".
 */
export interface ReferenceOnly {
/**
 * @maxItems 64
 */
lhds?: {
id: number
lhd_class: ("LHD_14" | "LHD_18")
/**
 * @minItems 1
 * @maxItems 16
 */
drawpoints: [NodeId]|[NodeId, NodeId]|[NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]|[NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId, NodeId]
tip_node: NodeId
pass_id: number
}[]
/**
 * @maxItems 16
 */
ore_passes?: []|[{
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]|[{
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}, {
id: number
chute_node: NodeId
capacity_t: number
}]
shaft_bin?: {
node: NodeId
capacity_t: number
hoist_t_per_h: number
}
planning_overlay?: {
path: Relpath
sha256: Sha256
}
zone_penalty_s?: number
}
