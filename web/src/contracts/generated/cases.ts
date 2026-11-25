/* Generated from contracts/cases.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "schema_version".
 */
export type SchemaVersion = string
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "category_id".
 */
export type CategoryId = ("A" | "B" | "C" | "D" | "E")
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "kpi".
 */
export type Kpi = {
id: ParamKey
name: TitleText
unit: KpiUnit
orientation: ("higher-is-better" | "lower-is-better" | "target" | "neutral")
/**
 * value the KPI should approach, in its unit
 */
target_value?: number
/**
 * shown on the Explore route (FR-018-05)
 */
headline: boolean
}
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "param_key".
 */
export type ParamKey = string
/**
 * ASCII unit id; the web renders the display symbol
 * 
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "kpi_unit".
 */
export type KpiUnit = ("1" | "%" | "pp" | "s" | "min" | "h" | "m" | "mm" | "km" | "km2" | "m3" | "m3/shift" | "t/h" | "kWh/t" | "kg/t" | "L/t" | "L/(t.km)" | "USD" | "USD/t" | "kg/VKT" | "ug/m3" | "mm/s" | "passes/truck" | "1/(1000 h)")
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "synthetic".
 */
export type Synthetic = {
label: TitleText
/**
 * validation class of spec 008 (FR-008-36); unvalidated is labelled 'calibrated synthetic - not validated against real data'
 */
validation: ("validated-against-real" | "descriptive-only" | "unvalidated")
reference_source?: Slug
}
/**
 * method ladder id M1-M23
 * 
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "method_id".
 */
export type MethodId = string
/**
 * engine ids of the engine table (spec 018 section 7.1)
 * 
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "engine_id".
 */
export type EngineId = ("des" | "policies" | "haulage" | "lp" | "routing" | "il1-twin" | "il2-twin" | "granular" | "gns" | "traffic" | "dust-lidar" | "detector" | "geotech" | "forecasters" | "swe" | "fno" | "plume" | "dust-particles" | "blasting" | "watershed" | "unet" | "comminution" | "meta-model" | "mincut" | "volume")
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "layer".
 */
export type Layer = ("terrain-2018" | "terrain-2023" | "roads" | "pit-shells" | "fleet" | "fields" | "sensors")
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "relpath".
 */
export type Relpath = string
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")

/**
 * Case registry studio/cases.yaml read by the web build, the docs matrices and the CI checks (DC-018-01, spec 018-web-cases).
 */
export interface PitStudioCaseRegistry {
/**
 * editor hint; ignored by consumers
 */
$schema?: string
schema_version: SchemaVersion
/**
 * the five labelled groups of the case rail, keyed by category letter
 */
categories: {
A: Category
B: Category
C: Category
D: Category
E: Category
}
/**
 * one entry per canonical case id; a repeated id is a duplicate key, rejected by the loader
 */
cases: {
A1: (Case & {
category?: "A"
recipe?: "studio/recipes/cases/a1.yaml"
})
A2: (Case & {
category?: "A"
recipe?: "studio/recipes/cases/a2.yaml"
})
A3: (Case & {
category?: "A"
recipe?: "studio/recipes/cases/a3.yaml"
})
B1: (Case & {
category?: "B"
recipe?: "studio/recipes/cases/b1.yaml"
})
B2: (Case & {
category?: "B"
recipe?: "studio/recipes/cases/b2.yaml"
})
C1: (Case & {
category?: "C"
recipe?: "studio/recipes/cases/c1.yaml"
})
C2: (Case & {
category?: "C"
recipe?: "studio/recipes/cases/c2.yaml"
})
C3: (Case & {
category?: "C"
recipe?: "studio/recipes/cases/c3.yaml"
})
D1: (Case & {
category?: "D"
recipe?: "studio/recipes/cases/d1.yaml"
})
D2: (Case & {
category?: "D"
recipe?: "studio/recipes/cases/d2.yaml"
})
E1: (Case & {
category?: "E"
recipe?: "studio/recipes/cases/e1.yaml"
})
E2: (Case & {
category?: "E"
recipe?: "studio/recipes/cases/e2.yaml"
})
}
}
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "category".
 */
export interface Category {
title: TitleText
}
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "title_text".
 */
export interface TitleText {
en: string
es: string
}
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "case".
 */
export interface Case {
category: CategoryId
title: TitleText
question: ProseText
/**
 * @minItems 1
 * @maxItems 8
 */
kpis: [Kpi]|[Kpi, Kpi]|[Kpi, Kpi, Kpi]|[Kpi, Kpi, Kpi, Kpi]|[Kpi, Kpi, Kpi, Kpi, Kpi]|[Kpi, Kpi, Kpi, Kpi, Kpi, Kpi]|[Kpi, Kpi, Kpi, Kpi, Kpi, Kpi, Kpi]|[Kpi, Kpi, Kpi, Kpi, Kpi, Kpi, Kpi, Kpi]
/**
 * data source ids of data/sources.yaml
 * 
 * @maxItems 16
 */
sources: []|[Slug]|[Slug, Slug]|[Slug, Slug, Slug]|[Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]|[Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug, Slug]
/**
 * @maxItems 8
 */
synthetic_data: []|[Synthetic]|[Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic, Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic]|[Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic, Synthetic]
/**
 * @minItems 1
 * @maxItems 23
 */
methods: [MethodId, ...(MethodId)[]]
/**
 * tool registry id -> role in the tool matrix (named or supporting)
 */
tools: {
[k: string]: "named" | "supporting" | undefined
}
/**
 * @minItems 1
 * @maxItems 8
 */
engines: [EngineId]|[EngineId, EngineId]|[EngineId, EngineId, EngineId]|[EngineId, EngineId, EngineId, EngineId]|[EngineId, EngineId, EngineId, EngineId, EngineId]|[EngineId, EngineId, EngineId, EngineId, EngineId, EngineId]|[EngineId, EngineId, EngineId, EngineId, EngineId, EngineId, EngineId]|[EngineId, EngineId, EngineId, EngineId, EngineId, EngineId, EngineId, EngineId]
/**
 * @maxItems 7
 */
layers: []|[Layer]|[Layer, Layer]|[Layer, Layer, Layer]|[Layer, Layer, Layer, Layer]|[Layer, Layer, Layer, Layer, Layer]|[Layer, Layer, Layer, Layer, Layer, Layer]|[Layer, Layer, Layer, Layer, Layer, Layer, Layer]
/**
 * SimClock step rate in frames per second (FR-018-22)
 */
clock_fps?: number
/**
 * studio/recipes/cases/<id in lower case>.yaml (FR-018-19)
 */
recipe: Relpath
validity: ProseText
}
/**
 * This interface was referenced by `PitStudioCaseRegistry`'s JSON-Schema
 * via the `definition` "prose_text".
 */
export interface ProseText {
en: string
es: string
}
