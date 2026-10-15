/* Generated from contracts/detection-eval.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Perception evaluation report of s50_evaluate (per model, precision, family and class AP with intervals and support; corruption curves; DR ablation; sim-to-real status, honesty label and verdicts) (DC-009-05, spec 009-perception). A fixture report (fixture true) comes from a contract-fixture SDG index and publishes no metric: its rows may omit every metric. A partial report (partial true) lists the models it names but did not evaluate as not run (absent) and carries no pooled row, no DR ablation and no pass or fail verdict.
 */
export type DetectionEvaluationReport = {
$schema?: string
schema_version: string
run_id: RunId
test_data: "synthetic held-out"
honesty_label: HonestyLabel
sim_to_real: ("not measured" | "measured")
protocol: Protocol
bootstrap: ClusterBootstrap
/**
 * @minItems 1
 * @maxItems 2
 */
families: [FamilyStatus]|[FamilyStatus, FamilyStatus]
/**
 * @maxItems 1000
 */
per_class: ClassResult[]
/**
 * @maxItems 200
 */
summary: SummaryResult[]
/**
 * @maxItems 2000
 */
corruption: CorruptionPoint[]
dr_ablation?: DrAblation
/**
 * @maxItems 200
 */
acceptance: Acceptance[]
real_probe?: RealProbe
/**
 * @maxItems 100
 */
rejected_inputs?: RejectedInput[]
fixture?: boolean
partial?: boolean
/**
 * @maxItems 60
 */
models?: ModelStatus[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "honesty_label".
 */
export type HonestyLabel = "calibrated synthetic — not validated against real data"
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "seed".
 */
export type Seed = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "reason".
 */
export type Reason = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "class_result".
 */
export type ClassResult = {
model: Model
precision: Precision
training_arm: TrainingArm
family: ("pit" | "crusher" | "pooled")
task: ("box" | "mask")
class: ClassName
support: number
ap50?: Unit
ap50_95?: Unit
ap50_interval?: Interval
ap50_95_interval?: Interval
descriptive: boolean
honesty_label: HonestyLabel
sim_to_real: ("not measured" | "measured")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "model".
 */
export type Model = ("d-fine-n" | "d-fine-s" | "rf-detr-seg-n")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "precision".
 */
export type Precision = ("fp32" | "fp16" | "int8")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "training_arm".
 */
export type TrainingArm = ("S" | "U")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "class_name".
 */
export type ClassName = ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "unit".
 */
export type Unit = number
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "summary_result".
 */
export type SummaryResult = {
model: Model
precision: Precision
training_arm: TrainingArm
family: ("pit" | "crusher" | "pooled")
task: ("box" | "mask")
metric: ("map50" | "mask_ap50")
value?: Unit
interval?: Interval
/**
 * @maxItems 5
 */
classes_included: []|[ClassName]|[ClassName, ClassName]|[ClassName, ClassName, ClassName]|[ClassName, ClassName, ClassName, ClassName]|[ClassName, ClassName, ClassName, ClassName, ClassName]
descriptive: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "acceptance".
 */
export type Acceptance = {
criterion: ("SC-009-01" | "SC-009-02" | "SC-009-03" | "SC-009-05" | "SC-009-06")
model: Model
precision: Precision
corruption?: ("dust" | "night" | "rain")
severity?: number
statistic: ("map50" | "mask_ap50" | "delta_rel_pct" | "abs_delta_mask_ap50_pp")
value?: number
threshold: number
verdict: ("pass" | "fail" | "not evaluable (insufficient support)" | "not run")
/**
 * @minItems 1
 * @maxItems 15
 */
insufficient_support?: [SupportShortfall]|[SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]|[SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall, SupportShortfall]
reason?: Reason
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "probe_class".
 */
export type ProbeClass = ("haul_truck" | "shovel" | "light_vehicle" | "person")
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
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "protocol".
 */
export interface Protocol {
implementation: "pycocotools"
implementation_version: Version
iou_thresholds: "0.50:0.05:0.95"
recall_points: 101
max_dets: 100
area: "all"
min_support: 100
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "cluster_bootstrap".
 */
export interface ClusterBootstrap {
resamples: 2000
method: "cluster-percentile"
cluster: "test-scenario-seed"
level: 0.95
seed: Seed
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "family_status".
 */
export interface FamilyStatus {
family: ("pit" | "crusher")
status: ("run" | "not run")
reason?: Reason
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "interval".
 */
export interface Interval {
lower: Unit
upper: Unit
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "corruption_point".
 */
export interface CorruptionPoint {
model: Model
precision: Precision
training_arm: TrainingArm
metric: ("map50" | "mask_ap50")
corruption: ("dust" | "night" | "rain")
severity: number
m_clean?: number
m_corrupted?: Unit
delta_rel_pct?: number
descriptive: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "dr_ablation".
 */
export interface DrAblation {
model: "d-fine-s"
precision: "fp32"
metric: "map50"
family: "pit"
arm_a: "S"
arm_b: "U"
difference?: number
interval?: DifferenceInterval
bootstrap: {
resamples: 10000
method: "paired-cluster-percentile"
cluster: "test-scenario-seed"
level: 0.95
identical_resample_indices: true
seed: Seed
}
verdict?: ("better" | "worse" | "no significant difference")
training_runs_per_arm: number
test_seeds: number
test_images: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "difference_interval".
 */
export interface DifferenceInterval {
lower: number
upper: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "support_shortfall".
 */
export interface SupportShortfall {
family: ("pit" | "crusher" | "pooled")
class: ClassName
count: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "real_probe".
 */
export interface RealProbe {
images: number
excluded_images: number
ground_truth: "labeller-a"
/**
 * @minItems 1
 * @maxItems 8
 */
per_class: [ProbeClassResult]|[ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult]|[ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult, ProbeClassResult]
/**
 * @minItems 1
 * @maxItems 2
 */
labeller_b_map50: [{
model: ("d-fine-n" | "d-fine-s")
map50: Unit
}]|[{
model: ("d-fine-n" | "d-fine-s")
map50: Unit
}, {
model: ("d-fine-n" | "d-fine-s")
map50: Unit
}]
/**
 * @minItems 1
 * @maxItems 4
 */
agreement: [{
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}]|[{
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}]|[{
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}]|[{
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}, {
class: ProbeClass
box_f1: Unit
iou_threshold: 0.5
}]
bootstrap: {
resamples: 2000
method: "image-percentile"
level: 0.95
seed: Seed
}
aggregate_only: true
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "probe_class_result".
 */
export interface ProbeClassResult {
model: ("d-fine-n" | "d-fine-s")
class: ProbeClass
support: number
ap50: Unit
ap50_interval: Interval
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "rejected_input".
 */
export interface RejectedInput {
input: Relpath
reason: Reason
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "model_status".
 */
export interface ModelStatus {
model: Model
precision: Precision
arm: TrainingArm
status: ("evaluated" | "not run (absent)")
provenance?: Provenance
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "provenance".
 */
export interface Provenance {
checkpoint_sha256?: Sha256
training_set_sha256?: Sha256
base_checkpoint_sha256?: Sha256
seed?: Seed
epochs?: number
}
