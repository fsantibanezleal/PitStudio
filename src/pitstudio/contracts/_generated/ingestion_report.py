# Generated from contracts/ingestion-report.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]{1,4}$")]


class Records(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9007199254740991)]


class CheckedFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Annotated[Relpath, Field(description="Path relative to the data root.")]
    sha256: Sha256
    validator: Literal[
        "tabular", "raster", "point-cloud", "vector", "image-mask", "image", "series", "dataset-structure"
    ]
    schema_name: Annotated[str, Field(max_length=64, min_length=1, pattern="^[a-z][a-z0-9_]{0,63}$")]
    status: Literal["accepted", "rejected"]
    records: Records | None


class Row(RootModel[int]):
    root: Annotated[int, Field(description="Table row or series index.", ge=0, le=9007199254740991)]


class Pixel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x: Annotated[int, Field(ge=0, le=1000000)]
    y: Annotated[int, Field(ge=0, le=1000000)]


class Expected(RootModel[str]):
    root: Annotated[str, Field(max_length=200, min_length=1)]


class Unit(RootModel[str]):
    root: Annotated[str, Field(max_length=32, min_length=1)]


class Violation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    file: Relpath
    row: Annotated[Row | None, Field(description="Table row or series index.")]
    pixel: Pixel | None
    field: Annotated[str, Field(max_length=128, min_length=1)]
    field_kind: Literal["column", "property"]
    value: Annotated[
        constr(max_length=200) | float | bool | None,
        Field(description="Found value; non-finite values are written as text."),
    ]
    expected: Expected | None
    rule: Annotated[str, Field(max_length=200, min_length=1)]
    unit: Unit | None


class Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class IngestionReport(BaseModel):
    """
    Accepted or rejected inputs with every violation, written by s10_preprocess and s20_feature_extraction (DC-008-03, spec 008-data-pipeline).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    source: Slug
    stage: Literal["s10_preprocess", "s20_feature_extraction"]
    run_id: RunId
    created: UtcTimestamp
    status: Literal["accepted", "rejected"]
    files: Annotated[list[CheckedFile], Field(max_length=100000, min_length=1)]
    violations: Annotated[list[Violation], Field(max_length=1000000)]
    outputs: Annotated[list[Output], Field(max_length=4096)]
