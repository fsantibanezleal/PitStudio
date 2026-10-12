/* Generated from contracts/vlm-record.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "date".
 */
export type Date = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "git_sha".
 */
export type GitSha = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "record_a".
 */
export type RecordA = {
task: "A"
record_id: ArtefactId
query_id: ArtefactId
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base" | "detector-rule" | "constant")
/**
 * @minItems 1
 * @maxItems 1
 */
frames: [ArtefactId]
question_type: number
condition: ("day" | "night" | "dust" | "rain")
question: string
output: string
parsed: ("yes" | "no" | "0" | "1" | "2" | "3+" | "unparseable")
truth: ("yes" | "no" | "0" | "1" | "2" | "3+")
correct: boolean
licence_class: RecordLicenceClass
provenance: (Provenance | null)
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "record_licence_class".
 */
export type RecordLicenceClass = ("display-only" | "own")
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "provenance".
 */
export type Provenance = {
model: ("nvidia/Cosmos-Reason2-2B" | "Qwen/Qwen3-VL-2B-Instruct")
revision: GitSha
quantisation: ("q8_0" | "bf16")
gguf_sha256: (Sha256 | null)
llamacpp_build: ("b11381" | null)
llamacpp_archive_sha256: (Sha256 | null)
transformers_version: (Version | null)
sampling: Sampling
date: Date
gpu: Gpu
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "sampling".
 */
export type Sampling = {
temperature: 0
top_k: 1
seed: number
max_new_tokens: number
reasoning: boolean
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "driver".
 */
export type Driver = string
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "record_b".
 */
export type RecordB = {
task: "B"
record_id: ArtefactId
pair_id: ArtefactId
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base")
corruption: ("gravity-x0.3" | "zero-friction" | "mass-injection" | "time-reversal" | "interpenetration" | "frozen-particles")
presentation: ("pair-calibrated-first" | "pair-corrupted-first" | "single-calibrated" | "single-corrupted")
input_mode: ("native-video" | "frame-list-approximation")
/**
 * @minItems 1
 * @maxItems 2
 */
frames: [ArtefactId]|[ArtefactId, ArtefactId]
question: string
output: string
parsed: ("first" | "second" | "yes" | "no" | "unparseable")
truth: ("first" | "second" | "yes" | "no")
correct: boolean
licence_class: RecordLicenceClass
provenance: Provenance
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "record_c".
 */
export type RecordC = {
task: "C"
record_id: ArtefactId
arm: ("cosmos-q8_0" | "cosmos-bf16" | "qwen-base" | "template-caption")
/**
 * @minItems 1
 * @maxItems 1
 */
frames: [ArtefactId]
condition: ("day" | "night" | "dust" | "rain")
question: string
output: string
mentioned_classes: ClassSet
visible_classes: ClassSet
hallucinated_classes: ClassSet
correct: boolean
licence_class: RecordLicenceClass
provenance: (Provenance | null)
}
/**
 * @maxItems 5
 * 
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "class_set".
 */
export type ClassSet = []|[("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")]|[("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")]|[("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")]|[("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")]|[("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder"), ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")]

/**
 * Published, display-only answer records of the reason lane (stratified sample), written by studio publish (DC-015-04, spec 015-vlm).
 */
export interface PublishedAnswerRecords {
$schema?: string
schema_version: SchemaVersion
case: CaseId
generated: Date
git_sha: GitSha
notices: Notices
sample: {
method: "stratified-random"
/**
 * @minItems 1
 * @maxItems 4
 */
strata: [("task" | "type" | "condition" | "corruption")]|[("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption")]|[("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption")]|[("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption"), ("task" | "type" | "condition" | "corruption")]
seed: number
n_full: number
n_published: number
selection_uses_correctness: false
}
/**
 * @minItems 1
 * @maxItems 2000
 */
records: [(RecordA | RecordB | RecordC), ...((RecordA | RecordB | RecordC))[]]
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "notices".
 */
export interface Notices {
cosmos: "Built on NVIDIA Cosmos"
honesty: "Zero-shot 2B VLM; not a safety system."
}
/**
 * This interface was referenced by `PublishedAnswerRecords`'s JSON-Schema
 * via the `definition` "gpu".
 */
export interface Gpu {
name: string
driver: Driver
}
