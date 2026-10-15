# Generated from contracts/muck-pile-render.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType


class Image(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    width_px: Literal[1024]
    height_px: Literal[1024]
    colour_space: Literal["sRGB"]


class Intrinsics(BaseModel):
    """
    pinhole intrinsics of the 1,024 x 1,024 view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    focal_length_px: Annotated[float, Field(gt=0.0, le=100000.0)]
    cx_px: Annotated[float, Field(ge=0.0, le=1024.0)]
    cy_px: Annotated[float, Field(ge=0.0, le=1024.0)]


InstanceToFragmentAdditionalProperty = TypeAliasType(
    "InstanceToFragmentAdditionalProperty", Annotated[int, Field(ge=1, le=1000000)]
)


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


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


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


class InstanceMask(BaseModel):
    """
    instance ids equal fragment ids; 0 = background
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    dtype: Literal["uint16", "uint32"]


class Depth(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    dtype: Literal["float32"]
    unit: Literal["m"]


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: SpdxId
    licence_class: LicenceClass


class File(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256


class Tile(BaseModel):
    """
    one non-overlapping 512 x 512 tile of the view
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tile: Annotated[int, Field(ge=0, le=3)]
    x0_px: Literal[0, 512]
    y0_px: Literal[0, 512]
    size_px: Literal[512]
    render: File
    instance_mask: File
    depth: File


class MuckPileRenderIndex(BaseModel):
    """
    Render-index record of one view of a settled synthetic muck pile written by st55_sdg (DC-012-04, spec 012-fragmentation).
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
    synthetic: Literal[True]
    stage: Literal["st55_sdg"]
    pile_seed: Annotated[int, Field(ge=0, le=4294967295)]
    view: Annotated[int, Field(ge=0, le=63)]
    image: Image
    render: File
    instance_mask: Annotated[
        InstanceMask,
        Field(description="instance ids equal fragment ids; 0 = background"),
    ]
    depth: Depth
    intrinsics: Annotated[Intrinsics, Field(description="pinhole intrinsics of the 1,024 x 1,024 view")]
    tiles: Annotated[list[Tile], Field(max_length=4, min_length=4)]
    instance_to_fragment: Annotated[
        dict[constr(pattern=r"^[1-9][0-9]{0,6}$", max_length=7), InstanceToFragmentAdditionalProperty],
        Field(
            description="visible instance id -> fragment id (at most one instance per 4 px of the view)",
            max_length=262144,
        ),
    ]
    fragment_table: File
    licence: Licence
