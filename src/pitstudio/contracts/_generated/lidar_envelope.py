# Generated from contracts/lidar-envelope.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class ProbeScene(BaseModel):
    """
    Probe scene: a ground plane and a 2 m cube at 20 m.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    cube_edge_m: Literal[2]
    cube_range_m: Literal[20]


class Version(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")]


class UtcTimestamp(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=32,
            pattern="^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\\.[0-9]{1,6})?Z$",
        ),
    ]


class SchemaVersion(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Contract version (major 1).",
            max_length=8,
            pattern="^1\\.[0-9]+$",
        ),
    ]


class ScanType(RootModel[Literal["rotary", "solid-state"]]):
    root: Annotated[Literal["rotary", "solid-state"], Field(description="Lidar scan pattern.")]


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Relpath(RootModel[str]):
    root: Annotated[
        str,
        Field(
            max_length=255,
            pattern="^[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?(/[A-Za-z0-9_]([A-Za-z0-9._-]{0,98}[A-Za-z0-9_])?){0,15}$",
        ),
    ]


class SensorId(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Sensor id, unique within one sensor block.",
            max_length=32,
            pattern="^[a-z][a-z0-9-]{0,31}$",
        ),
    ]


class ElevationFanDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=-45.0, le=45.0)]


class ElevationFanDeg(RootModel[list[ElevationFanDegItem]]):
    """
    Elevation fan [e_min, e_max] (deg), hard limit of +/-45 deg; e_min < e_max is a checker rule.
    """

    root: Annotated[
        list[ElevationFanDegItem],
        Field(
            description="Elevation fan [e_min, e_max] (deg), hard limit of +/-45 deg; e_min < e_max is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]


class AzimuthFanDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=-180.0, le=180.0)]


class AzimuthFanDeg(RootModel[list[AzimuthFanDegItem]]):
    """
    Azimuth fan [a_min, a_max] (deg); a_min < a_max is a checker rule.
    """

    root: Annotated[
        list[AzimuthFanDegItem],
        Field(
            description="Azimuth fan [a_min, a_max] (deg); a_min < a_max is a checker rule.",
            max_length=2,
            min_length=2,
        ),
    ]


class MountRotationDegItem(RootModel[float]):
    root: Annotated[float, Field(ge=-180.0, le=180.0)]


class MountRotationDeg(RootModel[list[MountRotationDegItem]]):
    """
    Mount rotation about x, y, z (deg).
    """

    root: Annotated[
        list[MountRotationDegItem],
        Field(
            description="Mount rotation about x, y, z (deg).",
            max_length=3,
            min_length=3,
        ),
    ]


class MountPositionMItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100.0, le=100.0)]


class MountPositionM(RootModel[list[MountPositionMItem]]):
    """
    Mount position x, y, z in the platform frame (m).
    """

    root: Annotated[
        list[MountPositionMItem],
        Field(
            description="Mount position x, y, z in the platform frame (m).",
            max_length=3,
            min_length=3,
        ),
    ]


class Lidar(BaseModel):
    """
    Generic lidar authored from datasheet-style parameters (S1 and the rain arm); no vendor profile.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["lidar"]
    id: SensorId
    scan_type: ScanType
    channels: Annotated[
        int,
        Field(description="Laser channels (beams per firing column).", ge=1, le=512),
    ]
    elevation_fan_deg: ElevationFanDeg
    azimuth_fan_deg: AzimuthFanDeg
    horizontal_resolution_deg: Annotated[
        float,
        Field(description="Azimuth step between firing columns (deg).", gt=0.0, le=10.0),
    ]
    min_range_m: Annotated[float, Field(description="Minimum range (m).", ge=0.0, le=50.0)]
    max_range_m: Annotated[
        float,
        Field(
            description="Maximum range (m); min_range_m < max_range_m is a checker rule.",
            gt=0.0,
            le=500.0,
        ),
    ]
    range_accuracy_m: Annotated[
        float,
        Field(
            description="Gaussian range accuracy (m); the renderer's rangeAccuracyM.",
            gt=0.0,
            le=1.0,
        ),
    ]
    max_returns: Annotated[
        int,
        Field(
            description="Returns per beam (multi-echo); the renderer's maxReturns.",
            ge=1,
            le=4,
        ),
    ]
    frame_rate_hz: Annotated[float | None, Field(description="Scan rate (Hz).", gt=0.0, le=100.0)] = None
    mount_position_m: MountPositionM
    mount_rotation_deg: MountRotationDeg


class PrincipalPointPxItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1920.0)]


class Camera(BaseModel):
    """
    Ideal pinhole camera (S2 drone survey, S3 crusher camera).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["camera"]
    id: SensorId
    width_px: Annotated[int, Field(description="Image width (px), at most 1920.", ge=16, le=1920)]
    height_px: Annotated[int, Field(description="Image height (px), at most 1080.", ge=16, le=1080)]
    focal_length_m: Annotated[float, Field(description="Focal length f (m).", gt=0.0, le=1.0)]
    pixel_pitch_m: Annotated[float, Field(description="Pixel pitch p_x (m).", gt=0.0, le=0.0001)]
    principal_point_px: Annotated[
        list[PrincipalPointPxItem],
        Field(description="Principal point [c_x, c_y] (px).", max_length=2, min_length=2),
    ]
    render_mode: Annotated[
        Literal["realtime-pathtracing", "pathtracing", "minimal"],
        Field(description="Camera render mode."),
    ]
    outputs: Annotated[
        list[Literal["LdrColor", "HdrColor", "DistanceToCameraSD", "DistanceToImagePlaneSD", "SemanticSegmentation"]],
        Field(description="Render products of the camera.", max_length=5, min_length=1),
    ]
    mount_position_m: MountPositionM
    mount_rotation_deg: MountRotationDeg


class Radar(BaseModel):
    """
    77 GHz-class proximity radar (S4a).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["radar"]
    id: SensorId
    wavelength_m: Annotated[
        float,
        Field(
            description="Carrier wavelength (m): 3.70-3.95 mm (76-81 GHz).",
            ge=0.0037,
            le=0.00395,
        ),
    ]
    motion_bvh: Annotated[Literal[True], Field(description="Motion BVH enabled (required for Doppler).")]
    range_resolution_m: Annotated[float, Field(description="Range resolution (m).", gt=0.0, le=10.0)]
    velocity_resolution_m_per_s: Annotated[
        float,
        Field(
            description="Radial-velocity resolution (m/s); the renderer's velResMps.",
            gt=0.0,
            le=10.0,
        ),
    ]
    azimuth_resolution_deg: Annotated[float, Field(description="Boresight azimuth resolution (deg).", gt=0.0, le=30.0)]
    elevation_resolution_deg: Annotated[
        float,
        Field(description="Boresight elevation resolution (deg).", gt=0.0, le=30.0),
    ]
    max_range_m: Annotated[float, Field(description="Maximum range (m).", gt=0.0, le=500.0)]
    frame_rate_hz: Annotated[float | None, Field(description="Frame rate (Hz).", gt=0.0, le=100.0)] = None
    mount_position_m: MountPositionM
    mount_rotation_deg: MountRotationDeg


class TransmittanceGridItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=1.0)]


class Dust(BaseModel):
    """
    Dust post-model settings read by s05_synthesize (S1).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    transmittance_grid: Annotated[
        list[TransmittanceGridItem],
        Field(
            description="One-way transmittance levels T1 of the uniform-layer sweep (pre-registered grid 1.0 ... 0.02).",
            max_length=16,
            min_length=1,
        ),
    ]
    beta_spacing_m: Annotated[
        float,
        Field(
            description="Sample spacing of the extinction profile along a beam (m), at most 0.5.",
            gt=0.0,
            le=0.5,
        ),
    ]
    dust_return_intensity: Annotated[
        float,
        Field(
            description="Display intensity of injected dust returns (normalised 0-1; no physical claim).",
            ge=0.0,
            le=1.0,
        ),
    ]
    extinction_fields: Annotated[
        list[Relpath] | None,
        Field(
            description="C3 extinction fields (declared stage inputs) for the field-driven runs.",
            max_length=16,
            min_length=0,
        ),
    ] = None


class SpeedsKmHItem(RootModel[float]):
    root: Annotated[float, Field(gt=0.0, le=100.0)]


class Metrics(BaseModel):
    """
    S1 metric settings (FR-013-36).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    k_min: Annotated[
        int,
        Field(
            description="Target points needed for a detection (default 3).",
            ge=1,
            le=1000,
        ),
    ]
    range_bin_m: Annotated[float, Field(description="Range-bin width (m), default 5.", gt=0.0, le=50.0)]
    speeds_km_h: Annotated[
        list[SpeedsKmHItem],
        Field(
            description="Truck speeds for the TTC margin (km/h), default 30, 40, 50.",
            max_length=8,
            min_length=1,
        ),
    ]
    targets: Annotated[
        list[Slug],
        Field(
            description="Target ids as labelled in the scene.",
            max_length=16,
            min_length=1,
        ),
    ]


class Exposure(BaseModel):
    """
    S2 exposure and noise post-model settings (FR-013-18).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    exposure_time_s: Annotated[float, Field(description="Exposure time t_e (s).", gt=0.0, le=1.0)]
    f_number: Annotated[float, Field(description="Aperture f-number N (-).", ge=1.0, le=32.0)]
    kappa_e_m2_sr_per_w_s: Annotated[
        float,
        Field(
            description="Lumped signal constant kappa (electrons per W sr^-1 m^-2 s).",
            gt=0.0,
            le=1000000000000.0,
        ),
    ]
    gain_dn_per_e: Annotated[
        float,
        Field(description="Conversion gain G (DN per electron).", gt=0.0, le=1000.0),
    ]
    read_noise_e: Annotated[
        float,
        Field(description="Read noise sigma_read (electrons).", ge=0.0, le=1000.0),
    ]
    dn_max: Annotated[int, Field(description="Saturation level DN_max.", ge=1, le=65535)]
    vignetting: Annotated[bool, Field(description="Apply natural cos^4 vignetting.")]


class AirlightRgbItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=1000000.0)]


class Haze(BaseModel):
    """
    S3 haze and box post-model settings (FR-013-16, FR-013-17).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    airlight_rgb: Annotated[
        list[AirlightRgbItem],
        Field(description="Airlight A, linear RGB.", max_length=3, min_length=3),
    ]
    min_box_area_px: Annotated[
        int,
        Field(
            description="Minimum semantic-component area for a box (px), default 16.",
            ge=1,
            le=2073600,
        ),
    ]
    extinction_field: Annotated[
        Relpath | None,
        Field(description="C3 extinction field (a declared stage input)."),
    ] = None


class Versions(BaseModel):
    """
    Versions read from studio/rtx/uv.lock.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    ovrtx: Version
    ovstage: Version


class Configuration(BaseModel):
    """
    One probed lidar configuration.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    scan_type: ScanType
    elevation_fan_deg: ElevationFanDeg
    azimuth_fan_deg: AzimuthFanDeg
    mount_rotation_deg: MountRotationDeg
    status: Annotated[
        Literal["pass", "fail"],
        Field(description="pass: more than 0 valid points on the probe scene."),
    ]
    valid_points: Annotated[
        int,
        Field(
            description="Valid points of the probe frame (a count, not performance data).",
            ge=0,
            le=10000000,
        ),
    ]


class PitstudioLidarEnvelope(BaseModel):
    """
    studio/rtx/lidar-envelope.json, written by the ovrtx probe and read by the st53_sensors guard (DC-013-02, spec 013-sensors).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    generated: Annotated[UtcTimestamp, Field(description="When the probe wrote the file (UTC).")]
    versions: Annotated[Versions, Field(description="Versions read from studio/rtx/uv.lock.")]
    probe_scene: Annotated[
        ProbeScene,
        Field(description="Probe scene: a ground plane and a 2 m cube at 20 m."),
    ]
    configurations: Annotated[
        list[Configuration],
        Field(
            description="Every lidar configuration referenced by the committed recipes.",
            max_length=256,
            min_length=1,
        ),
    ]
