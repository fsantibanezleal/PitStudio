/* Generated from contracts/dispatch-policy-io.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "policy".
 */
export type Policy = {
id: ("ppo" | "attention")
architecture: ("shared-mlp" | "dense-attention")
artefact_id: ArtefactId
onnx: Onnx
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Tensor layout, feature order, units, normalisation, masks and tie rule of an exported dispatch policy, written by s60_export (DC-007-04, spec 007-haulage-dispatch).
 */
export interface DispatchPolicyInputOutputLayout {
$schema?: string
schema_version: SchemaVersion
layout_version: 1
policy: Policy
inputs: Inputs
output: Output
decision: Decision
padding: Padding
time_unit: "h"
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "onnx".
 */
export interface Onnx {
path: Relpath
sha256: Sha256
bytes: number
opset: number
ir_version: 10
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "inputs".
 */
export interface Inputs {
truck_features: {
name: "truck_features"
dtype: "float32"
shape: [1,40,12]
features: [{"index":0,"name":"state_travel_empty","unit":"1","transform":"one-hot truck state"},{"index":1,"name":"state_queue_loader","unit":"1","transform":"one-hot truck state"},{"index":2,"name":"state_loading","unit":"1","transform":"one-hot truck state"},{"index":3,"name":"state_travel_loaded","unit":"1","transform":"one-hot truck state"},{"index":4,"name":"state_queue_dump","unit":"1","transform":"one-hot truck state"},{"index":5,"name":"state_dumping","unit":"1","transform":"one-hot truck state"},{"index":6,"name":"state_parked_or_down","unit":"1","transform":"one-hot truck state"},{"index":7,"name":"payload_ratio","unit":"1","transform":"payload / class mean payload"},{"index":8,"name":"time_left_in_state_h","unit":"h","transform":"identity"},{"index":9,"name":"eta_to_target_h","unit":"h","transform":"identity"},{"index":10,"name":"deciding","unit":"1","transform":"1 for the deciding truck, else 0"},{"index":11,"name":"valid","unit":"1","transform":"1 for a real truck slot, 0 for padding"}]
}
target_features: {
name: "target_features"
dtype: "float32"
shape: [1,16,9]
features: [{"index":0,"name":"is_dump","unit":"1","transform":"0 = loader, 1 = dump"},{"index":1,"name":"queued_frac","unit":"1","transform":"queued trucks / 40"},{"index":2,"name":"inbound_frac","unit":"1","transform":"inbound trucks / 40"},{"index":3,"name":"time_until_free_h","unit":"h","transform":"identity"},{"index":4,"name":"backlog_h","unit":"h","transform":"identity"},{"index":5,"name":"mean_service_time_h","unit":"h","transform":"identity"},{"index":6,"name":"deciding_truck_eta_h","unit":"h","transform":"identity; 0 when masked"},{"index":7,"name":"spots_frac","unit":"1","transform":"loading spots / 4"},{"index":8,"name":"serviceable","unit":"1","transform":"1 if serviceable, else 0"}]
}
truck_mask: {
name: "truck_mask"
dtype: "bool"
shape: [1,40]
meaning: "true = real truck slot"
}
target_mask: {
name: "target_mask"
dtype: "bool"
shape: [1,16]
meaning: "true = serviceable and reachable for the deciding truck"
}
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "output".
 */
export interface Output {
name: "logits"
dtype: "float32"
shape: [1,16]
meaning: "one logit per target slot"
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "decision".
 */
export interface Decision {
masking: "masked target has probability 0"
applied_by: "des"
selection: "argmax"
tie_rule: "lowest-target-index"
}
/**
 * This interface was referenced by `DispatchPolicyInputOutputLayout`'s JSON-Schema
 * via the `definition` "padding".
 */
export interface Padding {
max_trucks: 40
max_targets: 16
}
