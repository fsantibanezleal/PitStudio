# Generated from contracts/slope-results.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class PofSeed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=18446744073709551615)]


class CoordinateM(RootModel[float]):
    root: Annotated[float, Field(ge=-1000000.0, le=1000000.0)]


class Probability(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class Method(RootModel[Literal["bishop", "spencer"]]):
    root: Literal["bishop", "spencer"]


class Circle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    centre_x_m: CoordinateM
    centre_z_m: CoordinateM
    radius_m: Annotated[float, Field(gt=0.0, le=1000000.0)]
    entry_x_m: CoordinateM
    exit_x_m: CoordinateM


class FosResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Method
    status: Literal["ok", "no valid slip surface"]
    fos: Annotated[float | None, Field(gt=0.0, le=1000.0)] = None
    critical_circle: Circle | None = None
    iterations: Annotated[int | None, Field(ge=1, le=100)] = None
    theta_deg: Annotated[float | None, Field(gt=-90.0, lt=90.0)] = None
    slices: Annotated[int, Field(ge=10, le=500)]
    circles_evaluated: Annotated[int, Field(ge=1, le=100000)]
    rejected_circles: Annotated[int, Field(ge=0, le=100000)]


class WilsonInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower: Probability
    upper: Probability
    z: float


class PofResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Method
    candidate_set: Literal["lowest-F circles of the mean-parameter Bishop search"]
    samples: Annotated[int, Field(ge=1, le=1000000)]
    candidates: Annotated[int, Field(ge=1, le=100000)]
    failures: Annotated[int, Field(ge=0, le=1000000)]
    pof: Probability
    wilson_95: WilsonInterval
    seed: PofSeed


class SectionResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    section_id: ArtefactId
    section_sha256: Sha256
    fos: Annotated[list[FosResult], Field(max_length=2, min_length=1)]
    pof: PofResult | None = None


class C1FosAndPofTables(BaseModel):
    """
    Factor-of-safety and probability-of-failure tables of the C1 analysis per section and method (F, critical circle, rejected circles, k, N, K, PoF and its Wilson interval), baked for the web and the docs (DC-010-04, spec 010-slope).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    run_id: RunId | None = None
    mode: Literal["live", "baked"]
    sections: Annotated[list[SectionResult], Field(max_length=1000, min_length=1)]
