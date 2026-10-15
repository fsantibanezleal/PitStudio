/* Generated from contracts/terrain-grid.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * Attributes of the root group of the site-local terrain grid Zarr store written by st10_terrain (DC-004-03, spec 004-scene-pipeline); the arrays are elevation (float32), valid_mask and fill_mask. Version 1.1: optional `fixture` member.
 */
export type SiteLocalTerrainGridAttributes = {
schema_version: SchemaVersion
kind: "terrain-grid"
/**
 * X east, Y north, Z up, relative to the site origin
 */
frame: "site-enu"
/**
 * row 0 is the northern edge; columns run east
 */
layout: "north-up"
up_axis: "Z"
horizontal_unit: "m"
vertical_unit: "m"
cell_size_m: number
rows: number
cols: number
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
x_min_m: number
/**
 * site-frame coordinate, m (FR-004-02: |offset| <= 1.0e5 m horizontally)
 */
y_max_m: number
origin: SiteOrigin
crs: CrsRecord
input_kind: ("dem" | "laz")
method: ("dem-crop" | "laz-ground-mean")
/**
 * ASPRS classes kept (FR-004-04: class 2 only)
 * 
 * @minItems 1
 * @maxItems 1
 */
ground_classes?: [2]
/**
 * @minItems 1
 * @maxItems 8
 */
source_ids: [Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
project: string
epoch: number
arrays: {
elevation: {
dtype: "float32"
unit: "m"
/**
 * [rows, cols]
 * 
 * @minItems 2
 * @maxItems 2
 */
shape: [number, number]
/**
 * @minItems 2
 * @maxItems 2
 */
chunk_shape: [number, number]
/**
 * of the uncompressed C-order little-endian array bytes
 */
sha256: string
}
valid_mask: {
dtype: "bool"
/**
 * [rows, cols]
 * 
 * @minItems 2
 * @maxItems 2
 */
shape: [number, number]
/**
 * @minItems 2
 * @maxItems 2
 */
chunk_shape: [number, number]
/**
 * of the uncompressed C-order little-endian array bytes
 */
sha256: string
}
fill_mask: {
dtype: "bool"
/**
 * [rows, cols]
 * 
 * @minItems 2
 * @maxItems 2
 */
shape: [number, number]
/**
 * @minItems 2
 * @maxItems 2
 */
chunk_shape: [number, number]
/**
 * of the uncompressed C-order little-endian array bytes
 */
sha256: string
}
}
/**
 * cell and sample counts (FR-004-05, FR-004-12)
 */
counts: {
valid_cells: number
filled_cells: number
nodata_cells: number
unfilled_holes: number
rejected_non_finite: number
rejected_sentinel: number
rejected_out_of_range: number
}
/**
 * nodata fraction inside the AOI after filling (FR-004-12)
 */
nodata_frac: number
max_fill_cells: number
/**
 * site-frame z of valid cells
 */
elevation_range_m: {
/**
 * site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)
 */
min: number
/**
 * site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)
 */
max: number
}
/**
 * source elevations of valid samples after unit conversion (FR-004-12 hard range)
 */
source_elevation_range_m: {
min: number
max: number
}
/**
 * True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false.
 */
fixture?: boolean
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "crs_ref".
 */
export type CrsRef = {
/**
 * EPSG code read from the file; null when none exists
 */
epsg: (number | null)
/**
 * WKT read from the file; required when no EPSG code exists
 */
wkt?: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "linear_unit".
 */
export type LinearUnit = {
name: ("metre" | "us-survey-foot" | "international-foot")
/**
 * factor applied to reach metres (FR-004-03)
 */
factor_to_m: number
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string

/**
 * site origin of the site-local frame (FR-004-02)
 */
export interface SiteOrigin {
/**
 * EPSG code of the UTM zone of the site (NAD83(2011), ETRS89, NAD83, WGS 84 zones)
 */
epsg: number
easting_m: number
northing_m: number
/**
 * origin elevation z0 in the vertical datum of the inputs, m
 */
z0_m: number
}
/**
 * CRS and axis units read from the input's own metadata (FR-004-01, FR-004-03)
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "crs_record".
 */
export interface CrsRecord {
horizontal: CrsRef
vertical: CrsRef
horizontal_unit: LinearUnit
vertical_unit: LinearUnit
}
