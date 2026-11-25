/* Generated from contracts/ingestion-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Accepted or rejected inputs with every violation, written by s10_preprocess and s20_feature_extraction (DC-008-03, spec 008-data-pipeline).
 */
export type IngestionReport = {
$schema?: string
schema_version: SchemaVersion
source: Slug
stage: ("s10_preprocess" | "s20_feature_extraction")
run_id: RunId
created: UtcTimestamp
status: ("accepted" | "rejected")
/**
 * @minItems 1
 * @maxItems 100000
 */
files: [CheckedFile, ...(CheckedFile)[]]
/**
 * @maxItems 1000000
 */
violations: Violation[]
/**
 * @maxItems 4096
 */
outputs: {
path: Relpath
sha256: Sha256
}[]
/**
 * true = only some files of a multi-file source were verified; the missing ones are listed with status unavailable (FR-008-50)
 */
partial?: boolean
/**
 * true = the source is a fixture (FR-008-49)
 */
fixture?: boolean
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
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "checked_file".
 */
export type CheckedFile = {
/**
 * Path relative to the data root.
 */
path: string
/**
 * null only for a file with status unavailable (never fetched)
 */
sha256: (Sha256 | null)
validator: ("tabular" | "raster" | "point-cloud" | "vector" | "image-mask" | "image" | "series" | "dataset-structure")
schema_name: string
status: ("accepted" | "rejected" | "unavailable")
records: (number | null)
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "violation".
 */
export interface Violation {
file: Relpath
/**
 * Table row or series index.
 */
row: (number | null)
pixel: ({
x: number
y: number
} | null)
field: string
field_kind: ("column" | "property")
/**
 * Found value; non-finite values are written as text.
 */
value: (string | number | boolean | null)
expected: (string | null)
rule: string
unit: (string | null)
}
