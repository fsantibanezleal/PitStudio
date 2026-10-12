# Generated from contracts/pit-shells.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Bitset(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Block set: bit b of byte b // 8 (least significant bit first) is block index b in the block-model blocks order; standard base64 with padding.",
            max_length=166668,
            pattern="^([A-Za-z0-9+/]{4})*([A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$",
        ),
    ]


class Cents(RootModel[int]):
    root: Annotated[int, Field(ge=-4611686018427387904, le=4611686018427387903)]


class MiningCapacityTItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class ProcessingCapacityTItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class Lambda(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=2.0)]


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


class Unit1(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=199999)]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


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


class StripRatio(RootModel[float | None]):
    root: Annotated[float | None, Field(ge=0.0, le=1000000.0)]


class Tonnes(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000000000000.0)]


class Unit(BaseModel):
    """
    Bench-phase unit: the blocks of one pushback on one bench (FR-017-18).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[int, Field(ge=0, le=199999)]
    pushback: Annotated[int, Field(ge=0, le=199)]
    bench: Annotated[int, Field(ge=0, le=9999)]
    ore_t: Tonnes
    waste_t: Tonnes
    value_cents: Cents


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class BlockModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    sha256: Sha256
    n_blocks: Annotated[int, Field(ge=1, le=1000000)]


class UltimatePit(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shell: Annotated[int, Field(ge=0, le=199)]
    value_cents: Cents
    strip_ratio: StripRatio | None


class Config(BaseModel):
    """
    Shell and schedule configuration validated before solving (FR-017-28).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lambdas: Annotated[list[Lambda], Field(max_length=200, min_length=1)]
    t_min_t: Annotated[float, Field(gt=0.0, le=1000000000000.0)]
    periods: Annotated[int, Field(ge=1, le=50)]
    mining_capacity_t: Annotated[list[MiningCapacityTItem], Field(max_length=50, min_length=1)]
    processing_capacity_t: Annotated[list[ProcessingCapacityTItem], Field(max_length=50, min_length=1)]
    discount_rate: Annotated[float, Field(ge=0.0, lt=1.0)]
    time_limit_s: Annotated[float, Field(gt=0.0, le=604800.0)]
    mip_rel_gap: Annotated[float, Field(ge=0.0, le=0.0001)]


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: SpdxId
    licence_class: LicenceClass
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None


class Period(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    t: Annotated[int, Field(ge=1, le=50)]
    units: Annotated[list[Unit1], Field(max_length=200000, min_length=0)]
    mined_t: Tonnes
    ore_t: Tonnes
    cash_flow_usd: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    strip_ratio: StripRatio | None


class Pushback(BaseModel):
    """
    Incremental block set closed at the cumulative shell `shell` (FR-017-17).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    shell: Annotated[int, Field(ge=0, le=199)]
    blocks: Bitset
    ore_t: Tonnes
    waste_t: Tonnes
    strip_ratio_incremental: StripRatio | None
    strip_ratio_cumulative: StripRatio | None


class Solver(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Literal["highs", "scipy-milp"]
    version: Version


class Schedule(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    solver: Solver
    status: Literal["optimal", "time-limit", "infeasible", "unbounded", "error"]
    binaries: Annotated[int, Field(ge=0, le=200000)]
    gap: Annotated[float | None, Field(ge=0.0, le=1.0)]
    npv_usd: Annotated[float | None, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    periods: Annotated[list[Period], Field(max_length=50, min_length=0)]


class Shell(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lambda_: Annotated[Lambda, Field(alias="lambda")]
    blocks: Bitset
    block_count: Annotated[int, Field(ge=0, le=1000000)]
    ore_t: Tonnes
    waste_t: Tonnes
    value_cents: Cents
    strip_ratio: StripRatio | None


class E1ShellsPushbacksAndSchedule(BaseModel):
    """
    Nested pit shells, pushbacks, bench-phase units and the MILP schedule written by the planner (DC-017-03, spec 017-planning-survey).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    block_model: BlockModel
    licence: Licence
    block_set_encoding: Literal["bitset-lsb0-base64"]
    config: Config
    shells: Annotated[list[Shell], Field(max_length=200, min_length=1)]
    ultimate_pit: UltimatePit
    pushbacks: Annotated[list[Pushback], Field(max_length=200, min_length=1)]
    units: Annotated[list[Unit], Field(max_length=200000, min_length=0)]
    schedule: Schedule
