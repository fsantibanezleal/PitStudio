/* Generated from contracts/sources.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * source registry entry (data-model §5.1)
 * 
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "entry".
 */
export type Entry = (({
kind: "real"
spdx: "LicenseRef-USGov-PD"
licence_class: "public-domain"
} | {
kind: "real"
spdx: ("CC0-1.0" | "DL-DE-ZERO-2.0")
licence_class: "open-no-attribution"
} | {
kind: "real"
spdx: ("CC-BY-4.0" | "LicenseRef-Copernicus-CLMS")
licence_class: "attribution"
} | {
kind: "real"
spdx: ("CC-BY-SA-3.0" | "CC-BY-SA-4.0")
licence_class: "share-alike"
} | {
kind: "synthetic"
spdx: ("CC-BY-4.0" | "Apache-2.0")
licence_class: "own"
} | {
kind: "synthetic"
spdx: "LicenseRef-NVIDIA-Open-Model"
licence_class: "display-only"
}) & {
id: Slug
kind: ("real" | "synthetic")
title: string
landing_url: HttpsUrl
access: ("direct" | "api" | "account" | "manual")
/**
 * @maxItems 512
 */
files: File[]
spdx: SpdxId
licence_url: HttpsUrl
licence_class: LicenceClass
redistribution: ("redistributable" | "derived-only" | "no-redistribution")
attribution?: string
citation: string
card: string
/**
 * `env_var` is the name of the variable holding the key, never a credential value
 */
account: {
needed: boolean
env_var?: EnvVar
note?: string
}
/**
 * substitute sources in order of preference; [] = no substitute data
 */
fallback?: {
/**
 * @maxItems 8
 */
sources: []|[Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
text: string
}
optional?: boolean
})
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * file record (data-model §5.1.1); null sha256 / bytes = not yet pinned / known
 * 
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "file".
 */
export type File = {
url: HttpsUrl
sha256: (Sha256 | null)
bytes: (number | null)
name?: Relpath
spdx?: SpdxId
kind: ("raster" | "point-cloud" | "vector" | "image-set" | "table" | "document" | "archive")
publisher_checksum?: string
uncompressed_bytes?: number
/**
 * @minItems 1
 * @maxItems 64
 */
extract?: [Relglob, ...(Relglob)[]]
}
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "relglob".
 */
export type Relglob = string
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `PitStudioSourceRegistry`'s JSON-Schema
 * via the `definition` "env_var".
 */
export type EnvVar = string

/**
 * The data source registry data/sources.yaml (DC-001-04, spec 001-contracts).
 */
export interface PitStudioSourceRegistry {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
/**
 * @maxItems 256
 */
sources: Entry[]
}
