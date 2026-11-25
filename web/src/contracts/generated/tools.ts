/* Generated from contracts/tools.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * tool registry entry (data-model §4.1)
 * 
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "entry".
 */
export type Entry = {
id: ToolId
name: string
category: ("studio-tool" | "component")
/**
 * @minItems 1
 * @maxItems 4
 */
envs: [ToolEnv]|[ToolEnv, ToolEnv]|[ToolEnv, ToolEnv, ToolEnv]|[ToolEnv, ToolEnv, ToolEnv, ToolEnv]
version: VersionRef
/**
 * @minItems 1
 * @maxItems 4
 */
spdx: [SpdxId]|[SpdxId, SpdxId]|[SpdxId, SpdxId, SpdxId]|[SpdxId, SpdxId, SpdxId, SpdxId]
osi: boolean
licence_class: LicenceClass
ring: ("Adopt" | "Trial" | "Assess" | "Hold")
lane: ("live" | "replay" | "local-only")
performance: ("public" | "local-only")
role: string
/**
 * @maxItems 12
 */
cases: []|[CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
/**
 * @maxItems 16
 */
produces: []|[ArtefactKind]|[ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]|[ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind, ArtefactKind]
status: ("not-yet-run" | "done" | "evaluated-not-adopted")
reason?: string
docs_page?: string
/**
 * @maxItems 8
 */
alternatives_rejected?: []|[{
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]|[{
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}, {
name: string
reason: string
}]
notice?: string
}
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "tool_id".
 */
export type ToolId = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "tool_env".
 */
export type ToolEnv = ("root" | "runner" | "studio" | "isaac" | "rtx" | "isaaclab" | "kit" | "reason" | "pipeline" | "accel" | "web" | "external")
/**
 * a version reference resolved by the checker (data-model §4.2); never a literal string
 * 
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "version_ref".
 */
export type VersionRef = ({
from_lock: ("uv.lock" | "studio/uv.lock" | "studio/isaac/uv.lock" | "studio/rtx/uv.lock" | "studio/isaaclab/uv.lock" | "pipeline/uv.lock" | "pipeline/accel/uv.lock" | "web/pnpm-lock.yaml")
package: Package
} | {
from_binary: BinaryId
release: Version
sha256: Sha256
} | {
from_git_tag: Version
repository: HttpsUrl
} | {
own: true
})
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "package".
 */
export type Package = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "binary_id".
 */
export type BinaryId = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "https_url".
 */
export type HttpsUrl = string
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `PitStudioToolRegistry`'s JSON-Schema
 * via the `definition` "artefact_kind".
 */
export type ArtefactKind = ("video" | "image" | "figure" | "point-cloud" | "mesh" | "tiles" | "splat" | "onnx" | "table" | "trace" | "shard" | "field" | "text" | "model-card" | "telemetry" | "usd")

/**
 * The studio tool registry studio/tools.yaml (DC-001-03, spec 001-contracts).
 */
export interface PitStudioToolRegistry {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
/**
 * @minItems 1
 * @maxItems 64
 */
tools: [Entry, ...(Entry)[]]
}
