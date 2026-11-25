/* Generated from contracts/scene-validation-report.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Validator results, scene invariants, waivers and the build-twice hashes written by st45_validate (DC-004-07, spec 004-scene-pipeline). Version 1.1: optional `fixture` member.
 */
export type SceneValidationReport = {
$schema?: string
schema_version: SchemaVersion
kind: "scene-validation-report"
case: CaseId
manifest_id: Slug
params_sha256: Sha256
/**
 * incomplete when a validator did not run
 */
status: ("complete" | "incomplete")
passed: boolean
/**
 * @minItems 2
 * @maxItems 2
 */
validators: [ValidatorRun, ValidatorRun]
/**
 * variant selections validated (FR-004-34)
 * 
 * @minItems 1
 * @maxItems 1024
 */
selections: [Selection, ...(Selection)[]]
invariants: {
layer_units_axis: InvLayerUnitsAxis
class_label_coverage: InvClassLabelCoverage
time_sampled_labels: InvTimeSampledLabels
articulation_roots: InvArticulationRoots
cyclic_joint_graphs: InvCyclicJointGraphs
non_positive_masses: InvNonPositiveMasses
bench_height_deviation: InvBenchHeightDeviation
face_angle_deviation: InvFaceAngleDeviation
ramp_grade_max: InvRampGradeMax
windrow_margin: InvWindrowMargin
terrain_range_excess: InvTerrainRangeExcess
cut_fill_identity_residual: InvCutFillIdentityResidual
forbidden_paths: InvForbiddenPaths
layer_size_max: InvLayerSizeMax
}
/**
 * @maxItems 32
 */
waivers: Waiver[]
determinism: {
class: "bitwise"
/**
 * @minItems 1
 * @maxItems 64
 */
layers: [DeterminismLayer, ...(DeterminismLayer)[]]
identical: boolean
/**
 * SHA-256 of the sorted (role, sha256) list (FR-004-36)
 */
stage_hash: string
}
/**
 * True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false.
 */
fixture?: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "validator_run".
 */
export type ValidatorRun = {
id: ("usd-validation-nvidia" | "simready-validate")
/**
 * read from studio/uv.lock
 */
version: (Version | null)
status: ("ran" | "not_run")
/**
 * why the validator did not run (FR-004-38)
 */
reason?: string
/**
 * @maxItems 5000
 */
results: Result[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * layers whose upAxis, metersPerUnit or kilogramsPerUnit is wrong or unauthored (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_layer_units_axis".
 */
export type InvLayerUnitsAxis = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * share of geometry prims carrying exactly one class label (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_class_label_coverage".
 */
export type InvClassLabelCoverage = {
measured: number
unit: "fraction"
limit: 1
comparison: "ge"
passed: boolean
}
/**
 * label attributes with time samples (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_time_sampled_labels".
 */
export type InvTimeSampledLabels = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * machines without exactly one articulation root (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_articulation_roots".
 */
export type InvArticulationRoots = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * machines whose joint graph is not a tree (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_cyclic_joint_graphs".
 */
export type InvCyclicJointGraphs = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * bodies with mass <= 0 (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_non_positive_masses".
 */
export type InvNonPositiveMasses = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * largest |measured bench height - H| (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_bench_height_deviation".
 */
export type InvBenchHeightDeviation = {
measured: number
unit: "m"
limit: 0.5
comparison: "le"
passed: boolean
}
/**
 * largest |measured face angle - alpha| (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_face_angle_deviation".
 */
export type InvFaceAngleDeviation = {
measured: number
unit: "deg"
limit: 1
comparison: "le"
passed: boolean
}
/**
 * smallest windrow height minus the largest mid-axle height (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_windrow_margin".
 */
export type InvWindrowMargin = {
measured: number
unit: "m"
limit: 0
comparison: "ge"
passed: boolean
}
/**
 * largest excess of terrain z over the source range +/- max_error (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_terrain_range_excess".
 */
export type InvTerrainRangeExcess = {
measured: number
unit: "m"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * relative residual of the P-004-07 identity (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_cut_fill_identity_residual".
 */
export type InvCutFillIdentityResidual = {
measured: number
unit: "rel"
limit: 1e-12
comparison: "le"
passed: boolean
}
/**
 * forbidden asset paths in any layer (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_forbidden_paths".
 */
export type InvForbiddenPaths = {
measured: number
unit: "count"
limit: 0
comparison: "le"
passed: boolean
}
/**
 * largest small .usda layer (NFR-004-05: <= 10 MB) (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_layer_size_max".
 */
export type InvLayerSizeMax = {
measured: number
unit: "bytes"
limit: 10000000
comparison: "le"
passed: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "determinism_layer".
 */
export type DeterminismLayer = {
role: ("root" | "anim" | "sensors" | "weather" | "lights" | "fleet" | "design" | "terrain" | "asset")
path: Relpath
format: ("usda" | "usdc")
method: ("bytes" | "flattened-text")
first_sha256: Sha256
second_sha256: Sha256
equal: boolean
/**
 * first differing line of the two text exports (FR-004-39)
 */
first_difference?: {
line: number
first: string
second: string
}
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "result".
 */
export interface Result {
rule: string
severity: ("error" | "warning" | "info")
prim: (string | null)
/**
 * scrubbed validator message
 */
message: string
waived: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "selection".
 */
export interface Selection {
/**
 * a free variant name (pushback, scenario); a USD identifier
 */
pushback: string
/**
 * a free variant name (pushback, scenario); a USD identifier
 */
scenario: string
time_of_day: ("dawn" | "morning" | "noon" | "afternoon" | "dusk" | "night")
weather: ("clear" | "overcast" | "rain" | "dust" | "fog")
/**
 * name of a `lod` variant; one per terrain LOD (FR-004-08)
 */
lod: ("lod0" | "lod1" | "lod2")
}
/**
 * largest ramp centreline grade; limit g + 0.1 % (FR-004-35)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "inv_ramp_grade_max".
 */
export interface InvRampGradeMax {
measured: number
unit: "pct"
/**
 * g + 0.1 %
 */
limit: number
comparison: "le"
passed: boolean
}
export interface Waiver {
rule: string
reason: string
}
