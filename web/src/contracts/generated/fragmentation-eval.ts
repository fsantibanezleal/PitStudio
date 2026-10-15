/* Generated from contracts/fragmentation-eval.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Evaluation report of case D1 written by s50_evaluate: TSTR / TRTR per fold, x50 errors, paired comparisons, realism checks and statuses (DC-012-03, spec 012-fragmentation).
 */
export type FragmentationEvaluationReport = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
run_id: RunId
archive_status: ("verified" | "unavailable" | "sha256-mismatch")
/**
 * Isaac Sim status in the capability report
 */
isaac_sim: ("passing" | "not-passing")
/**
 * U-Net trained on real training lists, per fold
 */
trtr: {
status: ("succeeded" | "not_run")
reason?: string
/**
 * one value per fold, fold order
 * 
 * @minItems 5
 * @maxItems 5
 */
fold_iou?: [number, number, number, number, number]
}
/**
 * U-Net trained on synthetic tiles only, scored on the real test originals
 */
tstr: {
status: ("succeeded" | "not_run")
reason?: string
/**
 * one value per fold, fold order
 * 
 * @minItems 5
 * @maxItems 5
 */
fold_iou?: [number, number, number, number, number]
/**
 * IoU_TSTR / IoU_TRTR per fold
 * 
 * @minItems 5
 * @maxItems 5
 */
rho?: [number, number, number, number, number]
rho_mean?: number
rho_min?: number
rho_std?: number
threshold?: 0.9
verdict?: ("pass" | "fail")
}
/**
 * classical watershed + Swebrec baseline on the real test originals
 */
watershed: {
status: ("succeeded" | "not_run")
reason?: string
/**
 * one value per fold, fold order
 * 
 * @minItems 5
 * @maxItems 5
 */
fold_iou?: [number, number, number, number, number]
/**
 * parameters chosen per fold on its training originals
 * 
 * @minItems 5
 * @maxItems 5
 */
parameters?: [{
sigma_g_px: (0.5 | 1 | 2)
min_distance_px: (3 | 5 | 7 | 9)
offset: (-0.05 | 0 | 0.05)
}, {
sigma_g_px: (0.5 | 1 | 2)
min_distance_px: (3 | 5 | 7 | 9)
offset: (-0.05 | 0 | 0.05)
}, {
sigma_g_px: (0.5 | 1 | 2)
min_distance_px: (3 | 5 | 7 | 9)
offset: (-0.05 | 0 | 0.05)
}, {
sigma_g_px: (0.5 | 1 | 2)
min_distance_px: (3 | 5 | 7 | 9)
offset: (-0.05 | 0 | 0.05)
}, {
sigma_g_px: (0.5 | 1 | 2)
min_distance_px: (3 | 5 | 7 | 9)
offset: (-0.05 | 0 | 0.05)
}]
}
/**
 * x50 mean relative error of the TSTR U-Net on synthetic held-out views
 */
synthetic_x50: {
status: ("succeeded" | "not_run")
reason?: string
held_out_piles?: number
views?: number
mre_unet?: number
/**
 * 95 % pile-bootstrap interval
 * 
 * @minItems 2
 * @maxItems 2
 */
mre_unet_interval?: [number, number]
mre_watershed?: number
occlusion_bias_mean?: number
threshold?: 0.15
verdict?: ("pass" | "fail")
}
/**
 * paired cluster bootstrap on the 240 real test originals
 */
real_comparison: {
status: ("succeeded" | "not_run")
reason?: string
pairing_unit?: "original"
units?: 240
clusters?: 72
bootstrap_b?: 10000
/**
 * mean of e_watershed - e_unet
 */
mean_difference?: number
interval?: Interval
/**
 * U-Net against watershed + Swebrec
 */
verdict?: ("better" | "no significant difference" | "worse")
no_fit?: NoFit
}
/**
 * paired bootstrap over synthetic held-out piles
 */
synthetic_comparison: {
status: ("succeeded" | "not_run")
reason?: string
pairing_unit?: "pile"
units?: number
bootstrap_b?: 10000
/**
 * mean of e_watershed - e_unet
 */
mean_difference?: number
interval?: Interval
/**
 * U-Net against watershed + Swebrec
 */
verdict?: ("better" | "no significant difference" | "worse")
no_fit?: NoFit
}
/**
 * classifier two-sample test, real-versus-real baseline, injected shift and train-versus-test
 */
c2st: {
status: ("succeeded" | "not_run")
reason?: string
embedding?: {
model: "dinov2-vitb14"
weights_sha256: Sha256
input_px: 224
token: "cls"
}
n_synthetic?: number
n_real?: number
bootstrap_b?: 1000
shift?: {
corruption: "dust"
severity: 3
depth_m: 100
}
/**
 * @minItems 2
 * @maxItems 2
 */
families?: [Family, Family]
/**
 * both injected-shift AUCs >= 0.80
 */
powered?: boolean
verdict?: ("pass" | "fail" | "inconclusive (no power)")
}
/**
 * duplicate scan over all synthetic tiles and the 960 real files
 */
duplicates: {
status: ("succeeded" | "not_run")
reason?: string
phash_hamming_max?: 4
cosine_min?: 0.95
synthetic_tiles?: number
real_files?: 960
synthetic_real_flags?: number
train_test_flags?: number
/**
 * a leak stops the run with split-leak
 */
cross_group_leaks?: 0
}
/**
 * dataset-card attribution, verbatim
 */
attribution: "Si, Zhu, Di, Wang (2019). Rock fragment image segmentation combining CNN and watershed algorithm. Mendeley Data, V1. https://doi.org/10.17632/78ht3pjsr4.1. Licensed under CC BY 4.0."
label?: "TRTR only — synthetic arm not run"
d1_statement?: "synthetic-only U-Net claim; no measured sim-to-real"
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "run_id".
 */
export type RunId = string
/**
 * 95 % percentile interval: lower, upper
 * 
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "interval".
 */
export type Interval = [number, number]
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * 95 % cluster-bootstrap interval
 * 
 * @minItems 2
 * @maxItems 2
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "auc_interval".
 */
export type AucInterval = [number, number]

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "no_fit".
 */
export interface NoFit {
unet: number
watershed: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "family".
 */
export interface Family {
family: ("logistic" | "mlp")
auc: number
auc_interval: AucInterval
real_vs_real_auc: number
real_vs_real_interval: AucInterval
auc_minus_real_vs_real: number
shift_auc: number
train_vs_test_auc: number
}
