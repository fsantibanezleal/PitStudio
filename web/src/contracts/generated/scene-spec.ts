/* Generated from contracts/scene-spec.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * terrain level of detail (FR-004-06: LOD 0-2)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "lod_index".
 */
export type LodIndex = (0 | 1 | 2)
/**
 * design parameters with their design-code ranges and citations (FR-004-16 ... FR-004-22)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "design".
 */
export type Design = {
outline_source: ("rim-contour" | "upstream-shell")
/**
 * site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)
 */
rim_z_m?: number
/**
 * site-frame elevation, m (FR-004-02: |offset| <= 5.0e3 m vertically)
 */
floor_z_m: number
/**
 * bench height H, m (hard domain [5, 30])
 */
bench_height_m: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
/**
 * bench face angle alpha, degrees (hard domain [40, 85])
 */
face_angle_deg: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
/**
 * berm width b, m (hard domain [3, 60])
 */
berm_width_m: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
/**
 * ramp grade g, percent rise over run (hard domain [0, 15])
 */
ramp_grade_pct: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
/**
 * ramp width W, m (hard domain [8, 60])
 */
ramp_width_m: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
/**
 * windrow height, m (hard domain (0, 5])
 */
windrow_height_m: {
value: number
code_min: number
code_max: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
verification: ("verified" | "unverified")
}
}
/**
 * one machine model (FR-004-24, FR-004-27)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "asset".
 */
export type Asset = {
id: Slug
class_label: MachineClass
length_m: number
width_m: number
height_m: number
mass_kg: number
/**
 * mid-axle height (30 CFR 56.9300(b), FR-004-18)
 */
mid_axle_height_m?: number
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
dimensions_citation: string
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
mass_citation: string
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * class labels of the machines st30_assets builds (FR-004-24)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "machine_class".
 */
export type MachineClass = ("haul_truck" | "shovel" | "excavator" | "wheel_loader" | "water_truck" | "light_vehicle" | "crusher")
/**
 * one rigid body of an asset and the joint to its parent (FR-004-24, FR-004-27)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "part".
 */
export type Part = {
asset: Slug
id: Slug
part: PartLabel
/**
 * parent part id; null for the articulation root
 */
parent: (Slug | null)
joint?: ("revolute" | "prismatic")
axis?: ("X" | "Y" | "Z")
lower_deg?: number
upper_deg?: number
lower_m?: number
upper_m?: number
mass_kg: number
length_m: number
width_m: number
height_m: number
/**
 * true for a joint that closes a kinematic loop (FR-004-24)
 */
exclude_from_articulation?: boolean
/**
 * source of the value (document, table or page); at most 256 characters (FR-004-40)
 */
citation: string
}
/**
 * closed part-label vocabulary for articulated sub-parts (FR-004-25)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "part_label".
 */
export type PartLabel = ("chassis" | "cab" | "dump_body" | "wheel" | "axle" | "track" | "undercarriage" | "house" | "boom" | "stick" | "bucket" | "dipper" | "lift_arm" | "front_frame" | "rear_frame" | "tank" | "spray_bar" | "hopper")
/**
 * a UsdPreviewSurface material: CC0 textures from a source, or our own (CC-BY-4.0) (FR-004-26)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "material".
 */
export type Material = {
id: Slug
source: ("polyhaven" | "ambientcg" | null)
spdx: ("CC0-1.0" | "CC-BY-4.0")
}
/**
 * closed class-label vocabulary (SemanticsLabelsAPI `class`, FR-004-25)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "class_label".
 */
export type ClassLabel = ("terrain" | "bench" | "berm" | "ramp" | "windrow" | "haul_road" | "haul_truck" | "shovel" | "excavator" | "wheel_loader" | "water_truck" | "light_vehicle" | "crusher" | "person" | "boulder")
/**
 * a free variant name (pushback, scenario); a USD identifier
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "variant_name".
 */
export type VariantName = string
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "time_of_day".
 */
export type TimeOfDay = ("dawn" | "morning" | "noon" | "afternoon" | "dusk" | "night")
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "weather".
 */
export type Weather = ("clear" | "overcast" | "rain" | "dust" | "fog")
/**
 * name of a `lod` variant; one per terrain LOD (FR-004-08)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "lod_name".
 */
export type LodName = ("lod0" | "lod1" | "lod2")
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "rule_id".
 */
export type RuleId = string
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "spdx_id".
 */
export type SpdxId = ("LicenseRef-USGov-PD" | "CC0-1.0" | "DL-DE-ZERO-2.0" | "CC-BY-4.0" | "LicenseRef-Copernicus-CLMS" | "CC-BY-SA-3.0" | "CC-BY-SA-4.0" | "Apache-2.0" | "MIT" | "BSD-2-Clause" | "BSD-3-Clause" | "MPL-2.0" | "LGPL-2.1-or-later" | "LicenseRef-TOST-1.0" | "LicenseRef-NVIDIA-Open-Model" | "LicenseRef-NVIDIA-SLA" | "LicenseRef-NvidiaProprietary" | "LicenseRef-NVIDIA-Omniverse" | "LicenseRef-TensorRT-SLA" | "LicenseRef-TensorRT-RTX-SLA")
/**
 * data/sources.yaml ids a scene may use (closed list, FR-004-40)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "scene_source_id".
 */
export type SceneSourceId = ("usgs-3dep-bingham" | "ot-mckinley-2023" | "nrw-hambach-dgm1" | "tang-werner-footprint" | "maus-v2" | "polyhaven" | "ambientcg" | "makehuman-exports")

/**
 * Scene specification read from the recipe params of st10_terrain to st45_validate and the export stage (DC-004-01, spec 004-scene-pipeline). It is a recipe params object: keys follow param_key, nesting depth <= 4 including the root, no $schema member. Version 1.1: optional `fixture` member.
 */
export interface SceneSpecificationSceneSpec {
schema_version: SchemaVersion
case: CaseId
/**
 * scene master seed, 0 ... 2^63-1
 */
seed: number
site: Site
terrain: Terrain
design: Design
/**
 * @maxItems 32
 */
assets: Asset[]
/**
 * @maxItems 512
 */
parts: Part[]
/**
 * @maxItems 32
 */
fleet: FleetEntry[]
people_count: number
/**
 * @maxItems 64
 */
materials: Material[]
labels: Labels
variants: Variants
validation?: Validation
/**
 * True while the document derives from a contract fixture (ADR-0040, FR-004-44); no stage that consumes it may publish a result from it. Absent means false.
 */
fixture?: boolean
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "site".
 */
export interface Site {
name: string
origin: SiteOrigin
/**
 * mine-polygon datasets for FR-004-15
 * 
 * @minItems 1
 * @maxItems 2
 */
polygon_sources: [("tang-werner-footprint" | "maus-v2")]|[("tang-werner-footprint" | "maus-v2"), ("tang-werner-footprint" | "maus-v2")]
}
/**
 * site origin of the site-local frame (FR-004-02)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "site_origin".
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
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "terrain".
 */
export interface Terrain {
/**
 * @minItems 1
 * @maxItems 3
 */
sources: [TerrainSource]|[TerrainSource, TerrainSource]|[TerrainSource, TerrainSource, TerrainSource]
/**
 * grid cell size (FR-004-04; default 1.0 m)
 */
cell_size_m: number
/**
 * largest hole filled (FR-004-05; default and cap 16)
 */
max_fill_cells: number
/**
 * largest nodata fraction after filling (FR-004-12; default 0.05)
 */
max_nodata_frac: number
/**
 * grid cell cap (FR-004-13; default 1.0e8)
 */
max_cells: number
/**
 * AOI polygon vertices [x, y] in the site frame, m; >= 3 vertices (FR-004-13)
 * 
 * @minItems 3
 * @maxItems 1024
 */
aoi_xy_m: [[number, number], [number, number], [number, number], ...([number, number])[]]
/**
 * @minItems 1
 * @maxItems 3
 */
lods: [LodSpec]|[LodSpec, LodSpec]|[LodSpec, LodSpec, LodSpec]
/**
 * @maxItems 8
 */
transformations?: []|[Transformation]|[Transformation, Transformation]|[Transformation, Transformation, Transformation]|[Transformation, Transformation, Transformation, Transformation]|[Transformation, Transformation, Transformation, Transformation, Transformation]|[Transformation, Transformation, Transformation, Transformation, Transformation, Transformation]|[Transformation, Transformation, Transformation, Transformation, Transformation, Transformation, Transformation]|[Transformation, Transformation, Transformation, Transformation, Transformation, Transformation, Transformation, Transformation]
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "terrain_source".
 */
export interface TerrainSource {
id: ("usgs-3dep-bingham" | "ot-mckinley-2023" | "nrw-hambach-dgm1")
kind: ("dem" | "laz")
/**
 * 3DEP or survey project name (one project per terrain grid)
 */
project: string
/**
 * survey year
 */
epoch: number
/**
 * FR-004-09: optional sources may end 'not run'
 */
optional: boolean
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "lod_spec".
 */
export interface LodSpec {
lod: LodIndex
/**
 * RTIN vertical error bound (FR-004-06, P-004-01 domain 0.05-8 m)
 */
max_error_m: number
/**
 * skirt depth (FR-004-07; default 2 x max_error)
 */
skirt_depth_m: number
}
/**
 * a CRS or datum transformation the recipe declares (FR-004-11)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "transformation".
 */
export interface Transformation {
component: ("horizontal" | "vertical")
from_epsg: number
to_epsg: number
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "fleet_entry".
 */
export interface FleetEntry {
asset: Slug
count: number
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "labels".
 */
export interface Labels {
/**
 * @minItems 1
 * @maxItems 15
 */
classes: [ClassLabel]|[ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]|[ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel, ClassLabel]
/**
 * @maxItems 18
 */
parts: []|[PartLabel]|[PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]|[PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel, PartLabel]
}
/**
 * variant names per variant set; the first name is the default selection (FR-004-29)
 * 
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "variants".
 */
export interface Variants {
/**
 * @minItems 1
 * @maxItems 16
 */
pushback: [VariantName]|[VariantName, VariantName]|[VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]
/**
 * @minItems 1
 * @maxItems 16
 */
scenario: [VariantName]|[VariantName, VariantName]|[VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]|[VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName, VariantName]
/**
 * @minItems 1
 * @maxItems 6
 */
time_of_day: [TimeOfDay]|[TimeOfDay, TimeOfDay]|[TimeOfDay, TimeOfDay, TimeOfDay]|[TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay]|[TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay]|[TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay, TimeOfDay]
/**
 * @minItems 1
 * @maxItems 5
 */
weather: [Weather]|[Weather, Weather]|[Weather, Weather, Weather]|[Weather, Weather, Weather, Weather]|[Weather, Weather, Weather, Weather, Weather]
/**
 * @minItems 1
 * @maxItems 3
 */
lod: [LodName]|[LodName, LodName]|[LodName, LodName, LodName]
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "validation".
 */
export interface Validation {
/**
 * @maxItems 32
 */
waivers?: Waiver[]
}
/**
 * This interface was referenced by `SceneSpecificationSceneSpec`'s JSON-Schema
 * via the `definition` "waiver".
 */
export interface Waiver {
rule: RuleId
reason: string
}
