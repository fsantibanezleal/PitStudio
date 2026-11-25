/* Generated from contracts/muck-pile-render.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "licence_class".
 */
export type LicenceClass = ("public-domain" | "open-no-attribution" | "own" | "attribution" | "share-alike" | "display-only" | "reference-only")

/**
 * Render-index record of one view of a settled synthetic muck pile written by st55_sdg (DC-012-04, spec 012-fragmentation).
 */
export interface MuckPileRenderIndex {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
synthetic: true
stage: "st55_sdg"
pile_seed: number
view: number
image: {
width_px: 1024
height_px: 1024
colour_space: "sRGB"
}
render: File
/**
 * instance ids equal fragment ids; 0 = background
 */
instance_mask: {
path: Relpath
sha256: Sha256
dtype: ("uint16" | "uint32")
}
depth: {
path: Relpath
sha256: Sha256
dtype: "float32"
unit: "m"
}
/**
 * pinhole intrinsics of the 1,024 x 1,024 view
 */
intrinsics: {
focal_length_px: number
cx_px: number
cy_px: number
}
/**
 * @minItems 4
 * @maxItems 4
 */
tiles: [Tile, Tile, Tile, Tile]
/**
 * visible instance id -> fragment id (at most one instance per 4 px of the view)
 */
instance_to_fragment: {
[k: string]: number | undefined
}
fragment_table: File
licence: {
spdx: SpdxId
licence_class: LicenceClass
}
}
/**
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "file".
 */
export interface File {
path: Relpath
sha256: Sha256
}
/**
 * one non-overlapping 512 x 512 tile of the view
 * 
 * This interface was referenced by `MuckPileRenderIndex`'s JSON-Schema
 * via the `definition` "tile".
 */
export interface Tile {
tile: number
x0_px: (0 | 512)
y0_px: (0 | 512)
size_px: 512
render: File
instance_mask: File
depth: File
}
