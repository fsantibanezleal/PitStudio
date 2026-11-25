# Generated from contracts/results.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class ThrottleFrac(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    sw_power_cap: Annotated[float, Field(ge=0.0, le=1.0)]
    sw_thermal: Annotated[float, Field(ge=0.0, le=1.0)]
    hw_thermal: Annotated[float, Field(ge=0.0, le=1.0)]
    hw_slowdown: Annotated[float, Field(ge=0.0, le=1.0)]
    power_brake: Annotated[float, Field(ge=0.0, le=1.0)]


class CriterionStatus(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    requirement: Annotated[str, Field(max_length=9, pattern="^SC-[0-9]{3}-[0-9]{2}$")]
    status: Literal["pass", "fail", "not-run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None


class DiffInterval(BaseModel):
    """
    95 % interval of the paired difference challenger - baseline, in the metric's unit.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    lo: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    hi: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    level: float
    method: Literal["paired-t", "paired-bootstrap"]
    resamples: Annotated[int | None, Field(ge=1000, le=1000000)] = None


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class EstimateInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lo: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    hi: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    level: float
    method: Literal["percentile-bootstrap", "wilson", "t"]


class Threshold(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    comparator: Literal["ge", "le"]
    value: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]


class Label(RootModel[str]):
    root: Annotated[str, Field(max_length=120, min_length=1)]


class Latency(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    p50: Annotated[float, Field(ge=0.0, le=10000000.0)]
    p95: Annotated[float, Field(ge=0.0, le=10000000.0)]


class NameEnEs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=120, min_length=1)]
    es: Annotated[str, Field(max_length=120, min_length=1)]


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


class Package(RootModel[str]):
    root: Annotated[str, Field(max_length=100, pattern="^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")]


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class AccelRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Slug
    backend: Literal["pytorch", "ort-cpu", "ort-cuda", "ort-tensorrt", "tensorrt"]
    precision: Literal["fp32", "fp16", "int8", "fp8"]
    status: Literal["accepted", "rejected", "build-failed", "not-run"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    latency_ms: Latency | None
    throughput_items_per_s: Annotated[float | None, Field(ge=0.0, le=1000000000000.0)]
    energy_j_per_inference: Annotated[float | None, Field(ge=0.0, le=1000000000.0)]
    accuracy_delta_pp: Annotated[float | None, Field(ge=-100.0, le=100.0)]
    parity: Literal["pass", "rejected", "not-run"]
    tensorrt_licence_sha256: Sha256 | None = None


class Conditions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    gpu: Annotated[str, Field(max_length=128, min_length=1)]
    driver: Driver
    power_limit_enforced_w: Annotated[float | None, Field(ge=0.0, le=10000.0)]
    throttle_frac: ThrottleFrac
    versions: Annotated[
        dict[constr(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"), Version] | None,
        Field(max_length=16),
    ] = None


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


class AccelerationBundle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    id: Slug
    title: NameEnEs
    cases: Annotated[list[CaseId], Field(max_length=12, min_length=1)]
    run_ids: Annotated[list[RunId], Field(max_length=32, min_length=1)]
    criteria: Annotated[list[CriterionStatus], Field(max_length=8, min_length=0)]
    kind: Literal["acceleration"]
    tab: Literal["acceleration"]
    conditions: Conditions
    rows: Annotated[list[AccelRow], Field(max_length=256, min_length=1)]


class MetricModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: ParamKey
    name: NameEnEs
    unit: Annotated[str, Field(max_length=32, min_length=1)]
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


class PairedRow(BaseModel):
    """
    Paired comparison; verdict by the decision rule of FR-020-22 on the oriented interval.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["paired"]
    group: Slug | None = None
    metric: MetricModel
    challenger: Label
    baseline: Label
    pairing_unit: NameEnEs
    n: Annotated[int, Field(ge=2, le=1000000)]
    interval: DiffInterval
    verdict: Literal["challenger-better", "baseline-better", "no-significant-difference"]


class SingleEventRow(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["single-event"]
    group: Slug | None = None
    metric: MetricModel
    challenger: Label
    baseline: Label
    n: Literal[1]
    challenger_value: float
    baseline_value: float
    verdict: Literal["single-real-event"]


class EstimateRow(BaseModel):
    """
    One system's metric with its interval, optionally against a pre-registered threshold.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["estimate"]
    group: Slug | None = None
    metric: MetricModel
    system: Label
    n: Annotated[int, Field(ge=1, le=1000000)]
    value: Annotated[float, Field(ge=-1000000000000000.0, le=1000000000000000.0)]
    interval: EstimateInterval | None = None
    threshold: Threshold | None = None


class McnemarRow(BaseModel):
    """
    Exact McNemar test; b = challenger right and baseline wrong, c = the reverse.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["mcnemar"]
    group: Slug | None = None
    metric: MetricModel
    challenger: Label
    baseline: Label
    pairing_unit: NameEnEs
    n: Annotated[int, Field(ge=1, le=1000000)]
    b: Annotated[int, Field(ge=0, le=1000000)]
    c: Annotated[int, Field(ge=0, le=1000000)]
    p_value: Annotated[float, Field(ge=0.0, le=1.0)]
    verdict: Literal["challenger-better", "baseline-better", "no-significant-difference"]


class ComparisonBundle(BaseModel):
    """
    Comparison rows shown together, never folded into a composite score (FR-020-21).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    id: Slug
    title: NameEnEs
    cases: Annotated[list[CaseId], Field(max_length=12, min_length=1)]
    run_ids: Annotated[list[RunId], Field(max_length=32, min_length=1)]
    criteria: Annotated[list[CriterionStatus], Field(max_length=8, min_length=0)]
    kind: Literal["comparison"]
    tab: Literal["learned-vs-classical", "sim-to-real", "dr-ablation", "isaac-lab", "cosmos"]
    rows: Annotated[
        list[PairedRow | McnemarRow | SingleEventRow | EstimateRow],
        Field(max_length=64, min_length=1),
    ]


class ResultsBundle(RootModel[ComparisonBundle | AccelerationBundle]):
    root: Annotated[
        ComparisonBundle | AccelerationBundle,
        Field(
            description="One published comparison web/public/results/<comparison-id>.json (DC-020-02, spec 020-web-knowledge).",
            title="Results bundle",
        ),
    ]
