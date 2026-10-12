/* Generated from contracts/methods.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "method".
 */
export type Method = {
id: MethodId
name: NameEnEs
/**
 * @minItems 1
 * @maxItems 3
 */
tiers: [("classical" | "sota" | "beyond-sota" | "frontier")]|[("classical" | "sota" | "beyond-sota" | "frontier"), ("classical" | "sota" | "beyond-sota" | "frontier")]|[("classical" | "sota" | "beyond-sota" | "frontier"), ("classical" | "sota" | "beyond-sota" | "frontier"), ("classical" | "sota" | "beyond-sota" | "frontier")]
implementation: string
/**
 * @minItems 1
 * @maxItems 4
 */
spdx: [SpdxId]|[SpdxId, SpdxId]|[SpdxId, SpdxId, SpdxId]|[SpdxId, SpdxId, SpdxId, SpdxId]
/**
 * @minItems 1
 * @maxItems 3
 */
lanes: [("live" | "precompute" | "replay")]|[("live" | "precompute" | "replay"), ("live" | "precompute" | "replay")]|[("live" | "precompute" | "replay"), ("live" | "precompute" | "replay"), ("live" | "precompute" | "replay")]
learned: boolean
/**
 * @minItems 1
 * @maxItems 12
 */
cases: [CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
comparison?: Comparison
criterion?: Criterion
docs_page: string
}
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "method_id".
 */
export type MethodId = ("M1" | "M2" | "M3" | "M4" | "M5" | "M6" | "M7" | "M8" | "M9" | "M10" | "M11" | "M12" | "M13" | "M14" | "M15" | "M16" | "M17" | "M18" | "M19" | "M20" | "M21" | "M22" | "M23")
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = string

/**
 * The method ladder M1-M23 of studio/methods.yaml (DC-020-01, spec 020-web-knowledge).
 */
export interface MethodRegistry {
$schema?: string
/**
 * @minItems 23
 * @maxItems 23
 */
methods: [Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method, Method]
}
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "name_en_es".
 */
export interface NameEnEs {
en: string
es: string
}
/**
 * Pre-registered comparison design: baseline, metric with unit and orientation, pairing unit and number of pairs.
 * 
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "comparison".
 */
export interface Comparison {
baseline: NameEnEs
metric: Metric
pairing_unit: NameEnEs
n: number
}
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "metric".
 */
export interface Metric {
name: NameEnEs
unit: Unit
orientation: ("higher-is-better" | "lower-is-better")
}
/**
 * Acceptance criterion copied from the owning model spec's SC row.
 * 
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "criterion".
 */
export interface Criterion {
text: TextEnEs
requirement: string
spec: string
}
/**
 * This interface was referenced by `MethodRegistry`'s JSON-Schema
 * via the `definition` "text_en_es".
 */
export interface TextEnEs {
en: string
es: string
}
