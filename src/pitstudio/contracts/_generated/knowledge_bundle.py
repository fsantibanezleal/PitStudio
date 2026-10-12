# Generated from contracts/knowledge-bundle.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class BibKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_:-]{0,63}$")]


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class Symbol(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    symbol: Annotated[str, Field(max_length=64, min_length=1)]
    meaning: Annotated[str, Field(max_length=300, min_length=1)]
    units: Annotated[str, Field(max_length=64, min_length=1)]


class Engine(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9-]{1,31}$")]
    spec: Literal["007-haulage-dispatch", "013-sensors", "014-robot-learning", "018-web-cases"]


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


class EngineModel(BaseModel):
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


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


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


class MinephysSymbol(RootModel[str]):
    root: Annotated[str, Field(max_length=200, pattern="^minephys(\\.[a-z_][a-z0-9_]{0,63}){1,4}$")]


class Module(RootModel[Literal["haulage", "blasting", "geotech", "bulk", "comminution", "environment", "planning"]]):
    root: Literal["haulage", "blasting", "geotech", "bulk", "comminution", "environment", "planning"]


class Range(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    min: float
    max: float


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class SeeAlsoItem(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z][a-z0-9_-]{0,95}$")]


class Term(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[str, Field(max_length=96, pattern="^[a-z][a-z0-9_-]{0,95}$")]
    origin: Literal["minephys", "docs"]
    term_en: Annotated[str, Field(max_length=200, min_length=1)]
    term_es: Annotated[str, Field(max_length=200, min_length=1)]
    definition_en: Annotated[str, Field(max_length=1000, min_length=1)]
    definition_es: Annotated[str, Field(max_length=1000, min_length=1)]
    citation: BibKey | None = None
    see_also: Annotated[list[SeeAlsoItem] | None, Field(max_length=16, min_length=0)] = None


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class Verification(RootModel[Literal["verified", "UNVERIFIED"]]):
    root: Literal["verified", "UNVERIFIED"]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Input(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class Source(BaseModel):
    """
    The pinned minephys knowledge export and the PitStudio files the bundle was built from.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    minephys_version: Version
    minephys_commit: GitSha
    inputs: Annotated[list[Input], Field(max_length=8, min_length=0)]


class CitedBy(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    parameters: Annotated[list[KnowledgeRowId], Field(max_length=10000, min_length=0)]
    equations: Annotated[list[KnowledgeRowId], Field(max_length=2000, min_length=0)]


class BibEntry1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    key: BibKey
    entry_type: Literal["article", "book", "inbook", "inproceedings", "techreport", "manual", "misc"]
    authors: Annotated[str, Field(max_length=1000, min_length=1)]
    title: Annotated[str, Field(max_length=500, min_length=1)]
    year: Annotated[int, Field(ge=1800, le=2100)]
    doi: Annotated[str, Field(max_length=220, pattern="^10\\.[0-9]{4,9}/[!-~]{1,200}$")]
    url: HttpsUrl | None = None
    access: Literal["open", "paywalled", "regulation", "bibliographic-only"]
    cited_by: CitedBy


class BibEntry2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    key: BibKey
    entry_type: Literal["article", "book", "inbook", "inproceedings", "techreport", "manual", "misc"]
    authors: Annotated[str, Field(max_length=1000, min_length=1)]
    title: Annotated[str, Field(max_length=500, min_length=1)]
    year: Annotated[int, Field(ge=1800, le=2100)]
    doi: Annotated[str | None, Field(max_length=220, pattern="^10\\.[0-9]{4,9}/[!-~]{1,200}$")] = None
    url: HttpsUrl
    access: Literal["open", "paywalled", "regulation", "bibliographic-only"]
    cited_by: CitedBy


class BibEntry(RootModel[BibEntry1 | BibEntry2]):
    root: BibEntry1 | BibEntry2


class Dataset(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    title: Annotated[str, Field(max_length=300, min_length=1)]
    kind: Literal["real", "synthetic"]
    spdx: SpdxId
    redistribution: Literal["redistributable", "derived-only", "no-redistribution"]
    landing_url: HttpsUrl
    card: Annotated[str, Field(max_length=80, pattern="^data/cards/[a-z0-9-]{1,64}\\.md$")]


class Theory(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    topic: Topic
    anchor: Annotated[str, Field(max_length=67, pattern="^eq-[a-z0-9-]{1,64}$")]


class Equation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: KnowledgeRowId
    title: Annotated[str, Field(max_length=200, min_length=1)]
    module: Module
    latex: Annotated[str, Field(max_length=4000, min_length=1)]
    symbols: Annotated[list[Symbol], Field(max_length=64, min_length=1)]
    function: MinephysSymbol
    citation: BibKey
    page: Annotated[str, Field(max_length=200, min_length=1)]
    verification: Verification
    verified_on: Date | None = None
    rows: Annotated[list[KnowledgeRowId] | None, Field(max_length=64, min_length=0)] = None
    theory: Theory | None = None
    engine: Engine | None = None


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


class Framework(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ToolId
    name: Annotated[str, Field(max_length=64, min_length=1)]
    category: Literal["studio-tool", "component"]
    status: Literal["not-yet-run", "done", "evaluated-not-adopted"]
    licence_class: LicenceClass


class Si(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: float
    range: Range | None = None
    unit: Annotated[str, Field(max_length=32, min_length=1)]


class Si1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: float | None = None
    range: Range
    unit: Annotated[str, Field(max_length=32, min_length=1)]


class Parameter1(BaseModel):
    """
    One knowledge-table row as published, with its SI conversion.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: KnowledgeRowId
    module: Module
    quantity: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    value: float | constr(pattern=r"^-?[0-9]{1,20}/[0-9]{1,20}$", max_length=41)
    range: Range | None = None
    units: Annotated[str, Field(max_length=64, min_length=1)]
    si: Si | Si1
    citation: BibKey
    page: Annotated[str, Field(max_length=200, min_length=1)]
    verification: Verification
    verified_on: Date | None = None
    symbols: Annotated[list[MinephysSymbol], Field(max_length=8, min_length=1)]
    role: Literal["model_constant", "parameter", "limit", "conversion"] | None = None
    licence: SpdxId


class Si2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: float
    range: Range | None = None
    unit: Annotated[str, Field(max_length=32, min_length=1)]


class Si3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: float | None = None
    range: Range
    unit: Annotated[str, Field(max_length=32, min_length=1)]


class Parameter2(BaseModel):
    """
    One knowledge-table row as published, with its SI conversion.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: KnowledgeRowId
    module: Module
    quantity: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    value: float | constr(pattern=r"^-?[0-9]{1,20}/[0-9]{1,20}$", max_length=41) | None = None
    range: Range
    units: Annotated[str, Field(max_length=64, min_length=1)]
    si: Si2 | Si3
    citation: BibKey
    page: Annotated[str, Field(max_length=200, min_length=1)]
    verification: Verification
    verified_on: Date | None = None
    symbols: Annotated[list[MinephysSymbol], Field(max_length=8, min_length=1)]
    role: Literal["model_constant", "parameter", "limit", "conversion"] | None = None
    licence: SpdxId


class Parameter(RootModel[Parameter1 | Parameter2]):
    root: Annotated[
        Parameter1 | Parameter2,
        Field(description="One knowledge-table row as published, with its SI conversion."),
    ]


class KnowledgeBundle(BaseModel):
    """
    Knowledge bundle web/public/knowledge/bundle.json generated by build_knowledge.py from the pinned minephys export (DC-020-03, spec 020-web-knowledge).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    source: Annotated[
        Source,
        Field(description="The pinned minephys knowledge export and the PitStudio files the bundle was built from."),
    ]
    parameters: Annotated[list[Parameter], Field(max_length=10000, min_length=0)]
    equations: Annotated[list[Equation], Field(max_length=2000, min_length=0)]
    glossary: Annotated[list[Term], Field(max_length=5000, min_length=0)]
    datasets: Annotated[list[Dataset], Field(max_length=256, min_length=0)]
    frameworks: Annotated[list[Framework], Field(max_length=64, min_length=0)]
    bibliography: Annotated[list[BibEntry], Field(max_length=5000, min_length=0)]


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
    engine: EngineModel
    plot: Literal["xy", "field", "section", "3d"]
    controls: Annotated[list[RangeControl | ChoiceControl], Field(max_length=16, min_length=1)]
    features: Annotated[list[Feature], Field(max_length=8, min_length=1)]
    colormap: Literal["viridis", "cividis", "inferno", "magma"] | None
    justification3d: Justification3d | None = None
