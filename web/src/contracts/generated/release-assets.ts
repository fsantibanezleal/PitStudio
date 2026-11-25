/* Generated from contracts/release-assets.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `ReleaseAssetUploadList`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `ReleaseAssetUploadList`'s JSON-Schema
 * via the `definition` "release_tag".
 */
export type ReleaseTag = string
/**
 * This interface was referenced by `ReleaseAssetUploadList`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `ReleaseAssetUploadList`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Release-asset upload list written by s60_export: tag and the release-hosted files with path, bytes and SHA-256, sorted by path (DC-016-02, spec 016-export-acceleration).
 */
export interface ReleaseAssetUploadList {
$schema?: string
schema_version: SchemaVersion
tag: ReleaseTag
/**
 * @maxItems 2000
 */
entries: Entry[]
}
/**
 * This interface was referenced by `ReleaseAssetUploadList`'s JSON-Schema
 * via the `definition` "entry".
 */
export interface Entry {
path: Relpath
bytes: number
sha256: Sha256
}
