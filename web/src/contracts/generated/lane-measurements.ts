/* Generated from contracts/lane-measurements.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "semver".
 */
export type Semver = string
/**
 * measurements of one engine or one artefact
 * 
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "entry".
 */
export type Entry = ({
/**
 * engine ids of the engine table (spec 018 section 7.1)
 */
engine?: ("des" | "policies" | "haulage" | "lp" | "routing" | "il1-twin" | "il2-twin" | "granular" | "gns" | "traffic" | "dust-lidar" | "detector" | "geotech" | "forecasters" | "swe" | "fno" | "plume" | "dust-particles" | "blasting" | "watershed" | "unet" | "comminution" | "meta-model" | "mincut" | "volume")
artefact?: ArtefactId
measurements: LaneMeasurements
} & Entry1)
/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
export type Entry1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string

/**
 * Lane measurements assets/lane-measurements.json of the built Pages artifact, written by the T2 lane-gate suite in CI (DC-018-06, spec 018-web-cases).
 */
export interface PitStudioLaneMeasurements {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
/**
 * the measured commit
 */
git_sha: string
generated: UtcTimestamp
runner: Runner
/**
 * @minItems 1
 * @maxItems 2048
 */
entries: [Entry, ...(Entry)[]]
}
/**
 * CI runner configuration of the measurements (spec 018 section 7.3)
 * 
 * This interface was referenced by `PitStudioLaneMeasurements`'s JSON-Schema
 * via the `definition` "runner".
 */
export interface Runner {
os_image: string
cpu_model: string
logical_cpus: number
memory_bytes: number
browser: "chromium"
browser_version: Version
headless: true
playwright_version: Semver
node_version: Semver
forced_tier: "T2"
/**
 * interactions per engine for the p95 interaction time
 */
interactions: 50
/**
 * full runs per engine for the median run time
 */
runs: 5
}
/**
 * lane measurements (data-model §2.6); the lane value is checked against the gate by tools/check_contracts.py
 */
export interface LaneMeasurements {
web_drivable: boolean
max_asset_bytes: number
interaction_ms: (number | null)
run_ms_t2: (number | null)
trace_bytes: (number | null)
measured: {
tier: "T2"
date: string
browser: string
}
}
