# Generated from contracts/comminution-sweep.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Split(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    train: Annotated[int, Field(ge=1, le=10000)]
    validation: Annotated[int, Field(ge=1, le=10000)]
    held_out: Annotated[int, Field(ge=1, le=10000)]


class KnowledgeRowId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z][a-z0-9_]{0,95}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class XBenchHeightM(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=30.0)]


class XBondWorkIndexKwhPerT(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=50.0)]


class XBurdenM(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=20.0)]


class XConsumablesUsdPerT(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class XCostUsdPerT(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10000.0)]


class XCrusherCssMm(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=500.0)]


class XEfficiency(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1.0)]


class XEnergyCapKwhPerT(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class XEnergyCostUsdPerKwh(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10.0)]


class XExplosiveCostUsdPerKg(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class XHoleDiameterMm(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=500.0)]


class XMillPowerKw(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100000.0)]


class XMorrellIndexKwhPerT(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=50.0)]


class XPowderFactorKgPerM3(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=5.0)]


class XRockFactor(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=25.0)]


class XSpacingRatio(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=4.0)]


class XSpecificEnergyKwhPerT(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000.0)]


class XTargetP80Um(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=10000.0)]


class XThroughputTPerH(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000000.0)]


class Bound(BaseModel):
    """
    Bound pair of one input: both limits from the cited knowledge-table row, with its verification status.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    min: float
    max: float
    row: KnowledgeRowId
    verification: Literal["verified", "UNVERIFIED"]


class BurdenM(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XBurdenM
    max: XBurdenM


class SpacingRatio(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XSpacingRatio
    max: XSpacingRatio


class PowderFactorKgPerM3(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XPowderFactorKgPerM3
    max: XPowderFactorKgPerM3


class HoleDiameterMm(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XHoleDiameterMm
    max: XHoleDiameterMm


class BenchHeightM(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XBenchHeightM
    max: XBenchHeightM


class RockFactor(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XRockFactor
    max: XRockFactor


class BondWorkIndexKwhPerT(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XBondWorkIndexKwhPerT
    max: XBondWorkIndexKwhPerT


class MorrellIndexKwhPerT(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XMorrellIndexKwhPerT
    max: XMorrellIndexKwhPerT


class CrusherCssMm(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XCrusherCssMm
    max: XCrusherCssMm


class TargetP80Um(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XTargetP80Um
    max: XTargetP80Um


class MillPowerKw(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XMillPowerKw
    max: XMillPowerKw


class Efficiency(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XEfficiency
    max: XEfficiency


class EnergyCapKwhPerT(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XEnergyCapKwhPerT
    max: XEnergyCapKwhPerT


class ExplosiveCostUsdPerKg(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XExplosiveCostUsdPerKg
    max: XExplosiveCostUsdPerKg


class EnergyCostUsdPerKwh(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XEnergyCostUsdPerKwh
    max: XEnergyCostUsdPerKwh


class ConsumablesUsdPerT(Bound):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: XConsumablesUsdPerT
    max: XConsumablesUsdPerT


class Box1(BaseModel):
    """
    Sampling box: one bound pair per input of the D2 input vector (unit-suffixed names).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    burden_m: BurdenM
    spacing_ratio: SpacingRatio
    powder_factor_kg_per_m3: PowderFactorKgPerM3
    hole_diameter_mm: HoleDiameterMm
    bench_height_m: BenchHeightM
    rock_factor: RockFactor
    bond_work_index_kwh_per_t: BondWorkIndexKwhPerT
    morrell_index_kwh_per_t: MorrellIndexKwhPerT | None = None
    crusher_css_mm: CrusherCssMm
    target_p80_um: TargetP80Um
    mill_power_kw: MillPowerKw
    efficiency: Efficiency
    energy_cap_kwh_per_t: EnergyCapKwhPerT
    explosive_cost_usd_per_kg: ExplosiveCostUsdPerKg
    energy_cost_usd_per_kwh: EnergyCostUsdPerKwh
    consumables_usd_per_t: ConsumablesUsdPerT


class Box2(BaseModel):
    """
    Sampling box: one bound pair per input of the D2 input vector (unit-suffixed names).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    burden_m: BurdenM
    spacing_ratio: SpacingRatio
    powder_factor_kg_per_m3: PowderFactorKgPerM3
    hole_diameter_mm: HoleDiameterMm
    bench_height_m: BenchHeightM
    rock_factor: RockFactor
    bond_work_index_kwh_per_t: BondWorkIndexKwhPerT | None = None
    morrell_index_kwh_per_t: MorrellIndexKwhPerT
    crusher_css_mm: CrusherCssMm
    target_p80_um: TargetP80Um
    mill_power_kw: MillPowerKw
    efficiency: Efficiency
    energy_cap_kwh_per_t: EnergyCapKwhPerT
    explosive_cost_usd_per_kg: ExplosiveCostUsdPerKg
    energy_cost_usd_per_kwh: EnergyCostUsdPerKwh
    consumables_usd_per_t: ConsumablesUsdPerT


class Box(RootModel[Box1 | Box2]):
    root: Annotated[
        Box1 | Box2,
        Field(description="Sampling box: one bound pair per input of the D2 input vector (unit-suffixed names)."),
    ]


class ConfigInputs1(BaseModel):
    """
    Inputs fixed per ore x circuit configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    hole_diameter_mm: XHoleDiameterMm
    bench_height_m: XBenchHeightM
    rock_factor: XRockFactor
    bond_work_index_kwh_per_t: XBondWorkIndexKwhPerT
    morrell_index_kwh_per_t: XMorrellIndexKwhPerT | None = None
    crusher_css_mm: XCrusherCssMm
    target_p80_um: XTargetP80Um
    mill_power_kw: XMillPowerKw
    efficiency: XEfficiency
    energy_cap_kwh_per_t: XEnergyCapKwhPerT
    explosive_cost_usd_per_kg: XExplosiveCostUsdPerKg
    energy_cost_usd_per_kwh: XEnergyCostUsdPerKwh
    consumables_usd_per_t: XConsumablesUsdPerT


class ConfigInputs2(BaseModel):
    """
    Inputs fixed per ore x circuit configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    hole_diameter_mm: XHoleDiameterMm
    bench_height_m: XBenchHeightM
    rock_factor: XRockFactor
    bond_work_index_kwh_per_t: XBondWorkIndexKwhPerT | None = None
    morrell_index_kwh_per_t: XMorrellIndexKwhPerT
    crusher_css_mm: XCrusherCssMm
    target_p80_um: XTargetP80Um
    mill_power_kw: XMillPowerKw
    efficiency: XEfficiency
    energy_cap_kwh_per_t: XEnergyCapKwhPerT
    explosive_cost_usd_per_kg: XExplosiveCostUsdPerKg
    energy_cost_usd_per_kwh: XEnergyCostUsdPerKwh
    consumables_usd_per_t: XConsumablesUsdPerT


class ConfigInputs(RootModel[ConfigInputs1 | ConfigInputs2]):
    root: Annotated[
        ConfigInputs1 | ConfigInputs2,
        Field(description="Inputs fixed per ore x circuit configuration."),
    ]


class Design(BaseModel):
    """
    The sweep configuration that s05_synthesize validates before evaluating the chain (FR-017-10).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    energy_model: Literal["bond", "morrell"]
    n_configurations: Annotated[int, Field(ge=10, le=10000)]
    points_per_configuration: Annotated[int, Field(ge=8, le=4096)]
    split: Split
    box: Box


class Point(BaseModel):
    """
    One blast design of a configuration and the chain outputs at it.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    burden_m: XBurdenM
    spacing_ratio: XSpacingRatio
    powder_factor_kg_per_m3: XPowderFactorKgPerM3
    specific_energy_kwh_per_t: XSpecificEnergyKwhPerT
    throughput_t_per_h: XThroughputTPerH
    cost_usd_per_t: XCostUsdPerT


class Configuration(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    split: Literal["train", "validation", "held-out"]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    inputs: ConfigInputs
    points: Annotated[list[Point], Field(max_length=4096, min_length=8)]


class D2ComminutionSweeps(BaseModel):
    """
    Seeded Sobol sweeps of the mine-to-mill chain written by s05_synthesize (DC-017-01, spec 017-planning-survey).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    synthetic: Literal[True]
    label: Literal["calibrated synthetic — not validated against real data"]
    design: Design
    unverified_rows: Annotated[list[KnowledgeRowId], Field(max_length=64, min_length=0)]
    configurations: Annotated[list[Configuration], Field(max_length=10000, min_length=10)]
