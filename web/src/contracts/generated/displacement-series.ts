/* Generated from contracts/displacement-series.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Slope displacement series of one seeded synthetic Voight event, the real de Wit event, one S4b radar pixel or one S4b line-of-sight map, written by s05_synthesize, s10_preprocess and the radar-series builder (DC-010-02, spec 010-slope).
 */
export type DisplacementSeries = (SyntheticEvent | RealEvent | RadarPixel | RadarMap)
export type SyntheticEvent = {
$schema?: string
kind: "synthetic-event"
synthetic: true
event_id: ArtefactId
seed: Seed
split: ("train" | "validation" | "test")
stratum: Stratum
snr_note?: "observed SNR not available — nominal SNR"
parameters: VoightParameters
t_0_h: TimeH
t_f_h: TimeH
t_f_source: "synthetic (exact)"
realised_snr: Snr
sampling: Sampling
attribution?: string
/**
 * @minItems 64
 * @maxItems 1000000
 */
t_h: [TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, TimeH, ...(TimeH)[]]
/**
 * @minItems 64
 * @maxItems 1000000
 */
los_displacement_mm: [DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, DisplacementMm, ...(DisplacementMm)[]]
}
export type ArtefactId = string
export type Seed = number
export type Stratum = ("snr_obs" | "half_snr_obs" | "double_snr_obs" | "snr_obs_atmospheric" | "nominal_10" | "nominal_30" | "nominal_100")
export type Snr = number
export type TimeH = number
export type DisplacementMm = number
export type Slug = string
export type Sha256 = string
export type Relpath = string
export type UtcTimestamp = string
export type HttpsUrl = string
export type PixelId = number
/**
 * @minItems 3
 * @maxItems 3
 */
export type PointM = [number, number, number]
export type SignConvention = "positive = away from the radar"
export type PixelStatus = ("ok" | "ambiguous (phase wrapping)")

export interface VoightParameters {
alpha: number
a_coefficient: number
terminal_duration_h: number
onset_velocity_mm_per_day: number
steady_phase_fraction: number
regressive: boolean
regressive_velocity_reduction?: number
regressive_duration_fraction?: number
psi_deg: number
snr_target: Snr
sigma_d_mm: number
ar1?: Ar1
}
export interface Ar1 {
rho: number
marginal_sd_mm: number
}
export interface Sampling {
n_samples: number
interval_h: number
regular: boolean
}
export interface RealEvent {
$schema?: string
kind: "real-event"
synthetic: false
event_id: ArtefactId
source_id: Slug
archive_bytes: 8943265
archive_md5: "3adeb6c853d2e87249b7d3549a2a00ca"
archive_sha256: Sha256
archive_member: Relpath
extraction: ("series-as-delivered" | "map-median-top-5pct")
source_units: {
displacement: ("mm" | "cm" | "m")
time: ("s" | "min" | "h" | "d")
}
t_ref_utc?: UtcTimestamp
t_0_h: TimeH
t_f_h: TimeH
t_f_source: TFDocument
snr_obs: Snr
sampling: Sampling
attribution: string
licence: {
spdx: "CC-BY-4.0"
licence_class: "attribution"
}
use: "descriptive-evaluation-only"
/**
 * @minItems 2
 * @maxItems 1000000
 */
t_h: [TimeH, TimeH, ...(TimeH)[]]
/**
 * @minItems 2
 * @maxItems 1000000
 */
los_displacement_mm: [DisplacementMm, DisplacementMm, ...(DisplacementMm)[]]
}
export interface TFDocument {
kind: ("dataset-description" | "dataset-file" | "publication")
citation: string
url?: HttpsUrl
}
export interface RadarPixel {
$schema?: string
kind: "radar-pixel"
synthetic: true
event_id: ArtefactId
stratum?: Stratum
pixel_id: PixelId
pixel_position_m: PointM
radar: Radar
psi_deg: number
sign_convention: SignConvention
run_seed: Seed
status: PixelStatus
ambiguous_from_scan?: number
/**
 * @minItems 2
 * @maxItems 1000000
 */
t_h: [TimeH, TimeH, ...(TimeH)[]]
/**
 * @minItems 2
 * @maxItems 1000000
 */
los_displacement_mm: [DisplacementMm, DisplacementMm, ...(DisplacementMm)[]]
/**
 * @minItems 2
 * @maxItems 1000000
 */
measured_los_displacement_mm: [DisplacementMm, DisplacementMm, ...(DisplacementMm)[]]
/**
 * @minItems 2
 * @maxItems 1000000
 */
wrap_flags: [boolean, boolean, ...(boolean)[]]
}
export interface Radar {
position_m: PointM
wavelength_mm: number
scan_interval_min: number
}
export interface RadarMap {
$schema?: string
kind: "radar-map"
synthetic: true
event_id: ArtefactId
radar: Radar
sign_convention: SignConvention
scan_index: number
t_h: TimeH
ambiguous_pixels: number
/**
 * @minItems 1
 * @maxItems 1000000
 */
pixels: [MapPixel, ...(MapPixel)[]]
}
export interface MapPixel {
pixel_id: PixelId
position_m: PointM
los_displacement_mm: DisplacementMm
status: PixelStatus
}
