/* Generated from contracts/comminution-sweep.schema.json by web/scripts/gen-types.mjs. Do not edit. */

/**
 * The sweep configuration that s05_synthesize validates before evaluating the chain (FR-017-10).
 * 
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "design".
 */
export type Design = {
seed: number
energy_model: ("bond" | "morrell")
n_configurations: number
points_per_configuration: number
split: {
train: number
validation: number
held_out: number
}
box: Box
}
/**
 * Sampling box: one bound pair per input of the D2 input vector (unit-suffixed names).
 * 
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "box".
 */
export type Box = ({
burden_m: (Bound & {
min?: XBurdenM
max?: XBurdenM
})
spacing_ratio: (Bound & {
min?: XSpacingRatio
max?: XSpacingRatio
})
powder_factor_kg_per_m3: (Bound & {
min?: XPowderFactorKgPerM3
max?: XPowderFactorKgPerM3
})
hole_diameter_mm: (Bound & {
min?: XHoleDiameterMm
max?: XHoleDiameterMm
})
bench_height_m: (Bound & {
min?: XBenchHeightM
max?: XBenchHeightM
})
rock_factor: (Bound & {
min?: XRockFactor
max?: XRockFactor
})
bond_work_index_kwh_per_t?: (Bound & {
min?: XBondWorkIndexKwhPerT
max?: XBondWorkIndexKwhPerT
})
morrell_index_kwh_per_t?: (Bound & {
min?: XMorrellIndexKwhPerT
max?: XMorrellIndexKwhPerT
})
crusher_css_mm: (Bound & {
min?: XCrusherCssMm
max?: XCrusherCssMm
})
target_p80_um: (Bound & {
min?: XTargetP80Um
max?: XTargetP80Um
})
mill_power_kw: (Bound & {
min?: XMillPowerKw
max?: XMillPowerKw
})
efficiency: (Bound & {
min?: XEfficiency
max?: XEfficiency
})
energy_cap_kwh_per_t: (Bound & {
min?: XEnergyCapKwhPerT
max?: XEnergyCapKwhPerT
})
explosive_cost_usd_per_kg: (Bound & {
min?: XExplosiveCostUsdPerKg
max?: XExplosiveCostUsdPerKg
})
energy_cost_usd_per_kwh: (Bound & {
min?: XEnergyCostUsdPerKwh
max?: XEnergyCostUsdPerKwh
})
consumables_usd_per_t: (Bound & {
min?: XConsumablesUsdPerT
max?: XConsumablesUsdPerT
})
} & Box1)
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "knowledge_row_id".
 */
export type KnowledgeRowId = string
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_burden_m".
 */
export type XBurdenM = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_spacing_ratio".
 */
export type XSpacingRatio = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_powder_factor_kg_per_m3".
 */
export type XPowderFactorKgPerM3 = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_hole_diameter_mm".
 */
export type XHoleDiameterMm = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_bench_height_m".
 */
export type XBenchHeightM = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_rock_factor".
 */
export type XRockFactor = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_bond_work_index_kwh_per_t".
 */
export type XBondWorkIndexKwhPerT = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_morrell_index_kwh_per_t".
 */
export type XMorrellIndexKwhPerT = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_crusher_css_mm".
 */
export type XCrusherCssMm = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_target_p80_um".
 */
export type XTargetP80Um = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_mill_power_kw".
 */
export type XMillPowerKw = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_efficiency".
 */
export type XEfficiency = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_energy_cap_kwh_per_t".
 */
export type XEnergyCapKwhPerT = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_explosive_cost_usd_per_kg".
 */
export type XExplosiveCostUsdPerKg = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_energy_cost_usd_per_kwh".
 */
export type XEnergyCostUsdPerKwh = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_consumables_usd_per_t".
 */
export type XConsumablesUsdPerT = number
export type Box1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "slug".
 */
export type Slug = string
/**
 * Inputs fixed per ore x circuit configuration.
 * 
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "config_inputs".
 */
export type ConfigInputs = ({
hole_diameter_mm: XHoleDiameterMm
bench_height_m: XBenchHeightM
rock_factor: XRockFactor
bond_work_index_kwh_per_t?: XBondWorkIndexKwhPerT
morrell_index_kwh_per_t?: XMorrellIndexKwhPerT
crusher_css_mm: XCrusherCssMm
target_p80_um: XTargetP80Um
mill_power_kw: XMillPowerKw
efficiency: XEfficiency
energy_cap_kwh_per_t: XEnergyCapKwhPerT
explosive_cost_usd_per_kg: XExplosiveCostUsdPerKg
energy_cost_usd_per_kwh: XEnergyCostUsdPerKwh
consumables_usd_per_t: XConsumablesUsdPerT
} & ConfigInputs1)
export type ConfigInputs1 = {
[k: string]: unknown | undefined
}
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_specific_energy_kwh_per_t".
 */
export type XSpecificEnergyKwhPerT = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_throughput_t_per_h".
 */
export type XThroughputTPerH = number
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "x_cost_usd_per_t".
 */
export type XCostUsdPerT = number

/**
 * Seeded Sobol sweeps of the mine-to-mill chain written by s05_synthesize (DC-017-01, spec 017-planning-survey).
 */
export interface D2ComminutionSweeps {
$schema?: string
schema_version: string
synthetic: true
label: "calibrated synthetic — not validated against real data"
design: Design
/**
 * @minItems 0
 * @maxItems 64
 */
unverified_rows: KnowledgeRowId[]
/**
 * @minItems 10
 * @maxItems 10000
 */
configurations: [Configuration, Configuration, Configuration, Configuration, Configuration, Configuration, Configuration, Configuration, Configuration, Configuration, ...(Configuration)[]]
}
/**
 * Bound pair of one input: both limits from the cited knowledge-table row, with its verification status.
 * 
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "bound".
 */
export interface Bound {
min: number
max: number
row: KnowledgeRowId
verification: ("verified" | "UNVERIFIED")
}
/**
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "configuration".
 */
export interface Configuration {
id: Slug
split: ("train" | "validation" | "held-out")
seed: number
inputs: ConfigInputs
/**
 * @minItems 8
 * @maxItems 4096
 */
points: [Point, Point, Point, Point, Point, Point, Point, Point, ...(Point)[]]
}
/**
 * One blast design of a configuration and the chain outputs at it.
 * 
 * This interface was referenced by `D2ComminutionSweeps`'s JSON-Schema
 * via the `definition` "point".
 */
export interface Point {
burden_m: XBurdenM
spacing_ratio: XSpacingRatio
powder_factor_kg_per_m3: XPowderFactorKgPerM3
specific_energy_kwh_per_t: XSpecificEnergyKwhPerT
throughput_t_per_h: XThroughputTPerH
cost_usd_per_t: XCostUsdPerT
}
