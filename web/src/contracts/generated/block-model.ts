/* Generated from contracts/block-model.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Block model with values, grid indices and precedence arcs for the ultimate pit (DC-017-02, spec 017-planning-survey).
 */
export type E1BlockModel = {
$schema?: string
schema_version: string
id: Slug
synthetic: boolean
source: Source
licence: Licence
grid: Grid
precedence: Precedence
value_form: ("components" | "destination-values")
economics?: Economics
reference_optimum?: {
value: number
unit: ("usd-cents" | "instance-units")
source: ("oreblocks-stamp" | "minelib-best-known")
}
/**
 * @minItems 1
 * @maxItems 1000000
 */
blocks: [Block, ...(Block)[]]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "source".
 */
export type Source = {
kind: ("oreblocks" | "minelib" | "own-grid")
seed?: number
oreblocks_version?: Semver
instance?: Slug
/**
 * @minItems 1
 * @maxItems 8
 */
files?: [{
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]|[{
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}, {
name: Relpath
sha256: Sha256
}]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "semver".
 */
export type Semver = string
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
 * via the `definition` "licence".
 */
export type Licence = {
spdx: SpdxId
licence_class: LicenceClass
attribution?: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")
/**
 * Origin of the per-block arcs: the instance's own arcs or the level-cone generator (FR-017-13).
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "precedence".
 */
export type Precedence = {
source: ("own" | "generated")
slope_deg?: number
levels?: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "value_usd".
 */
export type ValueUsd = number

/**
 * Regular grid; index k increases upward; origin is the minimum corner.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "grid".
 */
export interface Grid {
/**
 * @minItems 3
 * @maxItems 3
 */
origin_m: [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
block_size_m: [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
shape: [number, number, number]
}
/**
 * Components of v_i(lambda) (FR-017-12): p, s_r, r, c_p and c_m.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "economics".
 */
export interface Economics {
metal_price_usd_per_t: number
selling_cost_usd_per_t: number
recovery: number
processing_cost_usd_per_t: number
mining_cost_usd_per_t: number
}
/**
 * One block; grade is a mass fraction; prec lists the ids of the blocks that must be mined first.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "block".
 */
export interface Block {
id: number
/**
 * @minItems 3
 * @maxItems 3
 */
ijk: [number, number, number]
/**
 * @minItems 3
 * @maxItems 3
 */
centre_m: [number, number, number]
tonnage_t: number
grade?: number
values_usd?: {
mill?: ValueUsd
waste?: ValueUsd
leach?: ValueUsd
stockpile?: ValueUsd
}
/**
 * @minItems 0
 * @maxItems 256
 */
prec?: number[]
}
