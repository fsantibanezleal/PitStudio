/* Generated from contracts/terrain-tiles.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string

/**
 * Quadtree tile index of the terrain meshes per level of detail, written by st10_terrain (DC-004-04, spec 004-scene-pipeline).
 */
export interface TerrainTileIndex {
$schema?: string
schema_version: SchemaVersion
kind: "terrain-tiles"
frame: "site-enu"
/**
 * tiles of 257 x 257 grid samples (FR-004-07)
 */
tile_samples: 257
/**
 * elevation array digest of the source grid
 */
grid_elevation_sha256: string
/**
 * the USD terrain layer holding the tile meshes
 */
layer_path: string
/**
 * @minItems 1
 * @maxItems 3
 */
lods: [Lod]|[Lod, Lod]|[Lod, Lod, Lod]
/**
 * @minItems 1
 * @maxItems 4096
 */
tiles: [Tile, ...(Tile)[]]
}
/**
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "lod".
 */
export interface Lod {
/**
 * terrain level of detail (FR-004-06: LOD 0-2)
 */
lod: (0 | 1 | 2)
max_error_m: number
skirt_depth_m: number
tile_count: number
}
/**
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "tile".
 */
export interface Tile {
/**
 * <lod>-<quadtree level>-<x>-<y>
 */
id: string
/**
 * terrain level of detail (FR-004-06: LOD 0-2)
 */
lod: (0 | 1 | 2)
level: number
x: number
y: number
/**
 * absolute USD prim path
 */
prim: string
bbox: Bbox
max_error_m: number
/**
 * <= 257^2 grid vertices + 4 x 257 skirt vertices
 */
vertices: number
/**
 * <= 2 x 256^2 + 8 x 256 skirt triangles
 */
triangles: number
/**
 * of the tile's float32 positions followed by its uint32 indices, little-endian
 */
sha256: string
}
/**
 * site-frame bounding box including skirts, m
 * 
 * This interface was referenced by `TerrainTileIndex`'s JSON-Schema
 * via the `definition` "bbox".
 */
export interface Bbox {
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
x_min_m: number
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
y_min_m: number
z_min_m: number
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
x_max_m: number
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
y_max_m: number
z_max_m: number
}
