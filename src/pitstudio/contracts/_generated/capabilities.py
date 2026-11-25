# Generated from contracts/capabilities.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class LocalOnly(RootModel[Literal["measured locally, not published (licence)"]]):
    root: Literal["measured locally, not published (licence)"]


VersionsAdditionalProperty = TypeAliasType("VersionsAdditionalProperty", Annotated[str, Field(max_length=64)])


class Note(RootModel[str]):
    root: Annotated[str, Field(max_length=300)]


class ProbeResult(BaseModel):
    """
    one probe of the capability bench
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["pass", "fail", "skip"]
    versions: Annotated[
        dict[constr(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"), VersionsAdditionalProperty],
        Field(max_length=32),
    ]
    metrics: (
        dict[constr(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$"), float | constr(max_length=200)] | LocalOnly | None
    ) = None
    telemetry: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$"), float] | None,
        Field(max_length=32),
    ] = None
    notes: Annotated[list[Note] | None, Field(max_length=20)] = None
    error: Annotated[str | None, Field(max_length=300)] = None


class PitstudioCapabilityReport(BaseModel):
    """
    Committed output of `studio/bench/run_bench.py`: which GPU tools run on the reference machine, their versions, and the metrics their licences allow publishing (DC-001-05, spec 001-contracts).
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
    generated: Date
    gpu: Annotated[str, Field(max_length=128, min_length=1)]
    driver: Driver
    probes: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,31}$"), ProbeResult],
        Field(max_length=64),
    ]
