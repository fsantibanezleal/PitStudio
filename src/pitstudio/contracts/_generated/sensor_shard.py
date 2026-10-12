# Generated from contracts/sensor-shard.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


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
    root: Annotated[
        str,
        Field(
            description="Contract version (major 1).",
            max_length=8,
            pattern="^1\\.[0-9]+$",
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


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class ScanType(RootModel[Literal["rotary", "solid-state"]]):
    root: Annotated[Literal["rotary", "solid-state"], Field(description="Lidar scan pattern.")]


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


class File(BaseModel):
    """
    One output file.
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    path: Relpath
    bytes: Annotated[int, Field(description="File size (bytes), at most 10 MB.", ge=0, le=10000000)]
    sha256: Sha256
    format: Annotated[
        Literal["parquet", "zarr", "png"],
        Field(description="parquet: tables; zarr: Zarr v3 chunk or metadata file; png: LDR image."),
    ]
    content: Annotated[
        Literal["lidar-returns", "radar-detections", "image-index", "hdr-color", "distance", "semantic", "ldr-color"],
        Field(description="Column set or array held by the file."),
    ]
    rows: Annotated[int | None, Field(description="Rows of a Parquet file.", ge=0, le=10000000)] = None


class LidarReturn(BaseModel):
    """
    One row of the lidar-returns column set (Parquet).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    frame: Annotated[int, Field(ge=0, le=4294967295)]
    beam: Annotated[
        int,
        Field(
            description="Beam index within the frame (input of the beam hash).",
            ge=0,
            le=4294967295,
        ),
    ]
    echo: Annotated[int, Field(description="Return index within the beam.", ge=0, le=3)]
    x_m: Annotated[float, Field(description="Sensor-frame x (m).", ge=-1000.0, le=1000.0)]
    y_m: Annotated[float, Field(description="Sensor-frame y (m).", ge=-1000.0, le=1000.0)]
    z_m: Annotated[float, Field(description="Sensor-frame z (m).", ge=-1000.0, le=1000.0)]
    range_m: Annotated[float, Field(description="Range (m).", gt=0.0, le=1000.0)]
    intensity: Annotated[
        float,
        Field(description="Clean return intensity I0 (normalised 0-1).", ge=0.0, le=1.0),
    ]
    flags: Annotated[int, Field(description="Renderer flags; 0x40 = valid.", ge=0, le=255)]
    material_class: Annotated[
        Literal["retro", "diffuse"],
        Field(description="retro if the non-visual material is retroreflective."),
    ]
    object_id: Annotated[
        int,
        Field(
            description="Scene label of the hit object; 0 = unlabelled.",
            ge=0,
            le=4294967295,
        ),
    ]


class RadarDetection(BaseModel):
    """
    One row of the radar-detections column set (Parquet).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    frame: Annotated[int, Field(ge=0, le=4294967295)]
    x_m: Annotated[float, Field(description="Sensor-frame x (m).", ge=-1000.0, le=1000.0)]
    y_m: Annotated[float, Field(description="Sensor-frame y (m).", ge=-1000.0, le=1000.0)]
    z_m: Annotated[float, Field(description="Sensor-frame z (m).", ge=-1000.0, le=1000.0)]
    rcs_dbsm: Annotated[float, Field(description="Radar cross-section (dBsm).", ge=-100.0, le=100.0)]
    radial_velocity_m_per_s: Annotated[
        float,
        Field(
            description="Radial velocity (m/s), positive = range increasing.",
            ge=-150.0,
            le=150.0,
        ),
    ]
    object_id: Annotated[
        int | None,
        Field(
            description="Scene label of the object where available.",
            ge=0,
            le=4294967295,
        ),
    ]


class WorldFromCameraItem(RootModel[float]):
    root: Annotated[float, Field(ge=-100000000.0, le=100000000.0)]


class ImageRecord(BaseModel):
    """
    One row of the image-index column set (Parquet).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    image: Annotated[int, Field(description="Image index.", ge=0, le=4294967295)]
    sensor: SensorId
    file: Annotated[Relpath, Field(description="PNG file or Zarr array of the image.")]
    width_px: Annotated[int, Field(ge=16, le=1920)]
    height_px: Annotated[int, Field(ge=16, le=1080)]
    fx_px: Annotated[float, Field(description="K[0][0] (px).", gt=0.0, le=1000000.0)]
    fy_px: Annotated[float, Field(description="K[1][1] (px).", gt=0.0, le=1000000.0)]
    cx_px: Annotated[float, Field(description="K[0][2] (px).", ge=0.0, le=1920.0)]
    cy_px: Annotated[float, Field(description="K[1][2] (px).", ge=0.0, le=1920.0)]
    world_from_camera: Annotated[
        list[WorldFromCameraItem],
        Field(
            description="World-from-camera pose, 4 x 4 row-major (translation in m).",
            max_length=16,
            min_length=16,
        ),
    ]
    gsd_m: Annotated[
        float | None,
        Field(
            description="Ground-sampling distance p_x H_agl / f (m), S2 only.",
            gt=0.0,
            le=10.0,
        ),
    ] = None
    h_agl_m: Annotated[
        float | None,
        Field(description="Height above ground (m), S2 only.", gt=0.0, le=1000.0),
    ] = None


class LidarFrame(BaseModel):
    """
    Per-frame counts of one lidar frame (outputs, not performance data).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    sensor: SensorId
    frame: Annotated[
        int,
        Field(
            description="Recorded frame index (warm-up frames excluded).",
            ge=0,
            le=4294967295,
        ),
    ]
    beams_emitted: Annotated[int, Field(description="Beams emitted in the frame.", ge=1, le=10000000)]
    valid_points: Annotated[
        int,
        Field(
            description="Valid points (flag 0x40) of the clean frame; never 0 (point-count guard).",
            ge=1,
            le=10000000,
        ),
    ]
    file: Annotated[Relpath, Field(description="Parquet shard holding the frame's returns.")]
    rain_rate_mm_h: Annotated[
        float | None,
        Field(description="Applied rain rate (rain arm only).", ge=0.0, le=200.0),
    ] = None


class PitstudioSensorShardIndex(BaseModel):
    """
    Shard index of st53_sensors and st57_rain_lidar, with the lidar-return, radar-detection and image-index column sets as $defs (DC-013-03, spec 013-sensors).
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    field_schema: Annotated[str | None, Field(alias="$schema", max_length=200)] = None
    schema_version: SchemaVersion
    run_id: RunId
    stage: Literal["st53_sensors", "st57_rain_lidar"]
    scenario: Literal["S1", "S2", "S3", "S4a", "rain"]
    backend: Annotated[Literal["ovrtx", "isaac", "fake"], Field(description="fake: test backend only.")]
    frames: Annotated[
        list[LidarFrame],
        Field(
            description="Per-frame counts of every recorded lidar frame.",
            max_length=20000,
            min_length=0,
        ),
    ]
    files: Annotated[
        list[File],
        Field(
            description="Every output file with its size and digest.",
            max_length=10000,
            min_length=1,
        ),
    ]
