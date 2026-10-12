# Generated from contracts/vlm-record.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Sample(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Literal["stratified-random"]
    strata: Annotated[
        list[Literal["task", "type", "condition", "corruption"]],
        Field(max_length=4, min_length=1),
    ]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    n_full: Annotated[int, Field(ge=0, le=9007199254740991)]
    n_published: Annotated[int, Field(ge=0, le=9007199254740991)]
    selection_uses_correctness: Literal[False]


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class GitSha(RootModel[str]):
    root: Annotated[str, Field(max_length=40, pattern="^[0-9a-f]{40}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Date(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=10, pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"),
    ]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


class Notices(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cosmos: Literal["Built on NVIDIA Cosmos"]
    honesty: Literal["Zero-shot 2B VLM; not a safety system."]


class RecordLicenceClass(RootModel[Literal["display-only", "own"]]):
    root: Literal["display-only", "own"]


class Sampling(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    temperature: Literal[0]
    top_k: Literal[1]
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    max_new_tokens: Annotated[int, Field(ge=1, le=4096)]
    reasoning: bool


class Gpu(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    name: Annotated[str, Field(max_length=128, min_length=1)]
    driver: Driver


class Provenance(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    model: Literal["nvidia/Cosmos-Reason2-2B", "Qwen/Qwen3-VL-2B-Instruct"]
    revision: GitSha
    quantisation: Literal["q8_0", "bf16"]
    gguf_sha256: Sha256 | None
    llamacpp_build: Literal["b11381"] | None
    llamacpp_archive_sha256: Sha256 | None
    transformers_version: Version | None
    sampling: Sampling
    date: Date
    gpu: Gpu


class Condition(RootModel[Literal["day", "night", "dust", "rain"]]):
    root: Literal["day", "night", "dust", "rain"]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class ObjectClass(RootModel[Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]]):
    root: Literal["haul_truck", "shovel", "light_vehicle", "person", "boulder"]


class Location(RootModel[Literal["haul_road", "bench", "loading_area"]]):
    root: Literal["haul_road", "bench", "loading_area"]


class FileRef(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class CoordinateM(RootModel[float]):
    root: Annotated[float, Field(ge=-100000.0, le=100000.0)]


class Vec3M(RootModel[list[CoordinateM]]):
    root: Annotated[list[CoordinateM], Field(max_length=3, min_length=3)]


class Vec2M(RootModel[list[CoordinateM]]):
    root: Annotated[list[CoordinateM], Field(max_length=2, min_length=2)]


class RotationXyzwItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1.0, le=1.0)]


class Pose(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    translation_m: Vec3M
    rotation_xyzw: Annotated[list[RotationXyzwItem], Field(max_length=4, min_length=4)]


class PrimId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=512,
            pattern="^/[A-Za-z_][A-Za-z0-9_]{0,63}(/[A-Za-z_][A-Za-z0-9_]{0,63}){0,15}$",
        ),
    ]


class VisiblePx(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=67108864)]


class HalfExtentsMItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class Footprint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    centre_m: Vec2M
    half_extents_m: Annotated[list[HalfExtentsMItem], Field(max_length=2, min_length=2)]
    heading_deg: Annotated[float, Field(ge=-180.0, le=180.0)]


class Object(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    prim_id: PrimId
    class_: Annotated[ObjectClass, Field(alias="class")]
    asset_id: ArtefactId | None = None
    pose: Pose
    footprint: Footprint
    visible_px: VisiblePx
    in_frustum: bool


class BenchEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    edge_id: ArtefactId
    berm_present: bool
    visible_px: VisiblePx


class Image(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    width_px: Annotated[int, Field(ge=16, le=8192)]
    height_px: Annotated[int, Field(ge=16, le=8192)]


class Intrinsics(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    fx_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    fy_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    cx_px: Annotated[float, Field(ge=0.0, le=8192.0)]
    cy_px: Annotated[float, Field(ge=0.0, le=8192.0)]


class Camera(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    intrinsics: Intrinsics
    pose: Pose


class AnswerLabel(RootModel[Literal["yes", "no", "0", "1", "2", "3+"]]):
    root: Literal["yes", "no", "0", "1", "2", "3+"]


class Query(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    query_id: ArtefactId
    frame_id: ArtefactId
    frame_state_sha256: Sha256
    type: Annotated[int, Field(ge=1, le=6)]
    condition: Condition
    location: Location
    truth: AnswerLabel
    gate_subset: bool
    reasoning_subset: bool


class Corruption(
    RootModel[
        Literal[
            "gravity-x0.3", "zero-friction", "mass-injection", "time-reversal", "interpenetration", "frozen-particles"
        ]
    ]
):
    root: Literal[
        "gravity-x0.3", "zero-friction", "mass-injection", "time-reversal", "interpenetration", "frozen-particles"
    ]


class Clip(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    asset_id: ArtefactId
    path: Relpath
    sha256: Sha256
    duration_s: Annotated[float, Field(ge=5.0, le=8.0)]
    frame_count: Annotated[int, Field(ge=1, le=2000)]
    fps: Annotated[float, Field(gt=0.0, le=240.0)]
    camera_id: ArtefactId
    scene_id: ArtefactId


class SustainedS(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=8.0)]


class Confirmation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    statistic: Literal[
        "fitted_g_ratio",
        "repose_angle_deg",
        "mass_increase_pct",
        "reversed_frame_fraction",
        "deep_overlap_contact_fraction",
        "frozen_particle_fraction",
    ]
    value: Annotated[float, Field(ge=0.0, le=10000.0)]
    sustained_s: SustainedS | None
    own_detector_triggered: Literal[True]
    calibrated_detectors_clear: Literal[True]


class Pair(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pair_id: ArtefactId
    scenario: Literal["muck-pile-formation", "truck-dump", "bench-collapse"]
    source_run_id: RunId
    corruptions: Annotated[list[Corruption], Field(max_length=1, min_length=1)]
    calibrated: Clip
    corrupted: Clip
    confirmation: Confirmation


class ClassSet(RootModel[list[ObjectClass]]):
    root: Annotated[list[ObjectClass], Field(max_length=5)]


class RecordC(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    task: Literal["C"]
    record_id: ArtefactId
    arm: Literal["cosmos-q8_0", "cosmos-bf16", "qwen-base", "template-caption"]
    frames: Annotated[list[ArtefactId], Field(max_length=1, min_length=1)]
    condition: Condition
    question: Annotated[str, Field(max_length=300, min_length=1)]
    output: Annotated[str, Field(max_length=4000, min_length=0)]
    mentioned_classes: ClassSet
    visible_classes: ClassSet
    hallucinated_classes: ClassSet
    correct: bool
    licence_class: RecordLicenceClass
    provenance: Provenance | None


class RecordA(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    task: Literal["A"]
    record_id: ArtefactId
    query_id: ArtefactId
    arm: Literal["cosmos-q8_0", "cosmos-bf16", "qwen-base", "detector-rule", "constant"]
    frames: Annotated[list[ArtefactId], Field(max_length=1, min_length=1)]
    question_type: Annotated[int, Field(ge=1, le=6)]
    condition: Condition
    question: Annotated[str, Field(max_length=300, min_length=1)]
    output: Annotated[str, Field(max_length=32768, min_length=0)]
    parsed: Literal["yes", "no", "0", "1", "2", "3+", "unparseable"]
    truth: AnswerLabel
    correct: bool
    licence_class: RecordLicenceClass
    provenance: Provenance | None


class RecordB(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    task: Literal["B"]
    record_id: ArtefactId
    pair_id: ArtefactId
    arm: Literal["cosmos-q8_0", "cosmos-bf16", "qwen-base"]
    corruption: Corruption
    presentation: Literal["pair-calibrated-first", "pair-corrupted-first", "single-calibrated", "single-corrupted"]
    input_mode: Literal["native-video", "frame-list-approximation"]
    frames: Annotated[list[ArtefactId], Field(max_length=2, min_length=1)]
    question: Annotated[str, Field(max_length=300, min_length=1)]
    output: Annotated[str, Field(max_length=32768, min_length=0)]
    parsed: Literal["first", "second", "yes", "no", "unparseable"]
    truth: Literal["first", "second", "yes", "no"]
    correct: bool
    licence_class: RecordLicenceClass
    provenance: Provenance


class PublishedAnswerRecords(BaseModel):
    """
    Published, display-only answer records of the reason lane (stratified sample), written by studio publish (DC-015-04, spec 015-vlm).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    case: CaseId
    generated: Date
    git_sha: GitSha
    notices: Notices
    sample: Sample
    records: Annotated[list[RecordA | RecordB | RecordC], Field(max_length=2000, min_length=1)]
