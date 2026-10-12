/* Generated from contracts/parity-fixture.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Parity fixture web/tests/fixtures/parity/<engine-id>/<fixture>.json[.gz] written by tools/make_parity_fixtures.py (DC-018-04, spec 018-web-cases).
 */
export type PitStudioParityFixture = {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
/**
 * engine ids of the engine table (spec 018 section 7.1)
 */
engine: ("des" | "policies" | "haulage" | "lp" | "routing" | "il1-twin" | "il2-twin" | "granular" | "gns" | "traffic" | "dust-lidar" | "detector" | "geotech" | "forecasters" | "swe" | "fno" | "plume" | "dust-particles" | "blasting" | "watershed" | "unet" | "comminution" | "meta-model" | "mincut" | "volume")
/**
 * fixture id, equal to the file stem
 */
fixture: string
/**
 * engine function the fixture exercises
 */
function?: string
reference: Reference
tolerance: Tolerance
/**
 * @minItems 1
 * @maxItems 100000
 */
cases: [Vector, ...(Vector)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * parity class and its tolerance; each value is capped at the spec value, so a looser tolerance fails
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "tolerance".
 */
export type Tolerance = {
class: ParityClass
/**
 * relative tolerance
 */
rtol?: number
/**
 * absolute tolerance as a multiple of the output unit scale s_y (DC-018-02)
 */
atol_scale?: number
/**
 * convergence tolerance of the reference solver; rtol = max(1e-9, 10 x solver_tol)
 */
solver_tol?: number
objective_rtol?: number
/**
 * maximum absolute difference (non-dimensional for WGSL kernels)
 */
max_abs?: number
/**
 * box tolerance in pixels
 */
max_abs_px?: number
top1_agreement_min?: number
/**
 * binomial bound in standard errors, plus 1/N
 */
sigma?: number
observables?: {
repose_deg?: number
runout_rel?: number
discharge_rel?: number
mass_drift_rel?: number
}
/**
 * requirement of the owning spec that fixes the class and tolerance
 */
defined_by?: ("FR-007-10" | "FR-007-15" | "FR-007-20" | "FR-007-32" | "FR-007-39" | "P-013-15" | "FR-014-42")
}
/**
 * system class of spec 018 section 7.2; hosted = an engine of specs 007, 013 or 014 judged by its own suite
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "parity_class".
 */
export type ParityClass = ("analytical-closed-form" | "analytical-iterative" | "monte-carlo-count" | "monte-carlo-binomial" | "exact-stream" | "min-cut" | "rigid-body-hash" | "label-map-exact" | "wgsl-kernel" | "wgsl-observables" | "ml-wasm-fp32" | "ml-webgpu-fp32" | "ml-fp16" | "detector-wasm" | "detector-webgpu" | "hosted")
/**
 * JSON value of an engine input or output (64-bit integers as decimal or hex strings)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "value".
 */
export type Value = (number | boolean | null | string | Value[] | ValueMap1)
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "module_path".
 */
export type ModulePath = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "reference".
 */
export interface Reference {
/**
 * reference package (PyPI or npm name)
 */
name: string
version: Version
/**
 * reference function, e.g. minephys.blasting.kuz_ram_x50
 */
callable?: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "vector".
 */
export interface Vector {
name?: string
input: ValueMap
output: ValueMap2
variates?: Variates
}
/**
 * engine input in SI units (DC-018-02)
 */
export interface ValueMap {
[k: string]: Value | undefined
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "value_map".
 */
export interface ValueMap1 {
[k: string]: Value | undefined
}
/**
 * reference output
 */
export interface ValueMap2 {
[k: string]: Value | undefined
}
/**
 * recorded variate stream of a Monte-Carlo vector
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "variates".
 */
export interface Variates {
/**
 * numpy PCG64 seeded through SeedSequence
 */
generator: "pcg64"
/**
 * SeedSequence entropy as a decimal integer
 */
entropy: string
/**
 * @maxItems 8
 */
spawn_key: []|[number]|[number, number]|[number, number, number]|[number, number, number, number]|[number, number, number, number, number]|[number, number, number, number, number, number]|[number, number, number, number, number, number, number]|[number, number, number, number, number, number, number, number]
/**
 * sample matrix, one row per Monte-Carlo sample
 * 
 * @minItems 1
 * @maxItems 100000
 */
samples: [[number, ...(number)[]], ...([number, ...(number)[]])[]]
}
