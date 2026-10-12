# Generated from contracts/plausibility-pairs.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class RunId(RootModel[str]):
    root: Annotated[
        str,
        Field(max_length=64, pattern="^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$"),
    ]


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


class SchemaVersion(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^1\\.[0-9]+$")]


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


class PlausibilityPairIndex(BaseModel):
    """
    Task-B plausibility pair index written by the pair builder: calibrated and singly corrupted clips with the confirming detector statistic (DC-015-06, spec 015-vlm).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    seed: Annotated[int, Field(ge=0, le=9223372036854775807)]
    pairs: Annotated[list[Pair], Field(max_length=100, min_length=1)]
