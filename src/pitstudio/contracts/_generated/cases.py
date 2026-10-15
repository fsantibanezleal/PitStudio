# Generated from contracts/cases.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


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


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class TitleText(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=120, min_length=1)]
    es: Annotated[str, Field(max_length=120, min_length=1)]


class ProseText(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=600, min_length=1)]
    es: Annotated[str, Field(max_length=600, min_length=1)]


class CategoryId(RootModel[Literal["A", "B", "C", "D", "E"]]):
    root: Literal["A", "B", "C", "D", "E"]


class MethodId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="method ladder id M1-M23",
            max_length=3,
            pattern="^M([1-9]|1[0-9]|2[0-3])$",
        ),
    ]


class EngineId(
    RootModel[
        Literal[
            "des",
            "policies",
            "haulage",
            "lp",
            "routing",
            "il1-twin",
            "il2-twin",
            "granular",
            "gns",
            "traffic",
            "dust-lidar",
            "detector",
            "geotech",
            "forecasters",
            "swe",
            "fno",
            "plume",
            "dust-particles",
            "blasting",
            "watershed",
            "unet",
            "comminution",
            "meta-model",
            "mincut",
            "volume",
        ]
    ]
):
    root: Annotated[
        Literal[
            "des",
            "policies",
            "haulage",
            "lp",
            "routing",
            "il1-twin",
            "il2-twin",
            "granular",
            "gns",
            "traffic",
            "dust-lidar",
            "detector",
            "geotech",
            "forecasters",
            "swe",
            "fno",
            "plume",
            "dust-particles",
            "blasting",
            "watershed",
            "unet",
            "comminution",
            "meta-model",
            "mincut",
            "volume",
        ],
        Field(description="engine ids of the engine table (spec 018 section 7.1)"),
    ]


class Layer(RootModel[Literal["terrain-2018", "terrain-2023", "roads", "pit-shells", "fleet", "fields", "sensors"]]):
    root: Literal["terrain-2018", "terrain-2023", "roads", "pit-shells", "fleet", "fields", "sensors"]


class KpiUnit(
    RootModel[
        Literal[
            "1",
            "%",
            "pp",
            "s",
            "min",
            "h",
            "m",
            "mm",
            "km",
            "km2",
            "m3",
            "m3/shift",
            "t/h",
            "kWh/t",
            "kg/t",
            "L/t",
            "L/(t.km)",
            "USD",
            "USD/t",
            "kg/VKT",
            "ug/m3",
            "mm/s",
            "passes/truck",
            "1/(1000 h)",
        ]
    ]
):
    root: Annotated[
        Literal[
            "1",
            "%",
            "pp",
            "s",
            "min",
            "h",
            "m",
            "mm",
            "km",
            "km2",
            "m3",
            "m3/shift",
            "t/h",
            "kWh/t",
            "kg/t",
            "L/t",
            "L/(t.km)",
            "USD",
            "USD/t",
            "kg/VKT",
            "ug/m3",
            "mm/s",
            "passes/truck",
            "1/(1000 h)",
        ],
        Field(description="ASCII unit id; the web renders the display symbol"),
    ]


class Category(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    title: TitleText


class Kpi(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ParamKey
    name: TitleText
    unit: KpiUnit
    orientation: Literal["higher-is-better", "lower-is-better", "target", "neutral"]
    target_value: Annotated[float | None, Field(description="value the KPI should approach, in its unit")] = None
    headline: Annotated[bool, Field(description="shown on the Explore route (FR-018-05)")]


class Synthetic(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: TitleText
    validation: Annotated[
        Literal["validated-against-real", "descriptive-only", "unvalidated"],
        Field(
            description="validation class of spec 008 (FR-008-36); unvalidated is labelled 'calibrated synthetic - not validated against real data'"
        ),
    ]
    reference_source: Slug | None = None


class Case(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: CategoryId
    title: TitleText
    question: ProseText
    kpis: Annotated[list[Kpi], Field(max_length=8, min_length=1)]
    sources: Annotated[
        list[Slug],
        Field(description="data source ids of data/sources.yaml", max_length=16),
    ]
    synthetic_data: Annotated[list[Synthetic], Field(max_length=8)]
    methods: Annotated[list[MethodId], Field(max_length=23, min_length=1)]
    tools: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9-]{1,47}$", max_length=48), Literal["named", "supporting"]],
        Field(
            description="tool registry id -> role in the tool matrix (named or supporting)",
            max_length=32,
            min_length=1,
        ),
    ]
    engines: Annotated[list[EngineId], Field(max_length=8, min_length=1)]
    layers: Annotated[list[Layer], Field(max_length=7)]
    clock_fps: Annotated[
        float | None,
        Field(
            description="SimClock step rate in frames per second (FR-018-22)",
            gt=0.0,
            le=240.0,
        ),
    ] = 10
    recipe: Annotated[
        Relpath,
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]
    validity: ProseText


class Categories(BaseModel):
    """
    the five labelled groups of the case rail, keyed by category letter
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    A: Category
    B: Category
    C: Category
    D: Category
    E: Category


class A1(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["A"]
    recipe: Annotated[
        Literal["studio/recipes/cases/a1.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class A2(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["A"]
    recipe: Annotated[
        Literal["studio/recipes/cases/a2.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class A3(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["A"]
    recipe: Annotated[
        Literal["studio/recipes/cases/a3.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class B1(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["B"]
    recipe: Annotated[
        Literal["studio/recipes/cases/b1.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class B2(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["B"]
    recipe: Annotated[
        Literal["studio/recipes/cases/b2.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class C1(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["C"]
    recipe: Annotated[
        Literal["studio/recipes/cases/c1.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class C2(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["C"]
    recipe: Annotated[
        Literal["studio/recipes/cases/c2.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class C3(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["C"]
    recipe: Annotated[
        Literal["studio/recipes/cases/c3.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class D1(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["D"]
    recipe: Annotated[
        Literal["studio/recipes/cases/d1.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class D2(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["D"]
    recipe: Annotated[
        Literal["studio/recipes/cases/d2.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class E1(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["E"]
    recipe: Annotated[
        Literal["studio/recipes/cases/e1.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class E2(Case):
    model_config = ConfigDict(
        extra="forbid",
    )
    category: Literal["E"]
    recipe: Annotated[
        Literal["studio/recipes/cases/e2.yaml"],
        Field(description="studio/recipes/cases/<id in lower case>.yaml (FR-018-19)"),
    ]


class Cases(BaseModel):
    """
    one entry per canonical case id; a repeated id is a duplicate key, rejected by the loader
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    A1_1: Annotated[A1, Field(alias="A1")]
    A2_1: Annotated[A2, Field(alias="A2")]
    A3_1: Annotated[A3, Field(alias="A3")]
    B1_1: Annotated[B1, Field(alias="B1")]
    B2_1: Annotated[B2, Field(alias="B2")]
    C1_1: Annotated[C1, Field(alias="C1")]
    C2_1: Annotated[C2, Field(alias="C2")]
    C3_1: Annotated[C3, Field(alias="C3")]
    D1_1: Annotated[D1, Field(alias="D1")]
    D2_1: Annotated[D2, Field(alias="D2")]
    E1_1: Annotated[E1, Field(alias="E1")]
    E2_1: Annotated[E2, Field(alias="E2")]


class PitstudioCaseRegistry(BaseModel):
    """
    Case registry studio/cases.yaml read by the web build, the docs matrices and the CI checks (DC-018-01, spec 018-web-cases).
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
    schema_version: SchemaVersion
    categories: Annotated[
        Categories,
        Field(description="the five labelled groups of the case rail, keyed by category letter"),
    ]
    cases: Annotated[
        Cases,
        Field(description="one entry per canonical case id; a repeated id is a duplicate key, rejected by the loader"),
    ]
