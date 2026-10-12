/* Generated from contracts/knowledge-bundle.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * One knowledge-table row as published, with its SI conversion.
 * 
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "parameter".
 */
export type Parameter = ({
id: KnowledgeRowId
module: Module
quantity?: string
value?: (number | string)
range?: Range
units: string
si: ({
[k: string]: unknown | undefined
} & {
value?: number
range?: Range
unit: string
})
citation: BibKey
page: string
verification: Verification
verified_on?: Date
/**
 * @minItems 1
 * @maxItems 8
 */
symbols: [MinephysSymbol]|[MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol]|[MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol, MinephysSymbol]
role?: ("model_constant" | "parameter" | "limit" | "conversion")
licence: SpdxId
} & Parameter1)
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "knowledge_row_id".
 */
export type KnowledgeRowId = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "module".
 */
export type Module = ("haulage" | "blasting" | "geotech" | "bulk" | "comminution" | "environment" | "planning")
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "bib_key".
 */
export type BibKey = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "verification".
 */
export type Verification = ("verified" | "UNVERIFIED")
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "date".
 */
export type Date = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "minephys_symbol".
 */
export type MinephysSymbol = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
export type Parameter1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "equation".
 */
export type Equation = {
id: KnowledgeRowId
title: string
module: Module
latex: string
/**
 * @minItems 1
 * @maxItems 64
 */
symbols: [{
symbol: string
meaning: string
units: string
}, ...({
symbol: string
meaning: string
units: string
})[]]
function: MinephysSymbol
citation: BibKey
page: string
verification: Verification
verified_on?: Date
/**
 * @minItems 0
 * @maxItems 64
 */
rows?: KnowledgeRowId[]
theory?: {
topic: ("haulage" | "loading-and-terramechanics" | "drill-and-blast" | "slopes-and-monitoring" | "bulk-flow-dem-mpm" | "comminution" | "dust" | "tailings" | "planning" | "rtx-sensor-physics" | "robot-learning" | "vision-language-reasoning" | "sim-to-real")
anchor: string
}
engine?: {
id: string
spec: ("007-haulage-dispatch" | "013-sensors" | "014-robot-learning" | "018-web-cases")
}
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "tool_id".
 */
export type ToolId = string
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "bib_entry".
 */
export type BibEntry = (BibEntry1 & {
key: BibKey
entry_type: ("article" | "book" | "inbook" | "inproceedings" | "techreport" | "manual" | "misc")
authors: string
title: string
year: number
doi?: string
url?: HttpsUrl
access: ("open" | "paywalled" | "regulation" | "bibliographic-only")
cited_by: {
/**
 * @minItems 0
 * @maxItems 10000
 */
parameters: KnowledgeRowId[]
/**
 * @minItems 0
 * @maxItems 2000
 */
equations: KnowledgeRowId[]
}
})
export type BibEntry1 = {
[k: string]: unknown | undefined
}

/**
 * Knowledge bundle web/public/knowledge/bundle.json generated by build_knowledge.py from the pinned minephys export (DC-020-03, spec 020-web-knowledge).
 */
export interface KnowledgeBundle {
$schema?: string
schema_version: string
/**
 * The pinned minephys knowledge export and the PitStudio files the bundle was built from.
 */
source: {
minephys_version: Version
minephys_commit: GitSha
/**
 * @minItems 0
 * @maxItems 8
 */
inputs: []|[{
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]|[{
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}, {
path: Relpath
sha256: Sha256
}]
}
/**
 * @minItems 0
 * @maxItems 10000
 */
parameters: Parameter[]
/**
 * @minItems 0
 * @maxItems 2000
 */
equations: Equation[]
/**
 * @minItems 0
 * @maxItems 5000
 */
glossary: Term[]
/**
 * @minItems 0
 * @maxItems 256
 */
datasets: Dataset[]
/**
 * @minItems 0
 * @maxItems 64
 */
frameworks: Framework[]
/**
 * @minItems 0
 * @maxItems 5000
 */
bibliography: BibEntry[]
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "range".
 */
export interface Range {
min: number
max: number
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "term".
 */
export interface Term {
id: string
origin: ("minephys" | "docs")
term_en: string
term_es: string
definition_en: string
definition_es: string
citation?: BibKey
/**
 * @minItems 0
 * @maxItems 16
 */
see_also?: []|[string]|[string, string]|[string, string, string]|[string, string, string, string]|[string, string, string, string, string]|[string, string, string, string, string, string]|[string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string, string, string, string, string, string, string, string, string]
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "dataset".
 */
export interface Dataset {
id: Slug
title: string
kind: ("real" | "synthetic")
spdx: SpdxId
redistribution: ("redistributable" | "derived-only" | "no-redistribution")
landing_url: HttpsUrl
card: string
}
/**
 * This interface was referenced by `KnowledgeBundle`'s JSON-Schema
 * via the `definition` "framework".
 */
export interface Framework {
id: ToolId
name: string
category: ("studio-tool" | "component")
status: ("not-yet-run" | "done" | "evaluated-not-adopted")
licence_class: LicenceClass
}
