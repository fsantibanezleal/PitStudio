# Generated from contracts/export-parity-report.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class MaxAbsError(RootModel[float]):
    root: Annotated[float, Field(ge=0.0)]


class Precision(RootModel[Literal["fp32", "fp16", "int8", "fp8"]]):
    root: Literal["fp32", "fp16", "int8", "fp8"]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class LocalOnly(RootModel[Literal["measured locally, not published (licence)"]]):
    root: Literal["measured locally, not published (licence)"]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class Backend(RootModel[Literal["pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt", "tensorrt-rtx"]]):
    root: Literal["pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt", "tensorrt-rtx"]


class Status(RootModel[Literal["pass", "rejected", "build-failed", "not_run"]]):
    root: Literal["pass", "rejected", "build-failed", "not_run"]


class Reason(RootModel[str]):
    root: Annotated[str, Field(max_length=300, min_length=1)]


class Fraction(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class QuantileMs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    value_ms: Annotated[float, Field(ge=0.0, le=3600000.0)]
    lo_ms: Annotated[float, Field(ge=0.0, le=3600000.0)]
    hi_ms: Annotated[float, Field(ge=0.0, le=3600000.0)]


class Bootstrap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[2000]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    level: float


class LatencyEntry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    regime: Literal["spaced", "sustained"]
    scope: Literal["gpu-compute", "end-to-end"]
    gap_ms: Annotated[float, Field(ge=0.0, le=200.0)]
    warmup_s: Annotated[float, Field(ge=5.0, le=600.0)]
    iterations: Annotated[int, Field(ge=50, le=1000)]
    timed_s: Annotated[float, Field(gt=0.0, le=3600.0)]
    p50: QuantileMs
    p90: QuantileMs
    p95: QuantileMs
    p99: QuantileMs
    bootstrap: Bootstrap


class ThroughputEntry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sweep: Literal["batch", "particles"]
    size: Annotated[int, Field(ge=1, le=10000)]
    iterations: Annotated[int, Field(ge=1, le=1000000000)]
    elapsed_s: Annotated[float, Field(gt=0.0, le=86400.0)]
    samples_per_s: Annotated[float, Field(ge=0.0, le=1000000000000.0)]


class CameraStreams(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    frame_w_px: Literal[3840]
    frame_h_px: Literal[2160]
    tile_px: Literal[640]
    overlap_px: Literal[64]
    n_tiles: Literal[28]
    fps: Literal[10]
    best_batch: Literal[1, 4, 16, 64]
    tiles_per_s: Annotated[float, Field(ge=0.0, le=1000000000.0)]
    streams: Annotated[int, Field(ge=0, le=10000000)]
    recall: Fraction
    recall_score_min: float
    recall_iou_min: float


class Rtol(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=0.1)]


class Atol(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=0.1)]


class MetricDeltaPp(RootModel[float]):
    root: Annotated[float, Field(ge=-100.0, le=100.0)]


class Parity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    verdict: Literal["pass", "rejected"]
    reference: Literal["pytorch-fp32-golden"]
    rtol: Rtol | None
    atol: Atol | None
    max_abs_error: MaxAbsError | None
    mismatch_fraction: Fraction | None
    metric_delta_pp: MetricDeltaPp | None
    mask_iou: Fraction | None
    tf32_cleared: Literal[True]


class PowerLimitEnforcedW(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000.0)]


class Fingerprint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    gpu_name: Annotated[str, Field(max_length=128, min_length=1)]
    driver: Driver
    ort_version: Version
    torch_version: Version
    onnx_sha256: Sha256
    engine_sha256: Sha256 | None
    power_limit_enforced_w: PowerLimitEnforcedW | None
    power_source: Literal["ac", "battery"]
    os_power_mode: Literal["best-power-efficiency", "balanced", "best-performance"]
    tensorrt_licence_sha256: Sha256 | None


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class Tolerance1(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class Tolerance(RootModel[Tolerance1 | None]):
    root: Tolerance1 | None


class GoldenSet(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    split: Literal["validation", "held-out"]
    inputs: Annotated[list[Sha256], Field(max_length=5000, min_length=200)]


class Argmax(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    output: Annotated[str, Field(max_length=64, pattern="^[A-Za-z_][A-Za-z0-9_]{0,63}$")]
    gap_threshold: float
    rows: Annotated[int, Field(ge=0, le=9007199254740991)]
    rows_small_gap: Annotated[int, Field(ge=0, le=9007199254740991)]
    agreement: Fraction


class Metric(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ParamKey
    unit: Literal["pct"]
    fp32: Annotated[float, Field(ge=0.0, le=100.0)]
    variant: Annotated[float, Field(ge=0.0, le=100.0)]
    delta_pp: Annotated[float, Field(ge=-100.0, le=100.0)]


class Tolerances(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rtol: Tolerance | None
    atol: Tolerance | None
    max_abs: Tolerance | None
    metric_delta_pp_max: Tolerance | None
    mask_iou_min: Fraction | None


class ExportParityReport(BaseModel):
    """
    Parity report of one model variant at layer 1, 2 or 4 against the PyTorch fp32 golden outputs, written by s60_export and s64_bench (DC-016-03, spec 016-export-acceleration).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    run_id: RunId
    git_sha: GitSha
    layer: Literal[1, 2, 4]
    model: Slug
    variant: Literal["deployed", "parity"]
    precision: Precision
    backend: Literal["ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt"]
    tensorrt_version: Version | None
    onnx_sha256: Sha256
    engine_sha256: Sha256 | None
    golden_set: GoldenSet
    tolerances: Tolerances
    max_abs_error: MaxAbsError | None
    mismatch_fraction: Fraction | None
    argmax: Argmax | None
    metric: Metric | None
    mask_iou: Fraction | None
    verdict: Literal["pass", "rejected"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    fixture: bool | None = None
