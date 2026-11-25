# Generated from contracts/coco-instances.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class CocoId(RootModel[int]):
    root: Annotated[int, Field(ge=1, le=2147483647)]


class CoordinatePx(RootModel[float]):
    root: Annotated[float, Field(ge=-0.5, le=8192.5)]


class Image(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: CocoId
    file_name: Relpath
    width: Annotated[int, Field(ge=1, le=8192)]
    height: Annotated[int, Field(ge=1, le=8192)]


class Polygon(RootModel[list[CoordinatePx]]):
    root: Annotated[list[CoordinatePx], Field(max_length=8192, min_length=6)]


class Annotation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: CocoId
    image_id: CocoId
    category_id: Annotated[int, Field(ge=1, le=5)]
    bbox: Annotated[list[CoordinatePx], Field(max_length=4, min_length=4)]
    segmentation: Annotated[list[Polygon], Field(max_length=64, min_length=1)]
    area: Annotated[float, Field(gt=0.0, le=67108864.0)]
    iscrowd: Literal[0]


class Category1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Literal[1], Field(ge=1, le=5)]
    name: Literal["haul_truck"]
    supercategory: Annotated[str | None, Field(max_length=32, pattern="^[a-z][a-z_]{0,31}$")] = None


class Category2(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Literal[2], Field(ge=1, le=5)]
    name: Literal["shovel"]
    supercategory: Annotated[str | None, Field(max_length=32, pattern="^[a-z][a-z_]{0,31}$")] = None


class Category3(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Literal[3], Field(ge=1, le=5)]
    name: Literal["light_vehicle"]
    supercategory: Annotated[str | None, Field(max_length=32, pattern="^[a-z][a-z_]{0,31}$")] = None


class Category4(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Literal[4], Field(ge=1, le=5)]
    name: Literal["person"]
    supercategory: Annotated[str | None, Field(max_length=32, pattern="^[a-z][a-z_]{0,31}$")] = None


class Category5(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Annotated[Literal[5], Field(ge=1, le=5)]
    name: Literal["boulder"]
    supercategory: Annotated[str | None, Field(max_length=32, pattern="^[a-z][a-z_]{0,31}$")] = None


class Category(RootModel[Category1 | Category2 | Category3 | Category4 | Category5]):
    root: Category1 | Category2 | Category3 | Category4 | Category5


class CocoInstancesSubset(BaseModel):
    """
    Closed COCO instances subset (images, polygon annotations with iscrowd 0, the five perception categories) written by st55_sdg and the dataset builder (DC-009-02, spec 009-perception).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    images: Annotated[list[Image], Field(max_length=50000, min_length=1)]
    annotations: Annotated[list[Annotation], Field(max_length=1000000)]
    categories: Annotated[list[Category], Field(max_length=5, min_length=5)]
