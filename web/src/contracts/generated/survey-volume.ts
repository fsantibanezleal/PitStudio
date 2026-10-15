/* Generated from contracts/survey-volume.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "volume".
 */
export type Volume = {
id: Slug
scope: ("real" | "synthetic")
method: ("dem-differencing" | "photogrammetric" | "splat")
status: ("ok" | "not_run" | "failed")
reason?: string
label?: "measurement, not validation"
licence?: Licence
flight?: Slug
seed?: number
surfaces?: {
before: Surface
after: Surface
}
grid?: Grid
resampling?: Resampling
vertical_transform?: VerticalTransform
polygon?: Polygon
v_cut_m3?: number
v_fill_m3?: number
v_net_m3?: number
cells?: {
valid: number
nodata: number
nodata_fraction: number
}
uncertainty_m3?: {
uncorrelated: number
correlated: number
}
errors?: Errors
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "licence".
 */
export type Licence = {
spdx: SpdxId
licence_class: LicenceClass
attribution?: string
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "crs".
 */
export type Crs = string
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "resampling".
 */
export type Resampling = {
method: ("none" | "bilinear")
source_crs?: Crs
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "vertical_transform".
 */
export type VerticalTransform = {
kind: ("none" | "constant" | "grid")
offset_m?: number
grid?: {
path: Relpath
sha256: Sha256
}
source?: string
}

/**
 * Cut, fill and net volumes with uncertainty and error metrics written by s50_evaluate (DC-017-04, spec 017-planning-survey).
 */
export interface E2SurveyVolumes {
$schema?: string
schema_version: string
/**
 * @minItems 1
 * @maxItems 1024
 */
volumes: [Volume, ...(Volume)[]]
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "surface".
 */
export interface Surface {
path: Relpath
sha256: Sha256
epoch?: string
project?: string
crs?: Crs
vertical_datum?: string
rmse_z_m?: number
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "grid".
 */
export interface Grid {
cell_m: number
/**
 * @minItems 2
 * @maxItems 2
 */
shape: [number, number]
/**
 * @minItems 2
 * @maxItems 2
 */
origin_m: [number, number]
crs: Crs
}
/**
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "polygon".
 */
export interface Polygon {
/**
 * @minItems 3
 * @maxItems 10000
 */
vertices: [[number, number], [number, number], [number, number], ...([number, number])[]]
source: string
overlap_ratio?: number
}
/**
 * Error metrics of FR-017-39; reported only, with no pass field (SC-017-06).
 * 
 * This interface was referenced by `E2SurveyVolumes`'s JSON-Schema
 * via the `definition` "errors".
 */
export interface Errors {
fill_pct: number
cut_pct: number
floor_fill_pct: number
floor_cut_pct: number
reprojection_rmse_px: (number | null)
alignment_rmse_m: (number | null)
depth_abs_median_m: (number | null)
gsd_cm_per_px: number
registration_ratio: (number | null)
}
