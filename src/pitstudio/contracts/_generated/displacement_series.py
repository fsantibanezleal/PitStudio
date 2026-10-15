# Generated from contracts/displacement-series.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ArtefactId(RootModel[str]):
    root: Annotated[str, Field(max_length=96, pattern="^[a-z0-9][a-z0-9_-]{0,95}$")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Sha256(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[0-9a-f]{64}$")]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class HttpsUrl(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=2048,
            pattern="^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&'()*+,;=:@/-]*)?(\\?[A-Za-z0-9._~%!$&'()*+,;=:@/?-]*)?$",
        ),
    ]


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


class TimeH(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class DisplacementMm(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class Snr(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1000000000.0)]


class PixelId(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=999999)]


class PointMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-10000000.0, le=10000000.0)]


class PointM(RootModel[list[PointMItem]]):
    root: Annotated[list[PointMItem], Field(max_length=3, min_length=3)]


class Stratum(
    RootModel[
        Literal[
            "snr_obs",
            "half_snr_obs",
            "double_snr_obs",
            "snr_obs_atmospheric",
            "nominal_10",
            "nominal_30",
            "nominal_100",
        ]
    ]
):
    root: Literal[
        "snr_obs", "half_snr_obs", "double_snr_obs", "snr_obs_atmospheric", "nominal_10", "nominal_30", "nominal_100"
    ]


class SignConvention(RootModel[Literal["positive = away from the radar"]]):
    root: Literal["positive = away from the radar"]


class PixelStatus(RootModel[Literal["ok", "ambiguous (phase wrapping)"]]):
    root: Literal["ok", "ambiguous (phase wrapping)"]


class Sampling(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    n_samples: Annotated[int, Field(ge=2, le=1000000)]
    interval_h: Annotated[float, Field(gt=0.0, le=10000.0)]
    regular: bool


class Ar1(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    rho: Annotated[float, Field(gt=-1.0, lt=1.0)]
    marginal_sd_mm: Annotated[float, Field(ge=0.0, le=1000000.0)]


class VoightParameters(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    alpha: Annotated[float, Field(gt=1.0, le=10.0)]
    a_coefficient: Annotated[float, Field(gt=0.0, le=1000000000.0)]
    terminal_duration_h: Annotated[float, Field(gt=0.0, le=100000.0)]
    onset_velocity_mm_per_day: Annotated[float, Field(gt=0.0, le=10000.0)]
    steady_phase_fraction: Annotated[float, Field(ge=0.0, lt=1.0)]
    regressive: bool
    regressive_velocity_reduction: Annotated[float | None, Field(gt=0.0, lt=1.0)] = None
    regressive_duration_fraction: Annotated[float | None, Field(gt=0.0, lt=1.0)] = None
    psi_deg: Annotated[float, Field(ge=0.0, le=89.0)]
    snr_target: Snr
    sigma_d_mm: Annotated[float, Field(ge=0.0, le=1000000.0)]
    ar1: Ar1 | None = None


class Radar(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    position_m: PointM
    wavelength_mm: Annotated[float, Field(gt=1.0, lt=1000.0)]
    scan_interval_min: Annotated[float, Field(gt=0.0, le=10080.0)]


class SyntheticEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["synthetic-event"]
    synthetic: Literal[True]
    event_id: ArtefactId
    seed: Seed
    split: Literal["train", "validation", "test"]
    stratum: Stratum
    snr_note: Literal["observed SNR not available — nominal SNR"] | None = None
    parameters: VoightParameters
    t_0_h: TimeH
    t_f_h: TimeH
    t_f_source: Literal["synthetic (exact)"]
    realised_snr: Snr
    sampling: Sampling
    attribution: Annotated[str | None, Field(max_length=500)] = None
    t_h: Annotated[list[TimeH], Field(max_length=1000000, min_length=64)]
    los_displacement_mm: Annotated[list[DisplacementMm], Field(max_length=1000000, min_length=64)]


class TFDocument(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["dataset-description", "dataset-file", "publication"]
    citation: Annotated[str, Field(max_length=500, min_length=1)]
    url: HttpsUrl | None = None


class SourceUnits(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    displacement: Literal["mm", "cm", "m"]
    time: Literal["s", "min", "h", "d"]


class Licence(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    spdx: Literal["CC-BY-4.0"]
    licence_class: Literal["attribution"]


class RealEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["real-event"]
    synthetic: Literal[False]
    event_id: ArtefactId
    source_id: Slug
    archive_bytes: Literal[8943265]
    archive_md5: Literal["3adeb6c853d2e87249b7d3549a2a00ca"]
    archive_sha256: Sha256
    archive_member: Relpath
    extraction: Literal["series-as-delivered", "map-median-top-5pct"]
    source_units: SourceUnits
    t_ref_utc: UtcTimestamp | None = None
    t_0_h: TimeH
    t_f_h: TimeH
    t_f_source: TFDocument
    snr_obs: Snr
    sampling: Sampling
    attribution: Annotated[str, Field(max_length=2000, min_length=1)]
    licence: Licence
    use: Literal["descriptive-evaluation-only"]
    t_h: Annotated[list[TimeH], Field(max_length=1000000, min_length=2)]
    los_displacement_mm: Annotated[list[DisplacementMm], Field(max_length=1000000, min_length=2)]


class RadarPixel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["radar-pixel"]
    synthetic: Literal[True]
    event_id: ArtefactId
    stratum: Stratum | None = None
    pixel_id: PixelId
    pixel_position_m: PointM
    radar: Radar
    psi_deg: Annotated[float, Field(ge=0.0, le=180.0)]
    sign_convention: SignConvention
    run_seed: Seed
    status: PixelStatus
    ambiguous_from_scan: Annotated[int | None, Field(ge=0, le=999999)] = None
    t_h: Annotated[list[TimeH], Field(max_length=1000000, min_length=2)]
    los_displacement_mm: Annotated[list[DisplacementMm], Field(max_length=1000000, min_length=2)]
    measured_los_displacement_mm: Annotated[list[DisplacementMm], Field(max_length=1000000, min_length=2)]
    wrap_flags: Annotated[list[bool], Field(max_length=1000000, min_length=2)]


class MapPixel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    pixel_id: PixelId
    position_m: PointM
    los_displacement_mm: DisplacementMm
    status: PixelStatus


class RadarMap(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    kind: Literal["radar-map"]
    synthetic: Literal[True]
    event_id: ArtefactId
    radar: Radar
    sign_convention: SignConvention
    scan_index: Annotated[int, Field(ge=0, le=999999)]
    t_h: TimeH
    ambiguous_pixels: Annotated[int, Field(ge=0, le=1000000)]
    pixels: Annotated[list[MapPixel], Field(max_length=1000000, min_length=1)]


class DisplacementSeries(RootModel[SyntheticEvent | RealEvent | RadarPixel | RadarMap]):
    root: Annotated[
        SyntheticEvent | RealEvent | RadarPixel | RadarMap,
        Field(
            description="Slope displacement series of one seeded synthetic Voight event, the real de Wit event, one S4b radar pixel or one S4b line-of-sight map, written by s05_synthesize, s10_preprocess and the radar-series builder (DC-010-02, spec 010-slope).",
            title="Displacement series",
        ),
    ]
