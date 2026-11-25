# Generated from contracts/fragment-table.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Realised(BaseModel):
    """
    exact realised PSD summary (the truth of the pile)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fragment_count: Annotated[int, Field(ge=1, le=1000000)]
    total_volume_m3: Annotated[float, Field(description="V_real", gt=0.0, le=1000000.0)]
    max_fragment_volume_m3: Annotated[float, Field(description="v_max", gt=0.0, le=600.0)]
    x50_m: Annotated[float, Field(description="volume-weighted quantile Q-1", gt=0.0, le=10.0)]
    x80_m: Annotated[float, Field(description="volume-weighted quantile Q-1", gt=0.0, le=10.0)]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class VisiblePxItem(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=1048576)]


class Row(BaseModel):
    """
    one Parquet row of the fragment table
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fragment_id: Annotated[
        int,
        Field(
            description="equals the instance id in every render mask (0 = background)",
            ge=1,
            le=1000000,
        ),
    ]
    size_m: Annotated[float, Field(description="volume-equivalent sphere diameter x", gt=0.0, le=10.0)]
    volume_m3: Annotated[float, Field(description="pi x^3 / 6", gt=0.0, le=600.0)]
    mass_kg: Annotated[float, Field(gt=0.0, le=6000000.0)]
    class_index: Annotated[int, Field(description="size class j of K = 20 log-spaced classes", ge=0, le=19)]
    seed: Annotated[
        int,
        Field(
            description="seed of the fragment's procedural rock mesh",
            ge=0,
            le=4294967295,
        ),
    ]
    visible_px: Annotated[
        list[VisiblePxItem],
        Field(description="visible pixels per view, in view order", max_length=64),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Generator(BaseModel):
    """
    target parameters of the pile
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    passing_function: Annotated[
        Literal["swebrec-truncated"],
        Field(description="Swebrec of minephys.blasting, truncated to [x_min, x_max]"),
    ]
    x50_m: Annotated[float, Field(gt=0.0, le=10.0)]
    x_max_m: Annotated[float, Field(gt=0.0, le=10.0)]
    x_min_m: Annotated[float, Field(gt=0.0, le=10.0)]
    b: Annotated[float, Field(gt=0.0, le=50.0)]
    target_volume_m3: Annotated[float, Field(description="V", gt=0.0, le=1000000.0)]
    size_classes: Literal[20]
    density_kg_per_m3: Annotated[float, Field(ge=500.0, le=10000.0)]
    minephys_version: Version


class Table(BaseModel):
    """
    the Parquet table whose rows follow $defs/row
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    format: Literal["parquet"]
    path: Relpath
    sha256: Sha256
    rows: Annotated[int, Field(ge=1, le=1000000)]


class MuckPileFragmentTable(BaseModel):
    """
    JSON sidecar of the Parquet fragment table
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
    synthetic: Literal[True]
    pile_seed: Annotated[int, Field(ge=0, le=4294967295)]
    generator: Annotated[Generator, Field(description="target parameters of the pile")]
    realised: Annotated[
        Realised,
        Field(description="exact realised PSD summary (the truth of the pile)"),
    ]
    view_count: Annotated[int, Field(ge=0, le=64)]
    table: Annotated[Table, Field(description="the Parquet table whose rows follow $defs/row")]
