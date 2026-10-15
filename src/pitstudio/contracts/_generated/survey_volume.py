# Generated from contracts/survey-volume.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Crs(RootModel[str]):
    root: Annotated[str, Field(max_length=12, pattern="^(EPSG:[0-9]{4,6}|local)$")]


class Errors(BaseModel):
    """
    Error metrics of FR-017-39; reported only, with no pass field (SC-017-06).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    fill_pct: Annotated[float, Field(ge=-100.0, le=10000.0)]
    cut_pct: Annotated[float, Field(ge=-100.0, le=10000.0)]
    floor_fill_pct: Annotated[float, Field(ge=-100.0, le=10000.0)]
    floor_cut_pct: Annotated[float, Field(ge=-100.0, le=10000.0)]
    reprojection_rmse_px: Annotated[float | None, Field(ge=0.0, le=1000.0)]
    alignment_rmse_m: Annotated[float | None, Field(ge=0.0, le=1000.0)]
    depth_abs_median_m: Annotated[float | None, Field(ge=0.0, le=1000.0)]
    gsd_cm_per_px: Annotated[float, Field(gt=0.0, le=100.0)]
    registration_ratio: Annotated[float | None, Field(ge=0.0, le=1.0)]


class ShapeItem(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=65536)]


class Grid(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    cell_m: Annotated[float, Field(gt=0.0, le=1000.0)]
    shape: Annotated[list[ShapeItem], Field(max_length=2, min_length=2)]
    origin_m: Annotated[list[float], Field(max_length=2, min_length=2)]
    crs: Crs


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


class Vertice(RootModel[list[float]]):
    root: Annotated[list[float], Field(max_length=2, min_length=2)]


class Polygon(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    vertices: Annotated[list[Vertice], Field(max_length=10000, min_length=3)]
    source: Annotated[str, Field(max_length=300, min_length=1)]
    overlap_ratio: Annotated[float | None, Field(ge=0.0, le=1.0)] = None


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Resampling(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    method: Literal["none", "bilinear"]
    source_crs: Crs | None = None


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


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


class Surface(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    epoch: Annotated[str | None, Field(max_length=32, min_length=1)] = None
    project: Annotated[str | None, Field(max_length=200, min_length=1)] = None
    crs: Crs | None = None
    vertical_datum: Annotated[str | None, Field(max_length=64, min_length=1)] = None
    rmse_z_m: Annotated[float | None, Field(ge=0.0, le=100.0)] = None


class Grid1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class VerticalTransform(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["none", "constant", "grid"]
    offset_m: Annotated[float | None, Field(ge=-1000.0, le=1000.0)] = None
    grid: Grid1 | None = None
    source: Annotated[str | None, Field(max_length=300, min_length=1)] = None


class Surfaces(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    before: Surface
    after: Surface


class Cells(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    valid: Annotated[int, Field(ge=0, le=4294967296)]
    nodata: Annotated[int, Field(ge=0, le=4294967296)]
    nodata_fraction: Annotated[float, Field(ge=0.0, le=1.0)]


class UncertaintyM3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    uncorrelated: Annotated[float, Field(ge=0.0, le=1000000000000.0)]
    correlated: Annotated[float, Field(ge=0.0, le=1000000000000.0)]


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: SpdxId
    licence_class: LicenceClass
    attribution: Annotated[str | None, Field(max_length=1000, min_length=1)] = None


class Volume(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    scope: Literal["real", "synthetic"]
    method: Literal["dem-differencing", "photogrammetric", "splat"]
    status: Literal["ok", "not_run", "failed"]
    reason: Annotated[str | None, Field(max_length=300, min_length=1)] = None
    label: Literal["measurement, not validation"] | None = None
    licence: Licence | None = None
    flight: Slug | None = None
    seed: Annotated[int | None, Field(ge=0, le=9223372036854775807)] = None
    surfaces: Surfaces | None = None
    grid: Grid | None = None
    resampling: Resampling | None = None
    vertical_transform: VerticalTransform | None = None
    polygon: Polygon | None = None
    v_cut_m3: Annotated[float | None, Field(ge=0.0, le=1000000000000.0)] = None
    v_fill_m3: Annotated[float | None, Field(ge=0.0, le=1000000000000.0)] = None
    v_net_m3: Annotated[float | None, Field(ge=-1000000000000.0, le=1000000000000.0)] = None
    cells: Cells | None = None
    uncertainty_m3: UncertaintyM3 | None = None
    errors: Errors | None = None


class E2SurveyVolumes(BaseModel):
    """
    Cut, fill and net volumes with uncertainty and error metrics written by s50_evaluate (DC-017-04, spec 017-planning-survey).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200, min_length=0)] = None
    schema_version: Annotated[str, Field(max_length=8, pattern="^1\\.[0-9]+$")]
    volumes: Annotated[list[Volume], Field(max_length=1024, min_length=1)]
