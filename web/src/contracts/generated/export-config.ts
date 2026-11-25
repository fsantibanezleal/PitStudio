/* Generated from contracts/export-config.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Per-model export config read by s60_export and s62_accel: opset and reason, output roles, gemm_heavy, web, domain allow-list, task metric, golden-set id and live flag (DC-016-04, spec 016-export-acceleration).
 */
export type ExportConfig = {
$schema?: string
schema_version: SchemaVersion
model: Slug
opset: (17 | 18 | 19)
opset_reason: string
ir_version: 10
/**
 * @minItems 1
 * @maxItems 16
 */
outputs: [Output]|[Output, Output]|[Output, Output, Output]|[Output, Output, Output, Output]|[Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]|[Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output, Output]
post_processor_in_graph: boolean
gemm_heavy: boolean
web: boolean
live: boolean
/**
 * @minItems 1
 * @maxItems 3
 */
domains: [("ai.onnx" | "ai.onnx.ml" | "com.microsoft")]|[("ai.onnx" | "ai.onnx.ml" | "com.microsoft"), ("ai.onnx" | "ai.onnx.ml" | "com.microsoft")]|[("ai.onnx" | "ai.onnx.ml" | "com.microsoft"), ("ai.onnx" | "ai.onnx.ml" | "com.microsoft"), ("ai.onnx" | "ai.onnx.ml" | "com.microsoft")]
/**
 * @minItems 1
 * @maxItems 4
 */
precisions: [("fp32" | "fp16" | "int8" | "fp8")]|[("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8")]|[("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8")]|[("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8"), ("fp32" | "fp16" | "int8" | "fp8")]
task_metric: {
id: ParamKey
unit: "pct"
orientation: ("higher-is-better" | "lower-is-better")
}
golden_set_id: Slug
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
 * via the `definition` "param_key".
 */
export type ParamKey = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "output".
 */
export interface Output {
name: string
role: ("class_scores" | "boxes" | "labels" | "scores" | "masks" | "regression" | "field" | "action_logits" | "value")
}
