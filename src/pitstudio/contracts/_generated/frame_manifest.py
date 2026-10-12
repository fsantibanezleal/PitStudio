# Generated from contracts/frame-manifest.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class ToolId(RootModel[str]):
    root: Annotated[str, Field(max_length=48, pattern="^[a-z][a-z0-9-]{1,47}$")]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Variant(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z0-9][a-z0-9-]{0,31}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


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


class Semver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$")]


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


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


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


class ExitCode(RootModel[int]):
    root: Annotated[int, Field(ge=-2147483648, le=2147483647)]


class Shards(BaseModel):
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


class StageKey(BaseModel):
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
    key: StageKey
    tool: ToolId
    env: EnvRecord
    cache_key: Sha256
    cache: Literal["hit", "miss"]
    status: Literal[
        "succeeded", "failed", "skipped", "cancelled", "blocked", "held", "interrupted", "env-disabled", "not_run"
    ]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    exit_code: ExitCode | None
    error_class: ErrorClass
    attempts: Annotated[list[Attempt], Field(max_length=5, min_length=1)]
    params: Params
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    shards: Shards | None = None
    determinism: StageDeterminism
    performance: Literal["public", "local-only"]
    wall_s: Annotated[float | None, Field(ge=0.0)] = None
    telemetry: TelemetrySummary | LocalOnly | None
    throughput: Throughput | None = None
    thermal_flag: bool
    log_tail: Annotated[str | None, Field(max_length=4000)] = None
    inputs: Annotated[list[InputRef], Field(max_length=32)]
    outputs: Annotated[list[OutputFile], Field(max_length=64)]


class Producer1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tool: ToolId
    stage: StageKey


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
    producer: Producer1
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


class Producer(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tool: ToolId
    stage: StageKey


class FrameManifest(BaseModel):
    """
    Lossless PNG frame sequence handed by a render or replay stage to st56_encode (DC-006-01, spec 006-media-telemetry).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["frame-manifest"]
    schema_version: SchemaVersion
    clip: Annotated[
        Slug,
        Field(description="clip name; outputs are <clip>.av1.mp4, <clip>.h264.mp4 and <clip>.webp (FR-006-13)"),
    ]
    run_id: RunId | None = None
    producer: Producer
    performance: Annotated[
        Literal["public", "local-only"],
        Field(
            description="performance class of the producer tool; local-only producers' timings never appear downstream (FR-006-14)"
        ),
    ]
    fps: Annotated[Literal[24, 25, 30, 50, 60], Field(description="source frame rate (FR-006-12)")]
    frames: Annotated[
        int,
        Field(
            description="frame count; at least 2 (FR-006-12); at most 10 minutes at 60 fps",
            ge=2,
            le=36000,
        ),
    ]
    width: Annotated[int, Field(ge=1920, le=8192)]
    height: Annotated[int, Field(ge=1080, le=8192)]
    bit_depth: Literal[8, 16]
    colour_space: Annotated[
        Literal["srgb", "bt709"],
        Field(description="transfer and primaries of the RGB frames"),
    ]
    format: Literal["png"]
    directory: Annotated[
        Relpath | None,
        Field(description="folder of the frames inside the stage's input folder"),
    ] = None
    frame_pattern: Annotated[
        str,
        Field(
            description="printf-style frame file name, e.g. frame_%05d.png; never a path",
            max_length=64,
            pattern="^([a-z0-9][a-z0-9_-]{0,47})?%0[3-9]d[.]png$",
        ),
    ]
    first_index: Annotated[int, Field(ge=0, le=99999999)]
    source_frames_sha256: Annotated[
        Sha256,
        Field(description="SHA-256 of the ordered list of per-frame SHA-256 digests (P-006-06)"),
    ]
    frame_sha256: Annotated[
        list[Sha256] | None,
        Field(description="per-frame digests in frame order", max_length=36000),
    ] = None
