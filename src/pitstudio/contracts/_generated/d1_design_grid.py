# Generated from contracts/d1-design-grid.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Units(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x50: Literal["m"]
    x80: Literal["m"]
    oversize: Literal["%"]
    ppv: Literal["m/s"]
    flyrock_radius: Literal["m"]


class Value(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100000.0)]


class Axe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    input: Literal[
        "air_density_kg_per_m3",
        "bench_height_m",
        "beta",
        "burden_m",
        "charge_length_m",
        "charge_per_delay_kg",
        "distance_m",
        "drag_coefficient",
        "drilling_deviation_m",
        "explosive_density_kg_per_m3",
        "fragment_diameter_m",
        "hole_diameter_m",
        "k_site_m_per_s",
        "launch_speed_m_per_s",
        "oversize_limit_m",
        "rock_density_kg_per_m3",
        "rock_factor",
        "rws",
        "spacing_m",
        "x_max_m",
    ]
    values: Annotated[list[Value], Field(max_length=64, min_length=1)]


class DesignInputs(BaseModel):
    """
    design inputs in SI units, as minephys.blasting takes them
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    burden_m: Annotated[float | None, Field(gt=0.0, le=20.0)] = None
    spacing_m: Annotated[float | None, Field(gt=0.0, le=30.0)] = None
    bench_height_m: Annotated[float | None, Field(gt=0.0, le=50.0)] = None
    hole_diameter_m: Annotated[float | None, Field(description="m, not mm", gt=0.0, le=1.0)] = None
    charge_length_m: Annotated[float | None, Field(gt=0.0, le=50.0)] = None
    drilling_deviation_m: Annotated[float | None, Field(ge=0.0, le=5.0)] = None
    explosive_density_kg_per_m3: Annotated[float | None, Field(gt=0.0, le=2000.0)] = None
    rws: Annotated[
        float | None,
        Field(description="relative weight strength, ANFO = 100", gt=0.0, le=300.0),
    ] = None
    rock_factor: Annotated[float | None, Field(description="Cunningham's range", ge=0.8, le=22.0)] = None
    x_max_m: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    oversize_limit_m: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    distance_m: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    charge_per_delay_kg: Annotated[float | None, Field(gt=0.0, le=100000.0)] = None
    k_site_m_per_s: Annotated[float | None, Field(gt=0.0, le=100.0)] = None
    beta: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    launch_speed_m_per_s: Annotated[float | None, Field(gt=0.0, le=500.0)] = None
    fragment_diameter_m: Annotated[float | None, Field(gt=0.0, le=10.0)] = None
    rock_density_kg_per_m3: Annotated[float | None, Field(gt=0.0, le=10000.0)] = None
    drag_coefficient: Annotated[float | None, Field(ge=0.0, le=10.0)] = None
    air_density_kg_per_m3: Annotated[float | None, Field(ge=0.0, le=2.0)] = None


class Point(BaseModel):
    """
    one grid point: the swept inputs and the model outputs
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    inputs: DesignInputs
    x50_m: Annotated[float, Field(gt=0.0, le=10.0)]
    x80_m: Annotated[float, Field(gt=0.0, le=10.0)]
    oversize_pct: Annotated[float, Field(ge=0.0, le=100.0)]
    ppv_m_per_s: Annotated[float, Field(ge=0.0, le=100.0)]
    flyrock_radius_m: Annotated[float, Field(ge=0.0, le=100000.0)]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class D1BlastDesignGrid(BaseModel):
    """
    Design grid of case D1 (x50, x80, oversize, PPV, flyrock radius) computed by minephys.blasting in the D1 recipe (DC-012-05, spec 012-fragmentation).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[
        str | None,
        Field(
            alias="$schema",
            description="editor hint; ignored by consumers",
            max_length=200,
        ),
    ] = None
    case_id: Literal["D1"]
    minephys_version: Version
    kuzram_variant: Literal["cunningham1983", "cunningham2005"]
    distribution: Literal["kco-swebrec", "rosin-rammler"]
    units: Units
    fixed_inputs: DesignInputs
    axes: Annotated[list[Axe], Field(max_length=4, min_length=1)]
    points: Annotated[list[Point], Field(max_length=4096, min_length=1)]
