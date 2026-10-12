/* Generated from contracts/des-trace.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "header".
 */
export type Header = {
scenario_id: Slug
bundle_sha256: Sha256
seed: number
dispatcher: ("fixed" | "nearest" | "sptf" | "sq" | "random" | "min-idle" | "lp" | "ppo" | "attention")
variate_profile: ("engine" | "exponential" | "deterministic")
mode: ("fast" | "traffic")
horizon_s: number
kpi_window: KpiWindow
engine: Engine
variates: {
generator: "philox4x64-10"
key_hash: "fnv-1a-64"
}
producer: ("python-reference" | "typescript-twin")
lp?: LpStatus
policy?: PolicyRef
synthetic: true
honesty: Honesty
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "semver".
 */
export type Semver = string
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "lp_status".
 */
export type LpStatus = {
status: ("optimal" | "infeasible" | "unbounded" | "invalid-input")
fallback: ("none" | "sptf")
}

/**
 * Event trace, cyclelog and scalar results of one shift, written by the haulage adapter (DC-007-02, spec 007-haulage-dispatch).
 */
export interface HaulageDESEventTrace {
$schema?: string
schema_version: SchemaVersion
header: Header
/**
 * @maxItems 2000000
 */
events: Event[]
/**
 * @maxItems 2000000
 */
cyclelog: CyclelogRow[]
results: Results
}
export interface KpiWindow {
warmup_s: number
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "engine".
 */
export interface Engine {
package: "minehaulsim"
version: Semver
pin_sha256: Sha256
}
export interface PolicyRef {
artefact_id: string
onnx_sha256: string
layout_version: 1
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "honesty".
 */
export interface Honesty {
label: "calibrated synthetic — not validated against real data"
bias_note: "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; no real haul telemetry exists to correct it."
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "event".
 */
export interface Event {
t_s: number
seq: number
kind: ("arrive-loader" | "load-end" | "depart-loaded" | "arrive-dump" | "dump-end" | "dispatch" | "loader-repair-end" | "segment-exit" | "junction-cross-end" | "zone-probe" | "bin-dump" | "lhd-start" | "lhd-dig" | "lhd-to-tip" | "lhd-at-tip" | "lhd-after-tip")
truck: (number | null)
node: (number | null)
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "cyclelog_row".
 */
export interface CyclelogRow {
t_s: number
truck: number
/**
 * Node id of the road network.
 */
node: number
event: ("load" | "haul" | "dump" | "return")
payload_t: number
}
/**
 * This interface was referenced by `HaulageDESEventTrace`'s JSON-Schema
 * via the `definition` "results".
 */
export interface Results {
tonnes_t: number
cycles: number
truck_wait_s: number
/**
 * @maxItems 64
 */
loader_wait_s: {
/**
 * Node id of the road network.
 */
loader: number
wait_s: number
}[]
events_executed: number
downtime: ({
/**
 * @maxItems 400
 */
truck_s: {
truck: number
downtime_s: number
}[]
/**
 * @maxItems 64
 */
loader_s: {
/**
 * Node id of the road network.
 */
loader: number
downtime_s: number
}[]
} | null)
}
