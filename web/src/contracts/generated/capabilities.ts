/* Generated from contracts/capabilities.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PitStudioCapabilityReport`'s JSON-Schema
 * via the `definition` "date".
 */
export type Date = string
/**
 * This interface was referenced by `PitStudioCapabilityReport`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `PitStudioCapabilityReport`'s JSON-Schema
 * via the `definition` "local_only".
 */
export type LocalOnly = "measured locally, not published (licence)"

/**
 * Committed output of `studio/bench/run_bench.py`: which GPU tools run on the reference machine, their versions, and the metrics their licences allow publishing (DC-001-05, spec 001-contracts).
 */
export interface PitStudioCapabilityReport {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
generated: Date
gpu: string
driver: Driver
probes: {
[k: string]: ProbeResult | undefined
}
}
/**
 * one probe of the capability bench
 * 
 * This interface was referenced by `PitStudioCapabilityReport`'s JSON-Schema
 * via the `definition` "probe_result".
 */
export interface ProbeResult {
status: ("pass" | "fail" | "skip")
versions: {
[k: string]: string | undefined
}
metrics?: ({
[k: string]: number | string | undefined
} | LocalOnly)
telemetry?: {
[k: string]: number | undefined
}
/**
 * @maxItems 20
 */
notes?: []|[string]|[string, string]|[string, string, string]|[string, string, string, string]|[string, string, string, string, string]|[string, string, string, string, string, string]|[string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]
error?: string
}
