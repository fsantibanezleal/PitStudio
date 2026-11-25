/* Generated from contracts/fetch-record.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One record per registry file written by s00_download (DC-008-02, spec 008-data-pipeline).
 */
export type FetchRecord = {
$schema?: string
schema_version: SchemaVersion
source: Slug
/**
 * Local file name.
 */
name: string
url: HttpsUrl
final_url: (HttpsUrl | null)
/**
 * Path relative to the data root.
 */
stored_as: (Relpath | null)
bytes: (FileBytes | null)
expected_bytes: (FileBytes | null)
sha256: (Sha256 | null)
expected_sha256: (Sha256 | null)
publisher_checksum: (string | null)
publisher_checksum_status: ("match" | "mismatch" | "not-declared" | "not-checked")
spdx: SpdxId
licence_class: LicenceClass
redistribution: ("redistributable" | "derived-only" | "no-redistribution")
retrieved: (UtcTimestamp | null)
status: ("verified" | "fallback-used" | "unavailable" | "skipped-no-account" | "pin-proposed")
/**
 * @maxItems 8
 */
fallback_sources: []|[Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
attempts: number
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
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "file_bytes".
 */
export type FileBytes = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "utc_timestamp".
 */
export type UtcTimestamp = string
