# Generated from contracts/methods.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class MethodId(
    RootModel[
        Literal[
            "M1",
            "M2",
            "M3",
            "M4",
            "M5",
            "M6",
            "M7",
            "M8",
            "M9",
            "M10",
            "M11",
            "M12",
            "M13",
            "M14",
            "M15",
            "M16",
            "M17",
            "M18",
            "M19",
            "M20",
            "M21",
            "M22",
            "M23",
        ]
    ]
):
    root: Literal[
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
        "M6",
        "M7",
        "M8",
        "M9",
        "M10",
        "M11",
        "M12",
        "M13",
        "M14",
        "M15",
        "M16",
        "M17",
        "M18",
        "M19",
        "M20",
        "M21",
        "M22",
        "M23",
    ]


class NameEnEs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=120, min_length=1)]
    es: Annotated[str, Field(max_length=120, min_length=1)]


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


class TextEnEs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=1000, min_length=1)]
    es: Annotated[str, Field(max_length=1000, min_length=1)]


class Unit(RootModel[str]):
    root: Annotated[str, Field(max_length=32, min_length=1)]


class Criterion(BaseModel):
    """
    Acceptance criterion copied from the owning model spec's SC row.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    text: TextEnEs
    requirement: Annotated[str, Field(max_length=9, pattern="^SC-[0-9]{3}-[0-9]{2}$")]
    spec: Annotated[str, Field(max_length=64, pattern="^[0-9]{3}-[a-z0-9-]{1,60}$")]


class Metric(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: NameEnEs
    unit: Unit
    orientation: Literal["higher-is-better", "lower-is-better"]


class Comparison(BaseModel):
    """
    Pre-registered comparison design: baseline, metric with unit and orientation, pairing unit and number of pairs.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    baseline: NameEnEs
    metric: Metric
    pairing_unit: NameEnEs
    n: Annotated[int, Field(ge=1, le=1000000)]


class Method(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: MethodId
    name: NameEnEs
    tiers: Annotated[
        list[Literal["classical", "sota", "beyond-sota", "frontier"]],
        Field(max_length=3, min_length=1),
    ]
    implementation: Annotated[str, Field(max_length=300, min_length=1)]
    spdx: Annotated[list[SpdxId], Field(max_length=4, min_length=1)]
    lanes: Annotated[list[Literal["live", "precompute", "replay"]], Field(max_length=3, min_length=1)]
    learned: bool
    cases: Annotated[list[CaseId], Field(max_length=12, min_length=1)]
    comparison: Comparison | None = None
    criterion: Criterion | None = None
    docs_page: Annotated[
        str,
        Field(
            max_length=96,
            pattern="^docs/methods/m(0[1-9]|1[0-9]|2[0-3])-[a-z0-9-]{1,64}\\.md$",
        ),
    ]


class MethodRegistry(BaseModel):
    """
    The method ladder M1-M23 of studio/methods.yaml (DC-020-01, spec 020-web-knowledge).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    methods: Annotated[list[Method], Field(max_length=23, min_length=23)]
