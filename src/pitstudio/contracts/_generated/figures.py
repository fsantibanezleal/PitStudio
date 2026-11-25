# Generated from contracts/figures.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Engine(BaseModel):
    """
    Browser engine of specs 007, 013, 014 or 018, or a teaching function of web/src/theory/fn/.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["engine", "teaching"]
    id: Annotated[str, Field(max_length=32, pattern="^[a-z][A-Za-z0-9-]{1,31}$")]


class FigureId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class KnowledgeRowId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z][a-z0-9_]{0,95}$")]


class NameEnEs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=120, min_length=1)]
    es: Annotated[str, Field(max_length=120, min_length=1)]


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


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Topic(
    RootModel[
        Literal[
            "haulage",
            "loading-and-terramechanics",
            "drill-and-blast",
            "slopes-and-monitoring",
            "bulk-flow-dem-mpm",
            "comminution",
            "dust",
            "tailings",
            "planning",
            "rtx-sensor-physics",
            "robot-learning",
            "vision-language-reasoning",
            "sim-to-real",
        ]
    ]
):
    root: Literal[
        "haulage",
        "loading-and-terramechanics",
        "drill-and-blast",
        "slopes-and-monitoring",
        "bulk-flow-dem-mpm",
        "comminution",
        "dust",
        "tailings",
        "planning",
        "rtx-sensor-physics",
        "robot-learning",
        "vision-language-reasoning",
        "sim-to-real",
    ]


class Justification3d(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    third_variable: Annotated[str, Field(max_length=64, min_length=1)]
    unit: Unit
    reason: TextEnEs


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


class Photo(BaseModel):
    """
    A registered raster photograph (FR-020-16); charts are never raster images.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["photo"]
    id: FigureId
    file: Relpath
    alt: TextEnEs
    licence: SpdxId
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None


class RangeControl(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["range"]
    id: ParamKey
    label: NameEnEs
    unit: Unit
    min: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    max: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    step: Annotated[float, Field(gt=0.0, le=1000000000000000.0)]
    default: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    default_row: KnowledgeRowId | None = None
    digest_exempt: bool | None = None


class Feature(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ParamKey
    label: NameEnEs
    unit: Unit | None = None


class Option(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs


class ChoiceControl(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["choice"]
    id: ParamKey
    label: NameEnEs
    options: Annotated[list[Option], Field(max_length=16, min_length=2)]
    default: Slug
    default_row: KnowledgeRowId | None = None


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


class Chart(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["chart"]
    id: FigureId
    topic: Topic
    title: NameEnEs
    engine: Engine
    plot: Literal["xy", "field", "section", "3d"]
    controls: Annotated[list[RangeControl | ChoiceControl], Field(max_length=16, min_length=1)]
    features: Annotated[list[Feature], Field(max_length=8, min_length=1)]
    colormap: Literal["viridis", "cividis", "inferno", "magma"] | None
    justification3d: Justification3d | None = None


class FigureRegistry(BaseModel):
    """
    Interactive figures and registered photographs of web/src/theory/figures.yaml (DC-020-04, spec 020-web-knowledge).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    figures: Annotated[list[Chart | Photo], Field(max_length=128, min_length=1)]
