# Generated from contracts/detection-eval.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Seed(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9223372036854775807)]


class HonestyLabel(RootModel[Literal["calibrated synthetic — not validated against real data"]]):
    root: Literal["calibrated synthetic — not validated against real data"]


class Model(RootModel[Literal["d-fine-n", "d-fine-s", "rf-detr-seg-n"]]):
    root: Literal["d-fine-n", "d-fine-s", "rf-detr-seg-n"]


class Precision(RootModel[Literal["fp32", "fp16", "int8"]]):
    root: Literal["fp32", "fp16", "int8"]


class TrainingArm(RootModel[Literal["S", "U"]]):
    root: Literal["S", "U"]


class ClassName(RootModel[Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]]):
    root: Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]


class ProbeClass(RootModel[Literal["haul_truck", "shovel", "light_vehicle", "person"]]):
    root: Literal["haul_truck", "shovel", "light_vehicle", "person"]


class Unit(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1.0)]


class Reason(RootModel[str]):
    root: Annotated[str, Field(max_length=300, min_length=1)]


class Interval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower: Unit
    upper: Unit


class DifferenceInterval(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    lower: Annotated[float, Field(ge=-1.0, le=1.0)]
    upper: Annotated[float, Field(ge=-1.0, le=1.0)]


class Protocol(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    implementation: Literal["pycocotools"]
    implementation_version: Version
    iou_thresholds: Literal["0.50:0.05:0.95"]
    recall_points: Literal[101]
    max_dets: Literal[100]
    area: Literal["all"]
    min_support: Literal[100]


class ClusterBootstrap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[2000]
    method: Literal["cluster-percentile"]
    cluster: Literal["test-scenario-seed"]
    level: float
    seed: Seed


class FamilyStatus(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    family: Literal["pit", "crusher"]
    status: Literal["run", "not run"]
    reason: Reason | None = None


class ClassResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Model
    precision: Precision
    training_arm: TrainingArm
    family: Literal["pit", "crusher", "pooled"]
    task: Literal["box", "mask"]
    class_: Annotated[ClassName, Field(alias="class")]
    support: Annotated[int, Field(ge=0, le=10000000)]
    ap50: Unit | None = None
    ap50_95: Unit | None = None
    ap50_interval: Interval | None = None
    ap50_95_interval: Interval | None = None
    descriptive: bool
    honesty_label: HonestyLabel
    sim_to_real: Literal["not measured", "measured"]


class SummaryResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Model
    precision: Precision
    training_arm: TrainingArm
    family: Literal["pit", "crusher", "pooled"]
    task: Literal["box", "mask"]
    metric: Literal["map50", "mask_ap50"]
    value: Unit | None = None
    interval: Interval | None = None
    classes_included: Annotated[list[ClassName], Field(max_length=5)]
    descriptive: bool


class CorruptionPoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Model
    precision: Precision
    training_arm: TrainingArm
    metric: Literal["map50", "mask_ap50"]
    corruption: Literal["dust", "night", "rain"]
    severity: Annotated[int, Field(ge=1, le=5)]
    m_clean: Annotated[float, Field(gt=0.0, le=1.0)]
    m_corrupted: Unit
    delta_rel_pct: Annotated[float, Field(ge=-100000.0, le=100.0)]
    descriptive: bool


class Bootstrap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[10000]
    method: Literal["paired-cluster-percentile"]
    cluster: Literal["test-scenario-seed"]
    level: float
    identical_resample_indices: Literal[True]
    seed: Seed


class DrAblation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["d-fine-s"]
    precision: Literal["fp32"]
    metric: Literal["map50"]
    family: Literal["pit"]
    arm_a: Literal["S"]
    arm_b: Literal["U"]
    difference: Annotated[float, Field(ge=-1.0, le=1.0)]
    interval: DifferenceInterval
    bootstrap: Bootstrap
    verdict: Literal["better", "worse", "no significant difference"]
    training_runs_per_arm: Annotated[int, Field(ge=1, le=100)]
    test_seeds: Annotated[int, Field(ge=2, le=100000)]
    test_images: Annotated[int, Field(ge=1, le=1000000)]


class SupportShortfall(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    family: Literal["pit", "crusher", "pooled"]
    class_: Annotated[ClassName, Field(alias="class")]
    count: Annotated[int, Field(ge=0, le=99)]


class Acceptance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    criterion: Literal["SC-009-01", "SC-009-02", "SC-009-03", "SC-009-05", "SC-009-06"]
    model: Model
    precision: Precision
    corruption: Literal["dust", "night", "rain"] | None = None
    severity: Annotated[int | None, Field(ge=1, le=2)] = None
    statistic: Literal["map50", "mask_ap50", "delta_rel_pct", "abs_delta_mask_ap50_pp"]
    value: Annotated[float | None, Field(ge=-100000.0, le=100.0)] = None
    threshold: Annotated[float, Field(ge=0.0, le=100.0)]
    verdict: Literal["pass", "fail", "not evaluable (insufficient support)", "not run"]
    insufficient_support: Annotated[list[SupportShortfall] | None, Field(max_length=15, min_length=1)] = None
    reason: Reason | None = None


class ProbeClassResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["d-fine-n", "d-fine-s"]
    class_: Annotated[ProbeClass, Field(alias="class")]
    support: Annotated[int, Field(ge=0, le=100000)]
    ap50: Unit
    ap50_interval: Interval


class LabellerBMap50Item(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["d-fine-n", "d-fine-s"]
    map50: Unit


class AgreementItem(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    class_: Annotated[ProbeClass, Field(alias="class")]
    box_f1: Unit
    iou_threshold: float


class Bootstrap1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    resamples: Literal[2000]
    method: Literal["image-percentile"]
    level: float
    seed: Seed


class RealProbe(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    images: Annotated[int, Field(ge=1, le=200)]
    excluded_images: Annotated[int, Field(ge=0, le=100000)]
    ground_truth: Literal["labeller-a"]
    per_class: Annotated[list[ProbeClassResult], Field(max_length=8, min_length=1)]
    labeller_b_map50: Annotated[list[LabellerBMap50Item], Field(max_length=2, min_length=1)]
    agreement: Annotated[list[AgreementItem], Field(max_length=4, min_length=1)]
    bootstrap: Bootstrap1
    aggregate_only: Literal[True]


class RejectedInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    input: Relpath
    reason: Reason


class DetectionEvaluationReport(BaseModel):
    """
    Perception evaluation report of s50_evaluate (per model, precision, family and class AP with intervals and support; corruption curves; DR ablation; sim-to-real status, honesty label and verdicts) (DC-009-05, spec 009-perception).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    run_id: RunId
    test_data: Literal["synthetic held-out"]
    honesty_label: HonestyLabel
    sim_to_real: Literal["not measured", "measured"]
    protocol: Protocol
    bootstrap: ClusterBootstrap
    families: Annotated[list[FamilyStatus], Field(max_length=2, min_length=1)]
    per_class: Annotated[list[ClassResult], Field(max_length=1000)]
    summary: Annotated[list[SummaryResult], Field(max_length=200)]
    corruption: Annotated[list[CorruptionPoint], Field(max_length=2000)]
    dr_ablation: DrAblation
    acceptance: Annotated[list[Acceptance], Field(max_length=200)]
    real_probe: RealProbe | None = None
    rejected_inputs: Annotated[list[RejectedInput] | None, Field(max_length=100)] = None
