# Generated from contracts/recipe.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class Variant(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z0-9][a-z0-9-]{0,31}$")]


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


class ModulePath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^[a-z_][a-z0-9_]{0,63}(\\.[a-z_][a-z0-9_]{0,63}){0,7}$",
        ),
    ]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class Probe(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9_]{0,31}$")]


class BinaryId(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9-]{1,31}$")]


class ValidatorId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class StageId(
    RootModel[
        Literal[
            "s00_download",
            "s05_synthesize",
            "s10_preprocess",
            "s20_feature_extraction",
            "s30_train",
            "s40_infer",
            "s50_evaluate",
            "s60_export",
            "s62_accel",
            "s64_bench",
            "st10_terrain",
            "st20_pit_design",
            "st30_assets",
            "st40_compose",
            "st45_validate",
            "st45b_kit_validate",
            "st50_physics",
            "st52_rtx_render",
            "st53_sensors",
            "st54_vehicles",
            "st55_sdg",
            "st56_encode",
            "st57_rain_lidar",
            "st58_kit_capture",
            "st58b_capture_splat",
            "st59_reason_bench",
            "st59a_vqa",
            "st59b_plausibility",
            "st59c_captions",
            "st60_il_train",
            "st61_il_mpm_eval",
        ]
    ]
):
    root: Literal[
        "s00_download",
        "s05_synthesize",
        "s10_preprocess",
        "s20_feature_extraction",
        "s30_train",
        "s40_infer",
        "s50_evaluate",
        "s60_export",
        "s62_accel",
        "s64_bench",
        "st10_terrain",
        "st20_pit_design",
        "st30_assets",
        "st40_compose",
        "st45_validate",
        "st45b_kit_validate",
        "st50_physics",
        "st52_rtx_render",
        "st53_sensors",
        "st54_vehicles",
        "st55_sdg",
        "st56_encode",
        "st57_rain_lidar",
        "st58_kit_capture",
        "st58b_capture_splat",
        "st59_reason_bench",
        "st59a_vqa",
        "st59b_plausibility",
        "st59c_captions",
        "st60_il_train",
        "st61_il_mpm_eval",
    ]


class Environment(
    RootModel[Literal["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]]
):
    root: Literal["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]


class ParamValue0(RootModel[constr(max_length=1024) | float | bool | None]):
    root: Annotated[
        constr(max_length=1024) | float | bool | None,
        Field(description="a scalar parameter value (non-finite numbers are rejected by the loader)"),
    ]


class ParamValue11(RootModel[list[ParamValue0 | None]]):
    root: Annotated[
        list[ParamValue0 | None],
        Field(
            description="a parameter value with at most 1 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue1(
    RootModel[
        ParamValue0
        | ParamValue11
        | dict[
            constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64),
            ParamValue0 | None,
        ]
        | None
    ]
):
    root: Annotated[
        ParamValue0
        | ParamValue11
        | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue0 | None]
        | None,
        Field(description="a parameter value with at most 1 further level(s) of nesting"),
    ]


class ParamValue21(RootModel[list[ParamValue1]]):
    root: Annotated[
        list[ParamValue1],
        Field(
            description="a parameter value with at most 2 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue2(
    RootModel[
        ParamValue0 | ParamValue21 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue1] | None
    ]
):
    root: Annotated[
        ParamValue0 | ParamValue21 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue1] | None,
        Field(description="a parameter value with at most 2 further level(s) of nesting"),
    ]


class ParamValue31(RootModel[list[ParamValue2]]):
    root: Annotated[
        list[ParamValue2],
        Field(
            description="a parameter value with at most 3 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue3(
    RootModel[
        ParamValue0 | ParamValue31 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue2] | None
    ]
):
    root: Annotated[
        ParamValue0 | ParamValue31 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue2] | None,
        Field(description="a parameter value with at most 3 further level(s) of nesting"),
    ]


class Params(RootModel[dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue3]]):
    root: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue3],
        Field(
            description="effective parameters; nesting depth <= 4 including this object",
            max_length=64,
        ),
    ]


class StageKey(BaseModel):
    """
    stage id plus optional variant
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: StageId
    variant: Variant | None = None


class StageInput1(BaseModel):
    """
    a source (logical id + SHA-256) or an upstream stage; never a path
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    sha256: Sha256


class StageInput2(BaseModel):
    """
    a source (logical id + SHA-256) or an upstream stage; never a path
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    stage: StageId
    variant: Variant | None = None
    output: Relpath | None = None


class StageInput(RootModel[StageInput1 | StageInput2]):
    root: Annotated[
        StageInput1 | StageInput2,
        Field(description="a source (logical id + SHA-256) or an upstream stage; never a path"),
    ]


class Resources(BaseModel):
    """
    estimates in GiB (2^30 B)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    gpu: Literal["exclusive", "nvenc", "none"]
    vram_gib_est: Annotated[float | None, Field(gt=0.0, le=256.0)] = None
    disk_gib_est: Annotated[float | None, Field(ge=0.0, le=10000.0)] = None
    cpu: Annotated[int | None, Field(ge=1, le=256)] = None


class Determinism1(BaseModel):
    """
    `bitwise` shorthand, or a class object
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[Literal["bitwise"], Field(alias="class")]


class Observables(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rtol: Annotated[float, Field(ge=0.0, le=1.0)]
    atol: Annotated[float, Field(ge=0.0)]


class Determinism2(BaseModel):
    """
    `bitwise` shorthand, or a class object
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[Literal["statistical"], Field(alias="class")]
    observables: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), Observables],
        Field(description="observable -> tolerance", max_length=32, min_length=1),
    ]


class Determinism3(BaseModel):
    """
    `bitwise` shorthand, or a class object
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[Literal["none"], Field(alias="class")]
    reason: Annotated[str, Field(max_length=300, min_length=10)]


class Determinism(RootModel[Literal["bitwise"] | Determinism1 | Determinism2 | Determinism3]):
    root: Annotated[
        Literal["bitwise"] | Determinism1 | Determinism2 | Determinism3,
        Field(description="`bitwise` shorthand, or a class object"),
    ]


class Binary(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: BinaryId
    sha256: Sha256


class Retry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    oom_fallback: Annotated[list[Params], Field(max_length=4, min_length=1)]


class Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    schema_: Annotated[ValidatorId, Field(alias="schema")]
    publish: bool | None = None


class Shardable(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    shard_size: Annotated[int, Field(ge=1, le=10000000)]
    total: Annotated[int, Field(ge=1, le=1000000000)]


class Stage(BaseModel):
    """
    recipe stage (data-model §3.2); `env` is bound to `id` (§3.3)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: StageId
    variant: Variant | None = None
    env: Environment
    tool: ToolId
    entry: ModulePath
    inputs: Annotated[list[StageInput], Field(max_length=32)]
    params: Params | None = None
    resources: Resources
    requires: Annotated[list[Probe] | None, Field(max_length=16)] = None
    binaries: Annotated[list[Binary] | None, Field(max_length=8)] = None
    determinism: Determinism
    retry: Retry | None = None
    timeout_s: Annotated[int, Field(ge=1, le=604800)]
    outputs: Annotated[list[Output], Field(max_length=64, min_length=1)]
    shardable: Shardable | None = None


class Recipe(BaseModel):
    """
    runner recipe (data-model §3.1)
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
    id: Slug
    case: CaseId | Literal["bench"]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    description: Annotated[str | None, Field(max_length=500)] = None
    stages: Annotated[list[Stage], Field(max_length=64, min_length=1)]


class JobRequest(BaseModel):
    """
    body of the console's POST /jobs (data-model §3.5); never an inline recipe
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    recipe: Slug
    stages: Annotated[list[StageKey] | None, Field(max_length=64, min_length=1)] = None
    force: bool | None = False
    rerun_check: bool | None = False
    profile: Slug


class PitstudioRecipe(RootModel[Recipe]):
    root: Annotated[
        Recipe,
        Field(
            description="Runner recipes and the console job request (DC-001-02, spec 001-contracts).",
            title="PitStudio recipe",
        ),
    ]
