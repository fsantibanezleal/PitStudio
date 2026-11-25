# Generated from contracts/surrogate-io.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, conint, constr
from typing_extensions import TypeAliasType

ConstantsAdditionalProperty = TypeAliasType(
    "ConstantsAdditionalProperty",
    Annotated[float, Field(ge=-1000000000000.0, le=1000000000000.0)],
)


class CaseId(RootModel[Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]]):
    root: Literal["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]


class Dim(RootModel[conint(ge=1, le=1048576) | constr(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,31}$", max_length=32)]):
    root: Annotated[
        conint(ge=1, le=1048576) | constr(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,31}$", max_length=32),
        Field(description="a fixed dimension (integer) or a symbolic one declared in `symbolic_dims`"),
    ]


class Dtype(RootModel[Literal["float32", "float16", "bfloat16", "int64", "int32", "int8", "uint8", "bool"]]):
    root: Annotated[
        Literal["float32", "float16", "bfloat16", "int64", "int32", "int8", "uint8", "bool"],
        Field(description="ONNX Runtime tensor element type"),
    ]


class MeanItem(RootModel[float]):
    root: Annotated[float, Field(ge=-1000000000000.0, le=1000000000000.0)]


class StdItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000000000.0)]


class Normalisation(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rule: Annotated[
        Literal["none", "standardise", "log-standardise", "patch-relief", "context-mean-abs"],
        Field(
            description="map from physical values to tensor values: standardise (x - mean) / std; log-standardise (ln x - mean) / std; patch-relief (x - patch mean) / patch relief; context-mean-abs x / mean |x| of the input context (outputs are scaled back by the same factor)"
        ),
    ]
    applied_in_graph: Annotated[
        bool,
        Field(description="true: the graph applies the map itself and the tensor carries physical values"),
    ]
    mean: Annotated[
        list[MeanItem] | None,
        Field(
            description="one value per channel, or one broadcast value",
            max_length=64,
            min_length=1,
        ),
    ] = None
    std: Annotated[
        list[StdItem] | None,
        Field(
            description="one value per channel, or one broadcast value",
            max_length=64,
            min_length=1,
        ),
    ] = None


class ParamKey(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z][a-z0-9_]{0,63}$")]


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


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class SymbolicDim(BaseModel):
    """
    accepted range of a symbolic dimension
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    min: Annotated[int, Field(ge=1, le=1048576)]
    max: Annotated[int, Field(ge=1, le=1048576)]


class Quantile(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, lt=1.0)]


class TensorName(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="graph input or output name",
            max_length=64,
            min_length=1,
            pattern="^[A-Za-z_][A-Za-z0-9_]{0,63}$",
        ),
    ]


class TensorUnit(
    RootModel[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
            "per-channel",
        ]
    ]
):
    root: Annotated[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
            "per-channel",
        ],
        Field(
            description='physical unit ("1" = dimensionless, counts, indices and categories); "per-channel" when the channels carry their own units'
        ),
    ]


class Unit(
    RootModel[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
        ]
    ]
):
    root: Annotated[
        Literal[
            "1",
            "m",
            "mm",
            "um",
            "m^2",
            "m^3",
            "m^2/s",
            "s",
            "h",
            "deg",
            "rad",
            "m/s",
            "m/s^2",
            "mm/h",
            "h/mm",
            "Pa",
            "Pa.s",
            "kg",
            "kg/m^3",
            "kg/m^2/s",
            "ug/m^3",
            "kW",
            "kWh/t",
            "t/h",
            "USD/kg",
            "USD/kWh",
            "USD/t",
        ],
        Field(description='physical unit ("1" = dimensionless, counts, indices and categories)'),
    ]


class Channel(BaseModel):
    """
    one channel; the array order is the channel order
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: ParamKey
    unit: Unit
    normalisation: Normalisation | None = None
    description: Annotated[str | None, Field(max_length=200)] = None


class EnvelopeRange(BaseModel):
    """
    closed training range of one parameter; outside it a result is labelled extrapolation
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    min: Annotated[float, Field(ge=-1000000000000.0, le=1000000000000.0)]
    max: Annotated[float, Field(ge=-1000000000000.0, le=1000000000000.0)]
    unit: Unit
    description: Annotated[str | None, Field(max_length=200)] = None


class OnnxFile(BaseModel):
    """
    the exported ONNX file this description belongs to
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    sha256: Sha256
    bytes: Annotated[int, Field(ge=1, le=2147483647)]


class Tensor(BaseModel):
    """
    one graph input or output
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    name: TensorName
    dtype: Dtype
    shape: Annotated[list[Dim], Field(max_length=8, min_length=1)]
    unit: TensorUnit
    channel_axis: Annotated[int | None, Field(ge=0, le=7)] = None
    channels: Annotated[list[Channel] | None, Field(max_length=64, min_length=1)] = None
    normalisation: Normalisation | None = None
    categories: Annotated[
        list[Slug] | None,
        Field(
            description="allowed category names in index order (e.g. particle types)",
            max_length=64,
            min_length=1,
        ),
    ] = None
    quantile_axis: Annotated[int | None, Field(ge=0, le=7)] = None
    quantiles: Annotated[
        list[Quantile] | None,
        Field(description="quantile levels in output order", max_length=99, min_length=1),
    ] = None
    description: Annotated[str | None, Field(max_length=200)] = None


class SurrogateOnnxInputOutputDescription(BaseModel):
    """
    Input/output description of an exported surrogate, forecaster or meta-model graph written by s60_export (DC-011-02, spec 011-surrogates; also DC-010-05 and the spec 017 meta-model).
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
    model_id: Slug
    engine: Annotated[
        Literal["gns", "fno", "forecasters", "meta-model"],
        Field(description="consuming web engine"),
    ]
    cases: Annotated[list[CaseId] | None, Field(max_length=12, min_length=1)] = None
    description: Annotated[str | None, Field(max_length=500)] = None
    onnx: OnnxFile
    opset: Annotated[Literal[17, 18, 19], Field(description="default-domain opset")]
    ir_version: Literal[10]
    ml_opset: Annotated[
        int | None,
        Field(description="ai.onnx.ml opset (tree converters only)", ge=1, le=5),
    ] = None
    precision: Annotated[
        Literal["fp32", "fp16", "int8", "fp8"],
        Field(description="precision of the graph's arithmetic"),
    ]
    delivery: Annotated[
        Literal["live", "precompute", "bench-only"],
        Field(description="live in the browser, precomputed outputs, or bench only"),
    ]
    delivery_reason: Annotated[str | None, Field(max_length=500, min_length=1)] = None
    aggregation: Annotated[
        Literal["padded-gather", "scatter-add"] | None,
        Field(description="GNS message aggregation layout"),
    ] = None
    symbolic_dims: Annotated[
        dict[constr(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,31}$", max_length=32), SymbolicDim] | None,
        Field(max_length=8),
    ] = None
    constants: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), ConstantsAdditionalProperty] | None,
        Field(description="model constants (unit-suffixed keys)", max_length=32),
    ] = None
    inputs: Annotated[list[Tensor], Field(max_length=16, min_length=1)]
    outputs: Annotated[list[Tensor], Field(max_length=16, min_length=1)]
    training_envelope: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64), EnvelopeRange],
        Field(max_length=64, min_length=1),
    ]
