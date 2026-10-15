/* Generated from contracts/vlm-queries.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "query".
 */
export type Query = {
query_id: ArtefactId
frame_id: ArtefactId
frame_state_sha256: Sha256
type: number
condition: ("day" | "night" | "dust" | "rain")
location: ("haul_road" | "bench" | "loading_area")
truth: AnswerLabel
gate_subset: boolean
reasoning_subset: boolean
}
/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `TaskAQuerySet`'s JSON-Schema
 * via the `definition` "answer_label".
 */
export type AnswerLabel = ("yes" | "no" | "0" | "1" | "2" | "3+")

/**
 * Task-A hazard query set written by the query builder: one query per (frame, type) with its exact answer (DC-015-02, spec 015-vlm).
 */
export interface TaskAQuerySet {
$schema?: string
schema_version: SchemaVersion
seed: number
source_run_id: RunId
/**
 * @minItems 1
 * @maxItems 6480
 */
queries: [Query, ...(Query)[]]
}
