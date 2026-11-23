/* Generated from contracts/chart-series.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * One published chart of a case: the series, axes, units, colour scale and the producer label of one chart of one published run, read by the generic chart reader of the Charts tab (DC-020-05, spec 020-web-knowledge). One JSON file per chart, published as an artefact of kind chart-series, at most 524288 bytes (studio-showcase budget class).
 */
export type ChartSeries = {
schema_version: "1.0"
kind: "chart-series"
id: Slug
case: CaseId
chart_type: ("line" | "bar" | "scatter" | "ecdf" | "raster" | "section" | "table")
/**
 * ok: the chart carries its data. not-run: the value could not be computed; the reason is published and nothing is drawn.
 */
status: ("ok" | "not-run")
title: NameEnEs
caption?: NameEnEs
producer: Producer
/**
 * The requirement or success-criterion ids of the specs this chart serves.
 * 
 * @minItems 1
 * @maxItems 8
 */
serves: [string]|[string, string]|[string, string, string]|[string, string, string, string]|[string, string, string, string, string]|[string, string, string, string, string, string]|[string, string, string, string, string, string, string]|[string, string, string, string, string, string, string, string]
not_run_reason?: NameEnEs
x_axis?: Axis
y_axis?: Axis
/**
 * bar: the category of each value of a series, in order.
 * 
 * @minItems 1
 * @maxItems 64
 */
categories?: [Category, ...(Category)[]]
/**
 * @minItems 1
 * @maxItems 12
 */
series?: [Series]|[Series, Series]|[Series, Series, Series]|[Series, Series, Series, Series]|[Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series, Series, Series, Series, Series]|[Series, Series, Series, Series, Series, Series, Series, Series, Series, Series, Series, Series]
/**
 * The features of the chart (FR-020-08), each labelled with the number the read-out panel shows.
 * 
 * @maxItems 24
 */
markers?: Marker[]
raster?: Raster
section?: Section
table?: Table
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "case_id".
 */
export type CaseId = ("A1" | "A2" | "A3" | "B1" | "B2" | "C1" | "C2" | "C3" | "D1" | "D2" | "E1" | "E2")
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "number_or_null".
 */
export type NumberOrNull = (number | null)
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "marker".
 */
export type Marker = {
id: Slug
label: NameEnEs
/**
 * The number as the read-out shows it, with its unit.
 */
value_text: string
orientation: ("vertical" | "horizontal" | "point")
x?: number
y?: number
}

/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "name_en_es".
 */
export interface NameEnEs {
en: string
es: string
}
/**
 * Who made the numbers: the studio tool, the method, the version and the data label of the run. Every published value carries all four.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "producer".
 */
export interface Producer {
tool: string
method: string
version: string
label: string
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "axis".
 */
export interface Axis {
label: NameEnEs
/**
 * The unit symbol; 1 for a dimensionless quantity.
 */
unit: string
scale?: ("linear" | "log")
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "category".
 */
export interface Category {
id: Slug
label: NameEnEs
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "series".
 */
export interface Series {
id: Slug
label: NameEnEs
/**
 * The unit of y when it differs from the unit of the y axis.
 */
unit?: string
/**
 * line (default), step (an ECDF or a staircase) or points.
 */
draw?: ("line" | "step" | "points")
/**
 * The number of samples the series summarises.
 */
n?: number
/**
 * @minItems 1
 * @maxItems 20000
 */
x?: [number, ...(number)[]]
/**
 * @minItems 1
 * @maxItems 20000
 */
y: [NumberOrNull, ...(NumberOrNull)[]]
/**
 * Lower edge of the band (line) or of the error bar (bar), same length as y.
 * 
 * @minItems 1
 * @maxItems 20000
 */
lo?: [NumberOrNull, ...(NumberOrNull)[]]
/**
 * Upper edge of the band (line) or of the error bar (bar), same length as y.
 * 
 * @minItems 1
 * @maxItems 20000
 */
hi?: [NumberOrNull, ...(NumberOrNull)[]]
band_label?: NameEnEs1
}
/**
 * What lo and hi are, for example the 95 % interval and its method.
 */
export interface NameEnEs1 {
en: string
es: string
}
/**
 * A map of nx by ny cells over a rectangular extent; values are row-major, the first row being the top (y1) row; null is no data.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "raster".
 */
export interface Raster {
nx: number
ny: number
extent: {
x0: number
x1: number
y0: number
y1: number
}
/**
 * @minItems 4
 * @maxItems 40000
 */
values: [NumberOrNull, NumberOrNull, NumberOrNull, NumberOrNull, ...(NumberOrNull)[]]
colour: {
/**
 * FR-020-10: viridis, cividis, inferno or magma only.
 */
colormap: ("viridis" | "cividis" | "inferno" | "magma")
vmin: number
vmax: number
unit: string
label: NameEnEs
}
}
/**
 * A vertical section: polylines (ground, benches, shells) and circles (slip circles), drawn with equal axis scales.
 * 
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "section".
 */
export interface Section {
/**
 * @minItems 1
 * @maxItems 64
 */
polylines: [{
id: Slug
label: NameEnEs
role?: ("ground" | "bench" | "shell" | "water" | "other")
/**
 * @minItems 2
 * @maxItems 5000
 */
points: [[number, number], [number, number], ...([number, number])[]]
}, ...({
id: Slug
label: NameEnEs
role?: ("ground" | "bench" | "shell" | "water" | "other")
/**
 * @minItems 2
 * @maxItems 5000
 */
points: [[number, number], [number, number], ...([number, number])[]]
})[]]
/**
 * @maxItems 64
 */
circles?: {
id: Slug
label: NameEnEs
role?: ("critical" | "other")
cx: number
cy: number
r: number
}[]
}
/**
 * This interface was referenced by `undefined`'s JSON-Schema
 * via the `definition` "table".
 */
export interface Table {
/**
 * @minItems 1
 * @maxItems 24
 */
columns: [({
id: Slug
label: NameEnEs
type: ("number" | "text")
unit?: string
} & {
id: Slug
label: NameEnEs
type: ("number" | "text")
unit?: string
}), ...(({
id: Slug
label: NameEnEs
type: ("number" | "text")
unit?: string
} & {
id: Slug
label: NameEnEs
type: ("number" | "text")
unit?: string
}))[]]
/**
 * @minItems 1
 * @maxItems 200
 */
rows: [[(number | string | null), ...((number | string | null))[]], ...([(number | string | null), ...((number | string | null))[]])[]]
}
