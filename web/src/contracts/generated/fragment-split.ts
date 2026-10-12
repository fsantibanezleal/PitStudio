/* Generated from contracts/fragment-split.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `MendeleyPerFoldValidationSubsets`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Validation subsets recorded on top of the spec 008 split file (DC-008-04): groups, folds and test lists live only there (DC-012-02, spec 012-fragmentation).
 */
export interface MendeleyPerFoldValidationSubsets {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
kind: "folds"
source_id: "mendeley-78ht3pjsr4"
archive_sha256: "7f4336a4fe1f83e3c828eed4c73e036d7694f94076b6f040e6211315693f402d"
/**
 * id of the spec 008 split file data/splits/<id>.json (DC-008-04) the validation subsets are carved from
 */
split_id: string
/**
 * membership_sha256 recorded in that split file; the 012 file is stale if it differs
 */
split_membership_sha256: string
validation_fraction: 0.1
validation_seed: number
/**
 * files of an original k: k, k + 240, k + 480, k + 720
 */
expansion: "dihedral-4"
/**
 * @minItems 5
 * @maxItems 5
 */
folds: [Fold, Fold, Fold, Fold, Fold]
}
/**
 * one fold of the spec 008 split file; the validation files are k + 240 m (m = 0..3) of the listed originals, carved by whole groups from that fold's training pool (FR-012-05)
 * 
 * This interface was referenced by `MendeleyPerFoldValidationSubsets`'s JSON-Schema
 * via the `definition` "fold".
 */
export interface Fold {
fold: number
/**
 * @minItems 1
 * @maxItems 240
 * 
 * Items: original file number
 */
validation_originals: [number, ...(number)[]]
}
