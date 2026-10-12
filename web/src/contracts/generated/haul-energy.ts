/* Generated from contracts/haul-energy.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "version".
 */
export type Version = string
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "sha256".
 */
export type Sha256 = string
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "row".
 */
export type Row = {
route: Slug
drivetrain: ("diesel" | "trolley" | "bev")
leg: ("loaded" | "empty")
empty_mass_t: number
payload_t: number
wheel_energy_kwh: number
source_energy_kwh: number
regenerated_kwh: number
source_energy_kwh_per_t: number
fuel_l_per_t_km: (number | null)
co2e_kg_per_t: number
basis: {
per_tonne: "payload-t"
per_km: "along-road-km"
}
/**
 * @minItems 1
 * @maxItems 64
 */
knowledge_rows: [KnowledgeRowId, ...(KnowledgeRowId)[]]
/**
 * @maxItems 64
 */
unverified_rows: KnowledgeRowId[]
}
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "knowledge_row_id".
 */
export type KnowledgeRowId = string

/**
 * Energy, fuel and CO2e per tonne by drivetrain and route, written by the route-energy engine (DC-007-05, spec 007-haulage-dispatch).
 */
export interface RouteEnergyTable {
$schema?: string
schema_version: SchemaVersion
id: Slug
knowledge: {
package: "minephys"
version: Version
}
/**
 * @minItems 1
 * @maxItems 256
 */
routes: [Route, ...(Route)[]]
/**
 * @minItems 1
 * @maxItems 4096
 */
rows: [Row, ...(Row)[]]
honesty: Honesty
}
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "route".
 */
export interface Route {
id: Slug
/**
 * Along-road length (the per-km basis).
 */
length_m: number
/**
 * @minItems 1
 * @maxItems 2048
 */
segments: [RouteSegment, ...(RouteSegment)[]]
grade_limit_frac?: number
dp_tolerance_m?: number
dem_sha256?: Sha256
}
/**
 * This interface was referenced by `RouteEnergyTable`'s JSON-Schema
 * via the `definition` "route_segment".
 */
export interface RouteSegment {
length_m: number
grade_pct: number
rolling_resistance_pct: number
trolley: boolean
}
export interface Honesty {
label: "calibrated synthetic — not validated against real data"
bias_note: "Known DES bias: simulated truck cycle times tend to underestimate short hauls and overestimate long hauls; no real haul telemetry exists to correct it."
}
