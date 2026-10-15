# Generated from contracts/console.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


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


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class JobId(RootModel[str]):
    root: Annotated[str, Field(max_length=25, pattern="^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")]


class JobState(
    RootModel[Literal["queued", "running", "succeeded", "failed", "cancelled", "blocked", "held", "interrupted"]]
):
    root: Annotated[
        Literal["queued", "running", "succeeded", "failed", "cancelled", "blocked", "held", "interrupted"],
        Field(description="runner job states (spec 002 plan.md D3)"),
    ]


class ErrorItem(BaseModel):
    """
    one validation error: instance JSON pointer, schema keyword or loader code, one-line message
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    pointer: Annotated[str, Field(max_length=512, pattern="^(/[^/\\x00-\\x1f\\x7f]*)*$")]
    keyword: Annotated[str, Field(max_length=48, pattern="^[A-Za-z$][A-Za-z0-9_-]{0,47}$")]
    message: Annotated[str, Field(max_length=300, min_length=1, pattern="^[^\\x00-\\x1f\\x7f]*$")]


class ContractVersion1(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="a contract's schema_version, or its exact PitStudio $id",
            max_length=8,
            pattern="^[0-9]{1,3}\\.[0-9]{1,4}$",
        ),
    ]


class ContractVersion2(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="a contract's schema_version, or its exact PitStudio $id",
            max_length=120,
            pattern="^https://fsantibanezleal\\.github\\.io/PitStudio/contracts/[a-z][a-z0-9-]{0,31}\\.schema\\.json$",
        ),
    ]


class ContractVersion(RootModel[ContractVersion1 | ContractVersion2]):
    root: Annotated[
        ContractVersion1 | ContractVersion2,
        Field(description="a contract's schema_version, or its exact PitStudio $id"),
    ]


class Health(BaseModel):
    """
    GET /health (FR-003-06): the only body readable from the public site, so no free text, path, host or user name
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    status: Literal["ok"]
    console_version: Semver
    runner_version: Semver
    contracts: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9-]{0,31}$", max_length=32), ContractVersion],
        Field(description="schema stem -> contract version", max_length=128, min_length=1),
    ]


class RecipePath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^studio/recipes/(cases|_bench)/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?\\.yaml$",
        ),
    ]


class RecipeSummary(BaseModel):
    """
    one recipe file (FR-003-07); id and case are null when an invalid file does not yield them
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug | None
    case: CaseId | Literal["bench"] | None
    path: RecipePath
    sha256: Sha256
    stages: Annotated[int, Field(ge=0, le=64)]
    valid: bool
    errors: Annotated[list[ErrorItem], Field(max_length=20)]


class RecipeList(BaseModel):
    """
    GET /recipes
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    recipes: Annotated[list[RecipeSummary], Field(max_length=256)]


class Shards(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    done: Annotated[int, Field(ge=0, le=10000)]
    total: Annotated[int, Field(ge=1, le=10000)]


class ExitCode(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=6)]


class Reason(RootModel[str]):
    root: Annotated[str, Field(max_length=300, min_length=1, pattern="^[^\\x00-\\x1f\\x7f]*$")]


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class Variant(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z0-9][a-z0-9-]{0,31}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class ReleaseTag(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^assets-v[0-9]+\\.[0-9]{2}\\.[0-9]{3}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Package(RootModel[str]):
    root: Annotated[str, Field(max_length=100, pattern="^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class PythonVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=10, pattern="^3\\.[0-9]{1,2}(\\.[0-9]{1,3})?$")]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


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


class ArtefactKind(
    RootModel[
        Literal[
            "video",
            "image",
            "figure",
            "point-cloud",
            "mesh",
            "tiles",
            "splat",
            "onnx",
            "table",
            "trace",
            "shard",
            "field",
            "text",
            "model-card",
            "telemetry",
            "usd",
        ]
    ]
):
    root: Literal[
        "video",
        "image",
        "figure",
        "point-cloud",
        "mesh",
        "tiles",
        "splat",
        "onnx",
        "table",
        "trace",
        "shard",
        "field",
        "text",
        "model-card",
        "telemetry",
        "usd",
    ]


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


class LocalOnly(RootModel[Literal["measured locally, not published (licence)"]]):
    root: Literal["measured locally, not published (licence)"]


class Environment(
    RootModel[Literal["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]]
):
    root: Literal["studio", "isaac", "rtx", "isaaclab", "kit", "reason", "pipeline", "accel", "external"]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


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


class InputRef(BaseModel):
    """
    a source id, an artefact id of the same run, or a minephys knowledge-table row id
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: ArtefactId
    sha256: Sha256
    kind: Literal["source", "artefact", "knowledge"]


class OutputFile(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Relpath
    sha256: Sha256
    bytes: Annotated[int, Field(ge=0, le=9007199254740991)]


class PowerLimitEnforcedW(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class Gpu(BaseModel):
    """
    GPU record (data-model §2.2); null for CPU-only runs
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    backend: Literal["nvml", "fake"]
    index: Annotated[int, Field(ge=0, le=15)]
    name: Annotated[str, Field(max_length=128, min_length=1)]
    driver: Driver
    vram_total_bytes: Annotated[int, Field(ge=0, le=9007199254740991)]
    power_limit_enforced_w: PowerLimitEnforcedW | None


class EnvRecord(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Environment
    python: PythonVersion | None
    lock_sha256: Sha256
    versions: Annotated[
        dict[constr(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", max_length=100), Version],
        Field(description="package -> version as read from the lock", max_length=64),
    ]


class ErrorClass(
    RootModel[
        Literal[
            "oom",
            "timeout",
            "warmup-timeout",
            "invalid-output",
            "invalid-result",
            "nonzero-exit",
            "guard",
            "lock-timeout",
            "lock-not-held",
            "cancelled",
            "interrupted",
            "hold",
            "unknown",
        ]
        | None
    ]
):
    root: (
        Literal[
            "oom",
            "timeout",
            "warmup-timeout",
            "invalid-output",
            "invalid-result",
            "nonzero-exit",
            "guard",
            "lock-timeout",
            "lock-not-held",
            "cancelled",
            "interrupted",
            "hold",
            "unknown",
        ]
        | None
    )


class Attempt(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    n: Annotated[int, Field(ge=1, le=5)]
    error_class: ErrorClass
    fallback: Params | None = None
    duration_s: Annotated[float | None, Field(ge=0.0)] = None


class StageDeterminism(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[Literal["bitwise", "statistical", "none"], Field(alias="class")]
    rerun_check: Literal["pending", "pass", "fail", "not-applicable"]
    max_deviation: Annotated[float | None, Field(ge=0.0)] = None


class SampleHz(RootModel[float]):
    root: Annotated[float, Field(ge=1.0, le=4.0)]


class NSamples(RootModel[int]):
    root: Annotated[int, Field(ge=0)]


class GpuBusyPct(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mean: Annotated[float, Field(ge=0.0, le=100.0)]
    p50: Annotated[float, Field(ge=0.0, le=100.0)]
    p95: Annotated[float, Field(ge=0.0, le=100.0)]


class MemUsedPeakBytes(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9007199254740991)]


class PowerW(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mean: Annotated[float, Field(ge=0.0)]
    p95: Annotated[float, Field(ge=0.0)]
    max: Annotated[float, Field(ge=0.0)]


class PowerAtLimitFrac(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class EnergyJ(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class SmClockMhz(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mean: Annotated[float, Field(ge=0.0)]
    p5: Annotated[float, Field(ge=0.0)]


class TempCMax(RootModel[float]):
    root: Annotated[float, Field(ge=-100.0, le=200.0)]


class ClocksEventFrac(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sw_power_cap: Annotated[float, Field(ge=0.0, le=1.0)]
    sw_thermal: Annotated[float, Field(ge=0.0, le=1.0)]
    hw_thermal: Annotated[float, Field(ge=0.0, le=1.0)]
    hw_slowdown: Annotated[float, Field(ge=0.0, le=1.0)]
    power_brake: Annotated[float, Field(ge=0.0, le=1.0)]
    idle: Annotated[float, Field(ge=0.0, le=1.0)]


class NvencUtilPct(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mean: Annotated[float, Field(ge=0.0, le=100.0)]
    max: Annotated[float, Field(ge=0.0, le=100.0)]


UnavailableAdditionalProperty = TypeAliasType(
    "UnavailableAdditionalProperty", Annotated[str, Field(max_length=120, min_length=1)]
)


class TelemetrySummary(BaseModel):
    """
    per-stage GPU telemetry summary (data-model §2.4); a null field is named in `unavailable`
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    sample_hz: SampleHz | None
    n_samples: NSamples | None
    gpu_busy_pct: GpuBusyPct | None
    mem_used_peak_bytes: MemUsedPeakBytes | None
    power_w: PowerW | None
    power_at_limit_frac: PowerAtLimitFrac | None
    energy_j: EnergyJ | None
    sm_clock_mhz: SmClockMhz | None
    temp_c_max: TempCMax | None
    clocks_event_frac: ClocksEventFrac | None
    nvenc_util_pct: NvencUtilPct | None = None
    pcie_replays_delta: int | None
    unavailable: Annotated[
        dict[
            constr(
                pattern=r"^(sample_hz|n_samples|gpu_busy_pct|mem_used_peak_bytes|power_w|power_at_limit_frac|energy_j|sm_clock_mhz|temp_c_max|clocks_event_frac|nvenc_util_pct|pcie_replays_delta)$"
            ),
            UnavailableAdditionalProperty,
        ]
        | None,
        Field(description="field name -> reason it is null", max_length=12),
    ] = None


class ExitCode1(RootModel[int]):
    root: Annotated[int, Field(ge=-2147483648, le=2147483647)]


class Shards1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    total: Annotated[int, Field(ge=1, le=10000)]
    done: Annotated[int, Field(ge=0, le=10000)]


class Throughput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value: Annotated[float, Field(ge=0.0)]
    unit: Annotated[str, Field(max_length=32, min_length=1)]


class InteractionMs(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class RunMsT2(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class TraceBytes(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9007199254740991)]


class Measured(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tier: Literal["T2"]
    date: Date
    browser: Annotated[str, Field(max_length=64, min_length=1)]


class LaneMeasurements(BaseModel):
    """
    lane measurements (data-model §2.6); the lane value is checked against the gate by tools/check_contracts.py
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    web_drivable: bool
    max_asset_bytes: Annotated[int, Field(ge=0, le=9007199254740991)]
    interaction_ms: InteractionMs | None
    run_ms_t2: RunMsT2 | None
    trace_bytes: TraceBytes | None
    measured: Measured


class Vmaf(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    mean: Annotated[float, Field(ge=0.0, le=100.0)]
    p5: Annotated[float, Field(ge=0.0, le=100.0)]
    model: Annotated[str, Field(max_length=64, min_length=1)]


class NvencApi(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^[0-9]+\\.[0-9]+$")]


class Arg(RootModel[str]):
    root: Annotated[str, Field(max_length=200)]


class Encoder1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    ffmpeg_version: Annotated[str, Field(max_length=32, pattern="^n?[0-9]+(\\.[0-9]+){0,3}$")]
    build_sha256: Sha256
    nvenc_api: NvencApi | None
    args: Annotated[list[Arg], Field(max_length=64)]


class EncodeFps(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class Encoder(BaseModel):
    """
    encoder record of a video artefact (data-model §2.7)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    codec: Literal["av1", "h264"]
    profile: Annotated[str, Field(max_length=32, min_length=1)]
    pix_fmt: Annotated[str, Field(max_length=16, pattern="^[a-z0-9]{2,16}$")]
    width: Annotated[int, Field(ge=16, le=8192)]
    height: Annotated[int, Field(ge=16, le=8192)]
    fps: Annotated[float, Field(gt=0.0, le=240.0)]
    frames: Annotated[int, Field(ge=1, le=2147483647)]
    duration_s: Annotated[float, Field(gt=0.0)]
    bitrate_kbps: Annotated[float, Field(gt=0.0)]
    vmaf: Vmaf
    source_frames_sha256: Sha256
    encoder: Encoder1
    encode_fps: EncodeFps | None


class Recipe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    path: Annotated[Relpath, Field(description="relative to studio/recipes/")]
    sha256: Sha256


class Note(RootModel[str]):
    root: Annotated[str, Field(max_length=300)]


class Run1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    run_id: RunId
    manifest: Annotated[Relpath, Field(description="relative to web/public/assets/runs/")]
    sha256: Sha256


class JobCreated(BaseModel):
    """
    202 body of POST /jobs (FR-003-09); location equals the Location header
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    job_id: JobId
    location: Annotated[str, Field(max_length=31, pattern="^/jobs/[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")]


class RunSummary(BaseModel):
    """
    one run of the store (FR-003-12); manifest fields are null when the manifest is invalid, state is null when no queue record exists
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    run_id: RunId
    recipe: Slug | None
    created: UtcTimestamp | None
    profile: Slug | None
    state: JobState | None
    stages: Annotated[int, Field(ge=0, le=64)]
    published: bool
    valid: bool


class RunList(BaseModel):
    """
    GET /runs
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    runs: Annotated[list[RunSummary], Field(max_length=1000)]


class Problem(BaseModel):
    """
    application/problem+json error body (RFC 9457, FR-003-22); one-line texts, no stack trace
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    type: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^(about:blank|https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~%-]+)*)$",
        ),
    ]
    title: Annotated[str, Field(max_length=100, min_length=1, pattern="^[^\\x00-\\x1f\\x7f]*$")]
    status: Annotated[int, Field(ge=400, le=599)]
    detail: Annotated[str, Field(max_length=300, pattern="^[^\\x00-\\x1f\\x7f]*$")]
    errors: Annotated[list[ErrorItem] | None, Field(max_length=50)] = None


class ModulePath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=200,
            pattern="^[a-z_][a-z0-9_]{0,63}(\\.[a-z_][a-z0-9_]{0,63}){0,7}$",
        ),
    ]


class Probe(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9_]{0,31}$")]


class BinaryId(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9-]{1,31}$")]


class ValidatorId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class ParamValue13(RootModel[list[ParamValue0 | None]]):
    root: Annotated[
        list[ParamValue0 | None],
        Field(
            description="a parameter value with at most 1 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue12(
    RootModel[
        ParamValue0
        | ParamValue13
        | dict[
            constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64),
            ParamValue0 | None,
        ]
        | None
    ]
):
    root: Annotated[
        ParamValue0
        | ParamValue13
        | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue0 | None]
        | None,
        Field(description="a parameter value with at most 1 further level(s) of nesting"),
    ]


class ParamValue23(RootModel[list[ParamValue12]]):
    root: Annotated[
        list[ParamValue12],
        Field(
            description="a parameter value with at most 2 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue22(
    RootModel[
        ParamValue0 | ParamValue23 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue12] | None
    ]
):
    root: Annotated[
        ParamValue0
        | ParamValue23
        | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue12]
        | None,
        Field(description="a parameter value with at most 2 further level(s) of nesting"),
    ]


class ParamValue33(RootModel[list[ParamValue22]]):
    root: Annotated[
        list[ParamValue22],
        Field(
            description="a parameter value with at most 3 further level(s) of nesting",
            max_length=1024,
        ),
    ]


class ParamValue32(
    RootModel[
        ParamValue0 | ParamValue33 | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue22] | None
    ]
):
    root: Annotated[
        ParamValue0
        | ParamValue33
        | dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue22]
        | None,
        Field(description="a parameter value with at most 3 further level(s) of nesting"),
    ]


class Params1(RootModel[dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue32]]):
    root: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ParamValue32],
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
    oom_fallback: Annotated[list[Params1], Field(max_length=4, min_length=1)]


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


class Stage1(BaseModel):
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
    params: Params1 | None = None
    resources: Resources
    requires: Annotated[list[Probe] | None, Field(max_length=16)] = None
    binaries: Annotated[list[Binary] | None, Field(max_length=8)] = None
    determinism: Determinism
    retry: Retry | None = None
    timeout_s: Annotated[int, Field(ge=1, le=604800)]
    outputs: Annotated[list[Output], Field(max_length=64, min_length=1)]
    shardable: Shardable | None = None


class Recipe1(BaseModel):
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
    stages: Annotated[list[Stage1], Field(max_length=64, min_length=1)]


class StageKeyModel(BaseModel):
    """
    stage id plus optional variant
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: StageId
    variant: Variant | None = None


class Stage(BaseModel):
    """
    stage record (data-model §2.3)
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    key: StageKeyModel
    tool: ToolId
    env: EnvRecord
    cache_key: Sha256
    cache: Literal["hit", "miss"]
    status: Literal[
        "succeeded", "failed", "skipped", "cancelled", "blocked", "held", "interrupted", "env-disabled", "not_run"
    ]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    exit_code: ExitCode1 | None
    error_class: ErrorClass
    attempts: Annotated[list[Attempt], Field(max_length=5, min_length=1)]
    params: Params
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    shards: Shards1 | None = None
    determinism: StageDeterminism
    performance: Literal["public", "local-only"]
    wall_s: Annotated[float | None, Field(ge=0.0)] = None
    telemetry: TelemetrySummary | LocalOnly | None
    throughput: Throughput | None = None
    thermal_flag: bool
    log_tail: Annotated[str | None, Field(max_length=4000)] = None
    inputs: Annotated[list[InputRef], Field(max_length=32)]
    outputs: Annotated[list[OutputFile], Field(max_length=64)]


class Producer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tool: ToolId
    stage: StageKeyModel


class Artefact(BaseModel):
    """
    artefact record (data-model §2.5); git host: `path` under web/public/; release host: the asset file name
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    id: ArtefactId
    run_id: RunId
    git_sha: GitSha
    path: Relpath
    bytes: Annotated[int, Field(ge=0, le=9007199254740991)]
    sha256: Sha256
    media_type: Annotated[str | None, Field(max_length=128, pattern="^[a-z]+/[a-z0-9.+-]{1,64}$")] = None
    kind: ArtefactKind
    producer: Producer
    inputs: Annotated[list[InputRef], Field(max_length=32)]
    cases: Annotated[list[CaseId] | None, Field(max_length=12)] = None
    lane: Literal["live", "replay", "static"]
    lane_measurements: LaneMeasurements | None = None
    licence_class: LicenceClass
    spdx: SpdxId
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None
    asset_host: Literal["git", "release"]
    release_tag: ReleaseTag | None = None
    budget_class: Literal[
        "videos", "tiles-glb", "shards-clouds", "splats", "onnx", "runtimes", "own-code", "studio-showcase"
    ]
    encoder: Encoder | None = None


class Run(BaseModel):
    """
    run manifest (data-model §2.1)
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
    kind: Literal["run"]
    schema_version: SchemaVersion
    run_id: RunId
    recipe: Recipe
    git_sha: GitSha
    git_dirty: bool
    runner_version: Semver
    created: UtcTimestamp
    profile: Slug
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    published: bool
    launcher: Literal["uv", "test"]
    gpu: Gpu | None
    stages: Annotated[list[Stage], Field(max_length=64, min_length=1)]
    artefacts: Annotated[list[Artefact], Field(max_length=2000)]
    notes: Annotated[list[Note] | None, Field(max_length=20)] = None


class WebIndex(BaseModel):
    """
    published artefact index web/public/assets/manifest.json (data-model §2.8)
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
    kind: Literal["web-index"]
    schema_version: SchemaVersion
    generated: Date
    git_sha: GitSha
    runs: Annotated[list[Run1], Field(max_length=500)]
    artefacts: Annotated[list[Artefact], Field(max_length=2000)]


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


class Job(BaseModel):
    """
    a runner job record (FR-003-08); exit_code is the runner exit code of spec 002 plan.md D2
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    job_id: JobId
    recipe: Slug
    state: JobState
    run_id: RunId | None
    created: UtcTimestamp
    stage: StageKeyModel | None
    shards: Shards | None
    exit_code: ExitCode | None
    reason: Reason | None


class JobList(BaseModel):
    """
    GET /queue
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    jobs: Annotated[list[Job], Field(max_length=1000)]


class PitstudioConsoleResponseBodies(
    RootModel[Health | RecipeSummary | RecipeList | Job | JobList | JobCreated | RunSummary | RunList | Problem]
):
    root: Annotated[
        Health | RecipeSummary | RecipeList | Job | JobList | JobCreated | RunSummary | RunList | Problem,
        Field(
            description="Response bodies of the loopback console API (DC-003-01, spec 003-console).",
            title="PitStudio console response bodies",
        ),
    ]
