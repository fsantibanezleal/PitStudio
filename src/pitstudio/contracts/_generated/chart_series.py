# Generated from contracts/chart-series.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr


class Serve(RootModel[str]):
    root: Annotated[str, Field(max_length=16, pattern="^(FR|NFR|SC|DC)-[0-9]{3}-[0-9]{2,3}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class NameEnEs(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    en: Annotated[str, Field(max_length=200, min_length=1)]
    es: Annotated[str, Field(max_length=200, min_length=1)]


class Producer(BaseModel):
    """
    Who made the numbers: the studio tool, the method, the version and the data label of the run. Every published value carries all four.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    tool: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9_-]{0,63}$")]
    method: Annotated[str, Field(max_length=160, min_length=1)]
    version: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]
    label: Annotated[str, Field(max_length=200, min_length=1)]


class Axis(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    label: NameEnEs
    unit: Annotated[
        str,
        Field(
            description="The unit symbol; 1 for a dimensionless quantity.",
            max_length=32,
            min_length=1,
        ),
    ]
    scale: Literal["linear", "log"] | None = None


class Category(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs


class NumberOrNull(RootModel[float | None]):
    root: float | None


class Series(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs
    unit: Annotated[
        str | None,
        Field(
            description="The unit of y when it differs from the unit of the y axis.",
            max_length=32,
            min_length=1,
        ),
    ] = None
    draw: Annotated[
        Literal["line", "step", "points"] | None,
        Field(description="line (default), step (an ECDF or a staircase) or points."),
    ] = None
    n: Annotated[
        int | None,
        Field(
            description="The number of samples the series summarises.",
            ge=1,
            le=1000000000,
        ),
    ] = None
    x: Annotated[list[float] | None, Field(max_length=20000, min_length=1)] = None
    y: Annotated[list[NumberOrNull | None], Field(max_length=20000, min_length=1)]
    lo: Annotated[
        list[NumberOrNull | None] | None,
        Field(
            description="Lower edge of the band (line) or of the error bar (bar), same length as y.",
            max_length=20000,
            min_length=1,
        ),
    ] = None
    hi: Annotated[
        list[NumberOrNull | None] | None,
        Field(
            description="Upper edge of the band (line) or of the error bar (bar), same length as y.",
            max_length=20000,
            min_length=1,
        ),
    ] = None
    band_label: Annotated[
        NameEnEs | None,
        Field(description="What lo and hi are, for example the 95 % interval and its method."),
    ] = None


class Marker(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs
    value_text: Annotated[
        str,
        Field(
            description="The number as the read-out shows it, with its unit.",
            max_length=60,
            min_length=1,
        ),
    ]
    orientation: Literal["vertical", "horizontal", "point"]
    x: float | None = None
    y: float | None = None


class Extent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    x0: float
    x1: float
    y0: float
    y1: float


class Colour(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    colormap: Annotated[
        Literal["viridis", "cividis", "inferno", "magma"],
        Field(description="FR-020-10: viridis, cividis, inferno or magma only."),
    ]
    vmin: float
    vmax: float
    unit: Annotated[str, Field(max_length=32, min_length=1)]
    label: NameEnEs


class Raster(BaseModel):
    """
    A map of nx by ny cells over a rectangular extent; values are row-major, the first row being the top (y1) row; null is no data.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    nx: Annotated[int, Field(ge=2, le=200)]
    ny: Annotated[int, Field(ge=2, le=200)]
    extent: Extent
    values: Annotated[list[NumberOrNull | None], Field(max_length=40000, min_length=4)]
    colour: Colour


class Point(RootModel[list[float]]):
    root: Annotated[list[float], Field(max_length=2, min_length=2)]


class Polyline(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs
    role: Literal["ground", "bench", "shell", "water", "other"] | None = None
    points: Annotated[list[Point], Field(max_length=5000, min_length=2)]


class Circle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs
    role: Literal["critical", "other"] | None = None
    cx: float
    cy: float
    r: Annotated[float, Field(gt=0.0)]


class Section(BaseModel):
    """
    A vertical section: polylines (ground, benches, shells) and circles (slip circles), drawn with equal axis scales.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    polylines: Annotated[list[Polyline], Field(max_length=64, min_length=1)]
    circles: Annotated[list[Circle] | None, Field(max_length=64)] = None


class Column(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    id: Slug
    label: NameEnEs
    type: Literal["number", "text"]
    unit: Annotated[str | None, Field(max_length=32, min_length=1)] = None


class RowItem(RootModel[float | constr(max_length=200) | None]):
    root: float | constr(max_length=200) | None


class Row(RootModel[list[RowItem | None]]):
    root: Annotated[list[RowItem | None], Field(max_length=24, min_length=1)]


class Table(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    columns: Annotated[list[Column], Field(max_length=24, min_length=1)]
    rows: Annotated[list[Row], Field(max_length=200, min_length=1)]


class ChartSeries(BaseModel):
    """
    One published chart of a case: the series, axes, units, colour scale and the producer label of one chart of one published run, read by the generic chart reader of the Charts tab (DC-020-05, spec 020-web-knowledge). One JSON file per chart, published as an artefact of kind chart-series, at most 524288 bytes (studio-showcase budget class).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    schema_version: Literal["1.0"]
    kind: Literal["chart-series"]
    id: Slug
    case: CaseId
    chart_type: Literal["line", "bar", "scatter", "ecdf", "raster", "section", "table"]
    status: Annotated[
        Literal["ok", "not-run"],
        Field(
            description="ok: the chart carries its data. not-run: the value could not be computed; the reason is published and nothing is drawn."
        ),
    ]
    title: NameEnEs
    caption: NameEnEs | None = None
    producer: Producer
    kpi: Annotated[
        str | None,
        Field(
            description="The id of the case KPI (DC-018-01) this chart shows; the Charts tab then lists no placeholder for it.",
            max_length=64,
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ] = None
    serves: Annotated[
        list[Serve],
        Field(
            description="The requirement or success-criterion ids of the specs this chart serves.",
            max_length=8,
            min_length=1,
        ),
    ]
    not_run_reason: NameEnEs | None = None
    x_axis: Axis | None = None
    y_axis: Axis | None = None
    categories: Annotated[
        list[Category] | None,
        Field(
            description="bar: the category of each value of a series, in order.",
            max_length=64,
            min_length=1,
        ),
    ] = None
    series: Annotated[list[Series] | None, Field(max_length=12, min_length=1)] = None
    markers: Annotated[
        list[Marker] | None,
        Field(
            description="The features of the chart (FR-020-08), each labelled with the number the read-out panel shows.",
            max_length=24,
        ),
    ] = None
    raster: Raster | None = None
    section: Section | None = None
    table: Table | None = None
