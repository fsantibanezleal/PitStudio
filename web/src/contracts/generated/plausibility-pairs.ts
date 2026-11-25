/* Generated from contracts/plausibility-pairs.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "pair".
 */
export type Pair = {
pair_id: ArtefactId
scenario: ("muck-pile-formation" | "truck-dump" | "bench-collapse")
source_run_id: RunId
/**
 * @minItems 1
 * @maxItems 1
 */
corruptions: [Corruption]
calibrated: Clip
corrupted: Clip
confirmation: Confirmation
}
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "corruption".
 */
export type Corruption = ("gravity-x0.3" | "zero-friction" | "mass-injection" | "time-reversal" | "interpenetration" | "frozen-particles")
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * Task-B plausibility pair index written by the pair builder: calibrated and singly corrupted clips with the confirming detector statistic (DC-015-06, spec 015-vlm).
 */
export interface PlausibilityPairIndex {
$schema?: string
schema_version: SchemaVersion
seed: number
/**
 * @minItems 1
 * @maxItems 100
 */
pairs: [Pair, ...(Pair)[]]
}
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "clip".
 */
export interface Clip {
asset_id: ArtefactId
path: Relpath
sha256: Sha256
duration_s: number
frame_count: number
fps: number
camera_id: ArtefactId
scene_id: ArtefactId
}
/**
 * This interface was referenced by `PlausibilityPairIndex`'s JSON-Schema
 * via the `definition` "confirmation".
 */
export interface Confirmation {
statistic: ("fitted_g_ratio" | "repose_angle_deg" | "mass_increase_pct" | "reversed_frame_fraction" | "deep_overlap_contact_fraction" | "frozen_particle_fraction")
value: number
sustained_s: (number | null)
own_detector_triggered: true
calibrated_detectors_clear: true
}
