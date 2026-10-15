/* Generated from contracts/surrogate-io.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Input/output description of an exported surrogate, forecaster or meta-model graph written by s60_export (DC-011-02, spec 011-surrogates; also DC-010-05 and the spec 017 meta-model).
 */
export type SurrogateONNXInputOutputDescription = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
model_id: Slug
/**
 * consuming web engine
 */
engine: ("gns" | "fno" | "forecasters" | "meta-model")
/**
 * @minItems 1
 * @maxItems 12
 */
cases?: [CaseId]|[CaseId, CaseId]|[CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]|[CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId, CaseId]
description?: string
onnx: OnnxFile
/**
 * default-domain opset
 */
opset: (17 | 18 | 19)
ir_version: 10
/**
 * ai.onnx.ml opset (tree converters only)
 */
ml_opset?: number
/**
 * precision of the graph's arithmetic
 */
precision: ("fp32" | "fp16" | "int8" | "fp8")
/**
 * live in the browser, precomputed outputs, or bench only
 */
delivery: ("live" | "precompute" | "bench-only")
delivery_reason?: string
/**
 * GNS message aggregation layout
 */
aggregation?: ("padded-gather" | "scatter-add")
symbolic_dims?: {
[k: string]: SymbolicDim | undefined
}
/**
 * model constants (unit-suffixed keys)
 */
constants?: {
[k: string]: number | undefined
}
/**
 * @minItems 1
 * @maxItems 16
 */
inputs: [Tensor]|[Tensor, Tensor]|[Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]
/**
 * @minItems 1
 * @maxItems 16
 */
outputs: [Tensor]|[Tensor, Tensor]|[Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]|[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]
training_envelope: {
[k: string]: EnvelopeRange | undefined
}
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * one graph input or output
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tensor".
 */
export type Tensor = {
name: TensorName
dtype: Dtype
/**
 * @minItems 1
 * @maxItems 8
 */
shape: [Dim]|[Dim, Dim]|[Dim, Dim, Dim]|[Dim, Dim, Dim, Dim]|[Dim, Dim, Dim, Dim, Dim]|[Dim, Dim, Dim, Dim, Dim, Dim]|[Dim, Dim, Dim, Dim, Dim, Dim, Dim]|[Dim, Dim, Dim, Dim, Dim, Dim, Dim, Dim]
unit: TensorUnit
channel_axis?: number
/**
 * @minItems 1
 * @maxItems 64
 */
channels?: [Channel, ...(Channel)[]]
normalisation?: Normalisation
/**
 * allowed category names in index order (e.g. particle types)
 * 
 * @minItems 1
 * @maxItems 64
 */
categories?: [Slug, ...(Slug)[]]
quantile_axis?: number
/**
 * quantile levels in output order
 * 
 * @minItems 1
 * @maxItems 99
 */
quantiles?: [number, ...(number)[]]
description?: string
}
/**
 * graph input or output name
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tensor_name".
 */
export type TensorName = string
/**
 * ONNX Runtime tensor element type
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dtype".
 */
export type Dtype = ("float32" | "float16" | "bfloat16" | "int64" | "int32" | "int8" | "uint8" | "bool")
/**
 * a fixed dimension (integer) or a symbolic one declared in `symbolic_dims`
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dim".
 */
export type Dim = (number | string)
/**
 * physical unit ("1" = dimensionless, counts, indices and categories); "per-channel" when the channels carry their own units
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tensor_unit".
 */
export type TensorUnit = ("1" | "m" | "mm" | "um" | "m^2" | "m^3" | "m^2/s" | "s" | "h" | "deg" | "rad" | "m/s" | "m/s^2" | "mm/h" | "h/mm" | "Pa" | "Pa.s" | "kg" | "kg/m^3" | "kg/m^2/s" | "ug/m^3" | "kW" | "kWh/t" | "t/h" | "USD/kg" | "USD/kWh" | "USD/t" | "per-channel")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * physical unit ("1" = dimensionless, counts, indices and categories)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = ("1" | "m" | "mm" | "um" | "m^2" | "m^3" | "m^2/s" | "s" | "h" | "deg" | "rad" | "m/s" | "m/s^2" | "mm/h" | "h/mm" | "Pa" | "Pa.s" | "kg" | "kg/m^3" | "kg/m^2/s" | "ug/m^3" | "kW" | "kWh/t" | "t/h" | "USD/kg" | "USD/kWh" | "USD/t")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "normalisation".
 */
export type Normalisation = {
/**
 * map from physical values to tensor values: standardise (x - mean) / std; log-standardise (ln x - mean) / std; patch-relief (x - patch mean) / patch relief; context-mean-abs x / mean |x| of the input context (outputs are scaled back by the same factor)
 */
rule: ("none" | "standardise" | "log-standardise" | "patch-relief" | "context-mean-abs")
/**
 * true: the graph applies the map itself and the tensor carries physical values
 */
applied_in_graph: boolean
/**
 * one value per channel, or one broadcast value
 * 
 * @minItems 1
 * @maxItems 64
 */
mean?: [number, ...(number)[]]
/**
 * one value per channel, or one broadcast value
 * 
 * @minItems 1
 * @maxItems 64
 */
std?: [number, ...(number)[]]
}

/**
 * the exported ONNX file this description belongs to
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "onnx_file".
 */
export interface OnnxFile {
path: Relpath
sha256: Sha256
bytes: number
}
/**
 * accepted range of a symbolic dimension
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "symbolic_dim".
 */
export interface SymbolicDim {
min: number
max: number
}
/**
 * one channel; the array order is the channel order
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "channel".
 */
export interface Channel {
name: ParamKey
unit: Unit
normalisation?: Normalisation
description?: string
}
/**
 * closed training range of one parameter; outside it a result is labelled extrapolation
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "envelope_range".
 */
export interface EnvelopeRange {
min: number
max: number
unit: Unit
description?: string
}
