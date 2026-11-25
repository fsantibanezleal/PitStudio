/* Generated from contracts/data-card.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Front matter of data/cards/<id>.md for real and synthetic sets (DC-008-05, spec 008-data-pipeline).
 */
export type DataCardFrontMatter = (RealCard | SyntheticCard)
export type RealCard = {
$schema?: string
id: Slug
title: string
spdx: SpdxId
licence_class: LicenceClass
redistribution: ("redistributable" | "derived-only" | "no-redistribution")
attribution?: string
/**
 * @maxItems 512
 */
files_sha256: (Sha256 | null)[]
kind: "real"
landing_url: HttpsUrl
citation: string
}
export type Slug = string
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
export type Sha256 = string
export type HttpsUrl = string
export type SyntheticCard = {
$schema?: string
id: Slug
title: string
spdx: SpdxId
licence_class: LicenceClass
redistribution: ("redistributable" | "derived-only" | "no-redistribution")
attribution?: string
/**
 * @maxItems 512
 */
files_sha256: (Sha256 | null)[]
kind: "synthetic"
synthetic: true
generator: {
module: ModulePath
stage: StageId
version: Version
git_sha: GitSha
}
config_sha256: Sha256
/**
 * @minItems 1
 * @maxItems 1024
 */
seeds: [number, ...(number)[]]
/**
 * @maxItems 256
 */
priors: {
name: string
citation: string
page: string
}[]
/**
 * @maxItems 1024
 */
assets: {
name: string
spdx: SpdxId
licence_class: LicenceClass
sha256: Sha256
}[]
validation: Validation
}
export type ModulePath = string
export type StageId = ("s00_download" | "s05_synthesize" | "s10_preprocess" | "s20_feature_extraction" | "s30_train" | "s40_infer" | "s50_evaluate" | "s60_export" | "s62_accel" | "s64_bench" | "st10_terrain" | "st20_pit_design" | "st30_assets" | "st40_compose" | "st45_validate" | "st45b_kit_validate" | "st50_physics" | "st52_rtx_render" | "st53_sensors" | "st54_vehicles" | "st55_sdg" | "st56_encode" | "st57_rain_lidar" | "st58_kit_capture" | "st58b_capture_splat" | "st59_reason_bench" | "st59a_vqa" | "st59b_plausibility" | "st59c_captions" | "st60_il_train" | "st61_il_mpm_eval")
export type Version = string
export type GitSha = string
export type Validation = {
class: ("validated-against-real" | "descriptive-only" | "unvalidated")
real_reference?: Slug
/**
 * @minItems 1
 * @maxItems 16
 */
tests?: [ValidationTest]|[ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]|[ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest, ValidationTest]
label?: "calibrated synthetic — not validated against real data"
c2st_tstr?: "not-applicable"
basis?: "single real event"
/**
 * @maxItems 32
 */
physics_benchmarks?: {
benchmark: string
verdict: ("pending" | "pass" | "fail")
}[]
}

export interface ValidationTest {
test: ("c2st" | "tstr")
verdict: ("pending" | "pass" | "warn" | "fail")
metric: ({
name: ("auc" | "auc-minus-real-baseline" | "tstr-trtr-ratio")
value: number
ci95_low: number
ci95_high: number
} | null)
}
