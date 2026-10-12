# Generated from contracts/field-dataset.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Grid(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    nx: Literal[64, 128]
    ny: Literal[64, 128]


class Scenario(BaseModel):
    """
    scenario parameters drawn from the recipe ranges
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    breach_row: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    breach_col: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    release_volume_m3: Annotated[float | None, Field(gt=0.0, le=100000000.0)] = None
    yield_stress_pa: Annotated[float | None, Field(description="Bingham yield stress", gt=0.0, le=10000.0)] = None
    plastic_viscosity_pa_s: Annotated[
        float | None, Field(description="Bingham plastic viscosity", gt=0.0, le=1000.0)
    ] = None
    density_kg_per_m3: Annotated[float | None, Field(ge=1000.0, le=3000.0)] = None
    source_row_start: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    source_col_start: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    source_row_end: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    source_col_end: Annotated[int | None, Field(description="grid cell index", ge=0, le=127)] = None
    source_strength_kg_per_m2_s: Annotated[float | None, Field(gt=0.0, le=1.0)] = None
    wind_speed_m_per_s: Annotated[float | None, Field(ge=0.0, le=50.0)] = None
    wind_direction_deg: Annotated[
        float | None,
        Field(
            description="direction the wind blows from, clockwise from north",
            ge=0.0,
            lt=360.0,
        ),
    ] = None


class OutputTimes(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000.0)]


class AveragingWindow(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000000.0)]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Store(BaseModel):
    """
    payload store; sha256 of the file (Parquet) or of the sorted chunk-digest listing (Zarr)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    format: Literal["zarr"]
    path: Relpath
    sha256: Sha256


class Unit(
    RootModel[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
        ]
    ]
):
    root: Annotated[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
        ],
        Field(description='physical unit ("1" = dimensionless, counts, indices and categories)'),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class SourceDem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    source_id: Slug
    sha256: Sha256


class Channel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: ParamKey
    role: Literal["input", "output"]
    unit: Unit


class FnoFieldDatasetMetadata(BaseModel):
    """
    Metadata of one Warp shallow-water or dust field run on a terrain patch written by st50_physics (DC-011-03, spec 011-surrogates).
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
    model: Literal["tailings", "dust"]
    patch_id: Slug
    scenario_id: Slug
    source_dem: SourceDem
    cell_size_m: Annotated[float, Field(gt=0.0, le=100.0)]
    grid: Grid
    resolution_transfer: Annotated[
        bool,
        Field(description="true only for the 128 x 128 resolution-transfer runs (labelled not claimed)"),
    ]
    channels: Annotated[
        list[Channel],
        Field(description="payload channels in store order", max_length=32, min_length=2),
    ]
    scenario: Annotated[Scenario, Field(description="scenario parameters drawn from the recipe ranges")]
    t_end_s: Annotated[float, Field(gt=0.0, le=1000000.0)]
    output_times_s: Annotated[
        list[OutputTimes] | None,
        Field(
            description="tailings: t_k = k T_end / 8, k = 1..8",
            max_length=8,
            min_length=1,
        ),
    ] = None
    averaging_window_s: Annotated[
        list[AveragingWindow] | None,
        Field(
            description="dust: start and end of the time average",
            max_length=2,
            min_length=2,
        ),
    ] = None
    solver: Literal["warp-swe-bingham", "warp-dust"]
    solver_version: Version
    store: Store
    label: Literal["calibrated synthetic — not validated against real data"]
