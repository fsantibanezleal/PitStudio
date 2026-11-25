# Generated from contracts/parity-report.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class Semver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class Observables(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    repose_deg: Annotated[float | None, Field(ge=0.0)] = None
    runout_rel: Annotated[float | None, Field(ge=0.0)] = None
    discharge_rel: Annotated[float | None, Field(ge=0.0)] = None
    mass_drift_rel: Annotated[float | None, Field(ge=0.0)] = None


class MaxError(BaseModel):
    """
    largest observed error over all vectors and browsers, in the metric of the class
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    abs: Annotated[float | None, Field(ge=0.0)] = None
    rel: Annotated[float | None, Field(ge=0.0)] = None
    abs_px: Annotated[float | None, Field(ge=0.0)] = None
    objective_rel: Annotated[float | None, Field(ge=0.0)] = None
    z: Annotated[float | None, Field(description="binomial deviation in standard errors", ge=0.0)] = None
    mismatches: Annotated[
        int | None,
        Field(
            description="differing counts, labels, set members, words or hashes",
            ge=0,
            le=9007199254740991,
        ),
    ] = None
    top1_agreement: Annotated[float | None, Field(description="lowest observed agreement", ge=0.0, le=1.0)] = None
    observables: Observables | None = None


class Fixtures(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    files: Annotated[int, Field(ge=0, le=10000)]
    vectors: Annotated[int, Field(ge=0, le=10000000)]


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


class Observables1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    repose_deg: Annotated[float | None, Field(ge=0.0, le=1.5)] = None
    runout_rel: Annotated[float | None, Field(ge=0.0, le=0.05)] = None
    discharge_rel: Annotated[float | None, Field(ge=0.0, le=0.05)] = None
    mass_drift_rel: Annotated[float | None, Field(ge=0.0, le=0.005)] = None


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class ModulePath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^[a-z_][a-z0-9_]{0,63}(\\.[a-z_][a-z0-9_]{0,63}){0,7}$",
        ),
    ]


class ParityClass(
    RootModel[
        Literal[
            "analytical-closed-form",
            "analytical-iterative",
            "monte-carlo-count",
            "monte-carlo-binomial",
            "exact-stream",
            "min-cut",
            "rigid-body-hash",
            "label-map-exact",
            "wgsl-kernel",
            "wgsl-observables",
            "ml-wasm-fp32",
            "ml-webgpu-fp32",
            "ml-fp16",
            "detector-wasm",
            "detector-webgpu",
            "hosted",
        ]
    ]
):
    root: Annotated[
        Literal[
            "analytical-closed-form",
            "analytical-iterative",
            "monte-carlo-count",
            "monte-carlo-binomial",
            "exact-stream",
            "min-cut",
            "rigid-body-hash",
            "label-map-exact",
            "wgsl-kernel",
            "wgsl-observables",
            "ml-wasm-fp32",
            "ml-webgpu-fp32",
            "ml-fp16",
            "detector-wasm",
            "detector-webgpu",
            "hosted",
        ],
        Field(
            description="system class of spec 018 section 7.2; hosted = an engine of specs 007, 013 or 014 judged by its own suite"
        ),
    ]


class Reference(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[
        str,
        Field(
            description="reference package (PyPI or npm name)",
            max_length=142,
            pattern="^(@[a-z0-9-]{1,40}/)?[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
        ),
    ]
    version: Version
    callable: Annotated[
        ModulePath | None,
        Field(description="reference function, e.g. minephys.blasting.kuz_ram_x50"),
    ] = None


class Value1(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="JSON value of an engine input or output (64-bit integers as decimal or hex strings)",
            max_length=1024,
        ),
    ]


class SpawnKeyItem(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=4294967295)]


class Sample(RootModel[list[float]]):
    root: Annotated[list[float], Field(max_length=64, min_length=1)]


class Variates(BaseModel):
    """
    recorded variate stream of a Monte-Carlo vector
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    generator: Annotated[Literal["pcg64"], Field(description="numpy PCG64 seeded through SeedSequence")]
    entropy: Annotated[
        str,
        Field(
            description="SeedSequence entropy as a decimal integer",
            max_length=39,
            pattern="^(0|[1-9][0-9]{0,38})$",
        ),
    ]
    spawn_key: Annotated[list[SpawnKeyItem], Field(max_length=8)]
    samples: Annotated[
        list[Sample],
        Field(
            description="sample matrix, one row per Monte-Carlo sample",
            max_length=100000,
            min_length=1,
        ),
    ]


class Tolerance(BaseModel):
    """
    parity class and its tolerance; each value is capped at the spec value, so a looser tolerance fails
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[ParityClass, Field(alias="class")]
    rtol: Annotated[float | None, Field(description="relative tolerance", ge=0.0, le=0.0001)] = None
    atol_scale: Annotated[
        float | None,
        Field(
            description="absolute tolerance as a multiple of the output unit scale s_y (DC-018-02)",
            ge=0.0,
            le=1e-12,
        ),
    ] = None
    solver_tol: Annotated[
        float | None,
        Field(
            description="convergence tolerance of the reference solver; rtol = max(1e-9, 10 x solver_tol)",
            gt=0.0,
            le=1e-05,
        ),
    ] = None
    objective_rtol: Annotated[float | None, Field(ge=0.0, le=1e-10)] = None
    max_abs: Annotated[
        float | None,
        Field(
            description="maximum absolute difference (non-dimensional for WGSL kernels)",
            ge=0.0,
            le=0.01,
        ),
    ] = None
    max_abs_px: Annotated[float | None, Field(description="box tolerance in pixels", ge=0.0, le=1.0)] = None
    top1_agreement_min: Annotated[float | None, Field(ge=0.995, le=1.0)] = None
    sigma: Annotated[
        float | None,
        Field(description="binomial bound in standard errors, plus 1/N", gt=0.0, le=3.0),
    ] = None
    observables: Observables1 | None = None
    defined_by: Annotated[
        Literal["FR-007-10", "FR-007-15", "FR-007-20", "FR-007-32", "FR-007-39", "P-013-15", "FR-014-42"] | None,
        Field(description="requirement of the owning spec that fixes the class and tolerance"),
    ] = None


class Entry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    engine: EngineId
    engine_version: Semver
    tolerance: Tolerance
    fixtures: Fixtures
    max_error: MaxError | None = None
    browsers: Annotated[list[Literal["chromium", "firefox", "webkit"]], Field(max_length=3)]
    verdict: Literal["pass", "fail", "not_run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None


class PitstudioWebEngineParityReport(BaseModel):
    """
    Web engine parity report assets/parity-report.json of the built Pages artifact, written by the parity suite in CI (DC-018-05, spec 018-web-cases).
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
    git_sha: Annotated[GitSha, Field(description="the built commit")]
    generated: UtcTimestamp
    engines: Annotated[list[Entry], Field(max_length=128, min_length=1)]


class Value(RootModel[Optional[Union[float, bool, Value1, "Value2", "ValueMap"]]]):
    root: Annotated[
        Optional[Union[float, bool, Value1, "Value2", "ValueMap"]],
        Field(description="JSON value of an engine input or output (64-bit integers as decimal or hex strings)"),
    ]


class Value2(RootModel[list[Value | None]]):
    root: Annotated[
        list[Value | None],
        Field(
            description="JSON value of an engine input or output (64-bit integers as decimal or hex strings)",
            max_length=4194304,
        ),
    ]


class ValueMap(RootModel[dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Value | None]]):
    root: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Value | None],
        Field(max_length=64),
    ]


class Vector(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str | None, Field(max_length=64, pattern="^[a-z0-9][a-z0-9_-]{0,63}$")] = None
    input: Annotated[ValueMap, Field(description="engine input in SI units (DC-018-02)")]
    output: Annotated[ValueMap, Field(description="reference output")]
    variates: Variates | None = None


Value.model_rebuild()
