/* Generated from contracts/coco-instances.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "coco_id".
 */
export type CocoId = number
/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "coordinate_px".
 */
export type CoordinatePx = number
/**
 * @minItems 6
 * @maxItems 8192
 * 
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "polygon".
 */
export type Polygon = [CoordinatePx, CoordinatePx, CoordinatePx, CoordinatePx, CoordinatePx, CoordinatePx, ...(CoordinatePx)[]]
/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "category".
 */
export type Category = ({
id: number
name: ("haul_truck" | "shovel" | "light_vehicle" | "person" | "boulder")
supercategory?: string
} & Category1)
export type Category1 = ({
id?: 1
name?: "haul_truck"
} | {
id?: 2
name?: "shovel"
} | {
id?: 3
name?: "light_vehicle"
} | {
id?: 4
name?: "person"
} | {
id?: 5
name?: "boulder"
})

/**
 * Closed COCO instances subset (images, polygon annotations with iscrowd 0, the five perception categories) written by st55_sdg and the dataset builder (DC-009-02, spec 009-perception).
 */
export interface COCOInstancesSubset {
$schema?: string
/**
 * @minItems 1
 * @maxItems 50000
 */
images: [Image, ...(Image)[]]
/**
 * @maxItems 1000000
 */
annotations: Annotation[]
/**
 * @minItems 5
 * @maxItems 5
 */
categories: [Category, Category, Category, Category, Category]
}
/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "image".
 */
export interface Image {
id: CocoId
file_name: Relpath
width: number
height: number
}
/**
 * This interface was referenced by `COCOInstancesSubset`'s JSON-Schema
 * via the `definition` "annotation".
 */
export interface Annotation {
id: CocoId
image_id: CocoId
category_id: number
/**
 * @minItems 4
 * @maxItems 4
 */
bbox: [CoordinatePx, CoordinatePx, CoordinatePx, CoordinatePx]
/**
 * @minItems 1
 * @maxItems 64
 */
segmentation: [Polygon, ...(Polygon)[]]
area: number
iscrowd: 0
}
