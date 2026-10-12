/* Generated from contracts/figures.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "chart".
 */
export type Chart = {
kind: "chart"
id: FigureId
topic: Topic
title: NameEnEs
engine: Engine
plot: ("xy" | "field" | "section" | "3d")
/**
 * @minItems 1
 * @maxItems 16
 */
controls: [(RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]|[(RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl), (RangeControl | ChoiceControl)]
/**
 * @minItems 1
 * @maxItems 8
 */
features: [{
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]|[{
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}, {
id: ParamKey
label: NameEnEs
unit?: Unit
}]
colormap: ("viridis" | "cividis" | "inferno" | "magma" | null)
justification3d?: {
third_variable: string
unit: Unit
reason: TextEnEs
}
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "figure_id".
 */
export type FigureId = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "topic".
 */
export type Topic = ("haulage" | "loading-and-terramechanics" | "drill-and-blast" | "slopes-and-monitoring" | "bulk-flow-dem-mpm" | "comminution" | "dust" | "tailings" | "planning" | "rtx-sensor-physics" | "robot-learning" | "vision-language-reasoning" | "sim-to-real")
/**
 * Browser engine of specs 007, 013, 014 or 018, or a teaching function of web/src/theory/fn/.
 * 
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "engine".
 */
export type Engine = {
kind: ("engine" | "teaching")
id: string
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "knowledge_row_id".
 */
export type KnowledgeRowId = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")

/**
 * Interactive figures and registered photographs of web/src/theory/figures.yaml (DC-020-04, spec 020-web-knowledge).
 */
export interface FigureRegistry {
$schema?: string
/**
 * @minItems 1
 * @maxItems 128
 */
figures: [(Chart | Photo), ...((Chart | Photo))[]]
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "name_en_es".
 */
export interface NameEnEs {
en: string
es: string
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "range_control".
 */
export interface RangeControl {
kind: "range"
id: ParamKey
label: NameEnEs
unit: Unit
min: number
max: number
step: number
default: number
default_row?: KnowledgeRowId
digest_exempt?: boolean
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "choice_control".
 */
export interface ChoiceControl {
kind: "choice"
id: ParamKey
label: NameEnEs
/**
 * @minItems 2
 * @maxItems 16
 */
options: [{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]|[{
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}, {
id: Slug
label: NameEnEs
}]
default: Slug
default_row?: KnowledgeRowId
}
/**
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "text_en_es".
 */
export interface TextEnEs {
en: string
es: string
}
/**
 * A registered raster photograph (FR-020-16); charts are never raster images.
 * 
 * This interface was referenced by `FigureRegistry`'s JSON-Schema
 * via the `definition` "photo".
 */
export interface Photo {
kind: "photo"
id: FigureId
file: Relpath
alt: TextEnEs
licence: SpdxId
attribution?: string
}
