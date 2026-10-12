/* Generated from contracts/split.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Groups and grouped folds fixed at ingestion by s10_preprocess under data/splits/ (DC-008-04, spec 008-data-pipeline).
 */
export type GroupedSplitFile = {
$schema?: string
schema_version: SchemaVersion
id: Slug
dataset: {
id: Slug
version: Version
kind: ("real" | "synthetic")
}
group_key: GroupKey
/**
 * @maxItems 4096
 */
links: {
a: RecordId
b: RecordId
}[]
/**
 * @minItems 1
 * @maxItems 100000
 */
groups: [{
id: RecordId
/**
 * @minItems 1
 * @maxItems 100000
 */
members: [RecordId, ...(RecordId)[]]
}, ...({
id: RecordId
/**
 * @minItems 1
 * @maxItems 100000
 */
members: [RecordId, ...(RecordId)[]]
})[]]
method: ("seeded-greedy-grouped-kfold" | "none")
seed: (number | null)
/**
 * @maxItems 20
 */
folds: []|[Fold]|[Fold, Fold]|[Fold, Fold, Fold]|[Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]|[Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold, Fold]
/**
 * SHA-256 of the RFC 8785 canonical JSON of {groups, folds}.
 */
membership_sha256: string
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
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "group_key".
 */
export type GroupKey = {
rule: ("mendeley-original-component" | "scenario-seed" | "event-seed" | "muck-pile-id" | "pit-layout-id" | "scene-seed" | "project-spatial-block" | "single-group")
block_size_m?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "record_id".
 */
export type RecordId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "fold".
 */
export interface Fold {
index: number
/**
 * @maxItems 100000
 */
test: RecordId[]
/**
 * @maxItems 1000000
 */
train_pool: RecordId[]
}
