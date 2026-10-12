# Generated from contracts/block-model.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ReferenceOptimum(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[int, Field(ge=-4611686018427387904, le=4611686018427387903)]
    unit: Literal["usd-cents", "instance-units"]
    source: Literal["oreblocks-stamp", "minelib-best-known"]


class IjkItem(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9999)]


class PrecItem(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=999999999)]


class Economics(BaseModel):
    """
    Components of v_i(lambda) (FR-017-12): p, s_r, r, c_p and c_m.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    metal_price_usd_per_t: Annotated[float, Field(gt=0.0, le=1000000000.0)]
    selling_cost_usd_per_t: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    recovery: Annotated[float, Field(gt=0.0, le=1.0)]
    processing_cost_usd_per_t: Annotated[float, Field(ge=0.0, le=1000000.0)]
    mining_cost_usd_per_t: Annotated[float, Field(ge=0.0, le=1000000.0)]


class BlockSizeMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000.0)]


class ShapeItem(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=10000)]


class Grid(BaseModel):
    """
    Regular grid; index k increases upward; origin is the minimum corner.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    origin_m: Annotated[list[float], Field(max_length=3, min_length=3)]
    block_size_m: Annotated[list[BlockSizeMItem], Field(max_length=3, min_length=3)]
    shape: Annotated[list[ShapeItem], Field(max_length=3, min_length=3)]


class LicenceClass(
    RootModel[
        Literal[
            "public-domain",
            "open-no-attribution",
            "own",
            "attribution",
            "share-alike",
            "display-only",
            "reference-only",
        ]
    ]
):
    root: Literal[
        "public-domain", "open-no-attribution", "own", "attribution", "share-alike", "display-only", "reference-only"
    ]


class Precedence(BaseModel):
    """
    Origin of the per-block arcs: the instance's own arcs or the level-cone generator (FR-017-13).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    source: Literal["own", "generated"]
    slope_deg: Annotated[float | None, Field(gt=0.0, lt=90.0)] = None
    levels: Annotated[int | None, Field(ge=1, le=16)] = None


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Semver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class File(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Relpath
    sha256: Sha256


class Source(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["oreblocks", "minelib", "own-grid"]
    seed: Annotated[int | None, Field(ge=0, le=9223372036854775807)] = None
    oreblocks_version: Semver | None = None
    instance: Slug | None = None
    files: Annotated[list[File] | None, Field(max_length=8, min_length=1)] = None


class SpdxId(
    RootModel[
        Literal[
            "LicenseRef-USGov-PD",
            "CC0-1.0",
            "DL-DE-ZERO-2.0",
            "CC-BY-4.0",
            "LicenseRef-Copernicus-CLMS",
            "CC-BY-SA-3.0",
            "CC-BY-SA-4.0",
            "Apache-2.0",
            "MIT",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "MPL-2.0",
            "LGPL-2.1-or-later",
            "LicenseRef-TOST-1.0",
            "LicenseRef-NVIDIA-Open-Model",
            "LicenseRef-NVIDIA-SLA",
            "LicenseRef-NvidiaProprietary",
            "LicenseRef-NVIDIA-Omniverse",
            "LicenseRef-TensorRT-SLA",
            "LicenseRef-TensorRT-RTX-SLA",
        ]
    ]
):
    root: Literal[
        "LicenseRef-USGov-PD",
        "CC0-1.0",
        "DL-DE-ZERO-2.0",
        "CC-BY-4.0",
        "LicenseRef-Copernicus-CLMS",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "Apache-2.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "MPL-2.0",
        "LGPL-2.1-or-later",
        "LicenseRef-TOST-1.0",
        "LicenseRef-NVIDIA-Open-Model",
        "LicenseRef-NVIDIA-SLA",
        "LicenseRef-NvidiaProprietary",
        "LicenseRef-NVIDIA-Omniverse",
        "LicenseRef-TensorRT-SLA",
        "LicenseRef-TensorRT-RTX-SLA",
    ]


class ValueUsd(RootModel[float]):
    root: Annotated[float, Field(ge=-1000000000000.0, le=1000000000000.0)]


class ValuesUsd(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mill: ValueUsd | None = None
    waste: ValueUsd | None = None
    leach: ValueUsd | None = None
    stockpile: ValueUsd | None = None


class Block(BaseModel):
    """
    One block; grade is a mass fraction; prec lists the ids of the blocks that must be mined first.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=999999999)]
    ijk: Annotated[list[IjkItem], Field(max_length=3, min_length=3)]
    centre_m: Annotated[list[float], Field(max_length=3, min_length=3)]
    tonnage_t: Annotated[float, Field(ge=0.0, le=10000000000.0)]
    grade: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    values_usd: ValuesUsd | None = None
    prec: Annotated[list[PrecItem] | None, Field(max_length=256, min_length=0)] = None


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: SpdxId
    licence_class: LicenceClass
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None


class E1BlockModel(BaseModel):
    """
    Block model with values, grid indices and precedence arcs for the ultimate pit (DC-017-02, spec 017-planning-survey).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    id: Slug
    synthetic: bool
    source: Source
    licence: Licence
    grid: Grid
    precedence: Precedence
    value_form: Literal["components", "destination-values"]
    economics: Economics | None = None
    reference_optimum: ReferenceOptimum | None = None
    blocks: Annotated[list[Block], Field(max_length=1000000, min_length=1)]
