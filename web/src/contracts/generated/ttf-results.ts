/* Generated from contracts/ttf-results.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "snr".
 */
export type Snr = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "event_result".
 */
export type EventResult = {
event_id: ArtefactId
stratum: Stratum
method: Method
cutoff: Cutoff
t_c_h: TimeH
t_f_h: TimeH
outcome: ("predicted" | "no failure predicted" | "no forecast")
t_hat_f_h?: TimeH
interval_80_h?: TimeInterval
rel_error?: RelError
error_h?: SignedH
scored_at_cap?: boolean
reason?: Reason
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "artefact_id".
 */
export type ArtefactId = string
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "stratum".
 */
export type Stratum = ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100")
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "method".
 */
export type Method = ("inverse_velocity" | "bayesian_ttf" | "tcn" | "patchtst" | "chronos_bolt_zero_shot" | "chronos_bolt_fine_tuned")
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "cutoff".
 */
export type Cutoff = (0.5 | 0.8)
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "time_h".
 */
export type TimeH = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "rel_error".
 */
export type RelError = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "signed_h".
 */
export type SignedH = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "reason".
 */
export type Reason = string
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "duration_h".
 */
export type DurationH = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "learned_method".
 */
export type LearnedMethod = ("tcn" | "patchtst" | "chronos_bolt_zero_shot" | "chronos_bolt_fine_tuned")
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "seed".
 */
export type Seed = number
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "verdict".
 */
export type Verdict = ("better" | "worse" | "no significant difference")

/**
 * Time-to-failure results of s50_evaluate for case C1 (per event, method and cut-off; summaries; SC-010-01 statements; paired comparisons with inverse velocity; the descriptive real-event block without intervals; the S4b block) (DC-010-03, spec 010-slope).
 */
export interface C1TimeToFailureResults {
$schema?: string
schema_version: string
run_id: RunId
snr_basis: ("observed" | "nominal")
snr_obs?: Snr
t_alarm_h: number
horizon_cap_steps: 1024
/**
 * @maxItems 100000
 */
events: EventResult[]
/**
 * @maxItems 50000
 */
alarms: Alarm[]
/**
 * @maxItems 500
 */
summary: Summary[]
/**
 * @maxItems 500
 */
alarm_summary: AlarmSummary[]
/**
 * @maxItems 8
 */
acceptance: []|[Acceptance]|[Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance, Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance]|[Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance, Acceptance]
/**
 * @maxItems 8
 */
comparisons: []|[Comparison]|[Comparison, Comparison]|[Comparison, Comparison, Comparison]|[Comparison, Comparison, Comparison, Comparison]|[Comparison, Comparison, Comparison, Comparison, Comparison]|[Comparison, Comparison, Comparison, Comparison, Comparison, Comparison]|[Comparison, Comparison, Comparison, Comparison, Comparison, Comparison, Comparison]|[Comparison, Comparison, Comparison, Comparison, Comparison, Comparison, Comparison, Comparison]
multiplicity: {
comparisons: 8
family_wise_claim: false
}
real_event: RealEvent
/**
 * @maxItems 500
 */
s4b?: S4B[]
/**
 * true while the results were computed from a contract-fixture series or section: the stages run against it, write fixture: true on every artefact and publish no lead-time claim or other result computed from it (FR-010-46)
 */
fixture?: boolean
/**
 * partial when a stratum or the real event that the comparison names is absent: each existing stratum is reported, no pooled claim or SC-010 verdict is computed over the incomplete set (FR-010-47)
 */
status?: ("complete" | "partial")
/**
 * each stratum (or the real event) that is `not run (absent)`, in the order the comparison names them (FR-010-47)
 * 
 * @maxItems 8
 */
missing_strata?: []|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]|[("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event"), ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100" | "real_event")]
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "time_interval".
 */
export interface TimeInterval {
lower_h: TimeH
upper_h: TimeH
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "alarm".
 */
export interface Alarm {
event_id: ArtefactId
stratum: Stratum
method: Method
alarmed: boolean
alarm_cutoff?: number
lead_time_h?: DurationH
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "summary".
 */
export interface Summary {
method: Method
stratum: Stratum
cutoff: Cutoff
n_events: number
median_rel_error: RelError
mean_rel_error: RelError
p90_rel_error: RelError
median_abs_error_h: DurationH
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "alarm_summary".
 */
export interface AlarmSummary {
method: Method
stratum: Stratum
n_events: number
never_alarmed_fraction: number
median_lead_time_h?: DurationH
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "acceptance".
 */
export interface Acceptance {
criterion: "SC-010-01"
method: LearnedMethod
cutoff: Cutoff
stratum: "snr_obs"
n_events?: number
median_rel_error?: RelError
interval?: RelInterval
bootstrap?: BootstrapPercentile
threshold: 0.1
verdict: ("pass" | "fail" | "not run")
reason?: Reason
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "rel_interval".
 */
export interface RelInterval {
lower: RelError
upper: RelError
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "bootstrap_percentile".
 */
export interface BootstrapPercentile {
resamples: 10000
method: "percentile"
level: 0.95
seed: Seed
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "comparison".
 */
export interface Comparison {
baseline: "inverse_velocity"
method: LearnedMethod
cutoff: Cutoff
stratum: "snr_obs"
n_pairs: number
mean_difference: number
interval: DifferenceInterval
bootstrap: BootstrapPaired
verdict: Verdict
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "difference_interval".
 */
export interface DifferenceInterval {
lower: number
upper: number
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "bootstrap_paired".
 */
export interface BootstrapPaired {
resamples: 10000
method: "paired-percentile"
resample_unit: "sorted-event-id"
level: 0.95
seed: Seed
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "real_event".
 */
export interface RealEvent {
event_id: ArtefactId
status: ("run" | "not run")
reason?: Reason
label: "single real event — no significance test"
snr_obs?: Snr
t_0_h?: TimeH
t_f_h?: TimeH
/**
 * @minItems 12
 * @maxItems 12
 */
rows?: [RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow, RealRow]
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "real_row".
 */
export interface RealRow {
cutoff: Cutoff
method: Method
t_c_h: TimeH
outcome: ("predicted" | "no failure predicted" | "no forecast" | "not run")
t_hat_f_h?: TimeH
signed_error_h?: SignedH
error_ratio?: number
scored_at_cap?: boolean
reason?: Reason
}
/**
 * This interface was referenced by `C1TimeToFailureResults`'s JSON-Schema
 * via the `definition` "s4b".
 */
export interface S4B {
psi_deg: (0 | 45 | 70)
cutoff: Cutoff
method: Method
series: ("los" | "full-vector-noise-free")
n_events: number
median_rel_error: RelError
excluded_ambiguous_pixels: number
}
