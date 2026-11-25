/* Generated from contracts/slope-results.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "fos_result".
 */
export type FosResult = {
method: Method
status: ("ok" | "no valid slip surface")
fos?: number
critical_circle?: Circle
iterations?: number
theta_deg?: number
slices: number
circles_evaluated: number
rejected_circles: number
}
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "method".
 */
export type Method = ("bishop" | "spencer")
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "coordinate_m".
 */
export type CoordinateM = number
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "probability".
 */
export type Probability = number
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "pof_seed".
 */
export type PofSeed = number

/**
 * Factor-of-safety and probability-of-failure tables of the C1 analysis per section and method (F, critical circle, rejected circles, k, N, K, PoF and its Wilson interval), baked for the web and the docs (DC-010-04, spec 010-slope).
 */
export interface C1FoSAndPoFTables {
$schema?: string
schema_version: string
run_id?: RunId
mode: ("live" | "baked")
/**
 * @minItems 1
 * @maxItems 1000
 */
sections: [SectionResult, ...(SectionResult)[]]
}
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "section_result".
 */
export interface SectionResult {
section_id: ArtefactId
section_sha256: Sha256
/**
 * @minItems 1
 * @maxItems 2
 */
fos: [FosResult]|[FosResult, FosResult]
pof?: PofResult
}
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "circle".
 */
export interface Circle {
centre_x_m: CoordinateM
centre_z_m: CoordinateM
radius_m: number
entry_x_m: CoordinateM
exit_x_m: CoordinateM
}
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "pof_result".
 */
export interface PofResult {
method: Method
candidate_set: "lowest-F circles of the mean-parameter Bishop search"
samples: number
candidates: number
failures: number
pof: Probability
wilson_95: WilsonInterval
seed: PofSeed
}
/**
 * This interface was referenced by `C1FoSAndPoFTables`'s JSON-Schema
 * via the `definition` "wilson_interval".
 */
export interface WilsonInterval {
lower: Probability
upper: Probability
z: 1.96
}
