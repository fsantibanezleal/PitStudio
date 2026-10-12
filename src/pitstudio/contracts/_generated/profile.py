# Generated from contracts/profile.schema.json by tools/gen_types.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, constr
from typing_extensions import TypeAliasType

QuotasAdditionalProperty = TypeAliasType("QuotasAdditionalProperty", Annotated[float, Field(gt=0.0, le=10000.0)])


class Slug(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[a-z0-9][a-z0-9-]{0,63}$")]


class Driver(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[0-9]+(\\.[0-9]+)+$")]


class BinaryId(RootModel[str]):
    root: Annotated[str, Field(max_length=32, pattern="^[a-z][a-z0-9-]{1,31}$")]


class EnvVar(RootModel[str]):
    root: Annotated[str, Field(max_length=64, pattern="^[A-Z][A-Z0-9_]{2,63}$")]


class StageId(
    RootModel[
        Literal[
            "s00_download",
            "s05_synthesize",
            "s10_preprocess",
            "s20_feature_extraction",
            "s30_train",
            "s40_infer",
            "s50_evaluate",
            "s60_export",
            "s62_accel",
            "s64_bench",
            "st10_terrain",
            "st20_pit_design",
            "st30_assets",
            "st40_compose",
            "st45_validate",
            "st45b_kit_validate",
            "st50_physics",
            "st52_rtx_render",
            "st53_sensors",
            "st54_vehicles",
            "st55_sdg",
            "st56_encode",
            "st57_rain_lidar",
            "st58_kit_capture",
            "st58b_capture_splat",
            "st59_reason_bench",
            "st59a_vqa",
            "st59b_plausibility",
            "st59c_captions",
            "st60_il_train",
            "st61_il_mpm_eval",
        ]
    ]
):
    root: Literal[
        "s00_download",
        "s05_synthesize",
        "s10_preprocess",
        "s20_feature_extraction",
        "s30_train",
        "s40_infer",
        "s50_evaluate",
        "s60_export",
        "s62_accel",
        "s64_bench",
        "st10_terrain",
        "st20_pit_design",
        "st30_assets",
        "st40_compose",
        "st45_validate",
        "st45b_kit_validate",
        "st50_physics",
        "st52_rtx_render",
        "st53_sensors",
        "st54_vehicles",
        "st55_sdg",
        "st56_encode",
        "st57_rain_lidar",
        "st58_kit_capture",
        "st58b_capture_splat",
        "st59_reason_bench",
        "st59a_vqa",
        "st59b_plausibility",
        "st59c_captions",
        "st60_il_train",
        "st61_il_mpm_eval",
    ]


class Environment(
    RootModel[
        Literal[
            "studio",
            "isaac",
            "rtx",
            "isaaclab",
            "kit",
            "reason",
            "pipeline",
            "accel",
            "external",
        ]
    ]
):
    root: Literal[
        "studio",
        "isaac",
        "rtx",
        "isaaclab",
        "kit",
        "reason",
        "pipeline",
        "accel",
        "external",
    ]


class StoreDefault(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="short machine-neutral absolute store root, used only when PITSTUDIO_STORE is unset: a drive-root folder on Windows, a /srv, /data or /scratch folder on Linux (bound to `os` at the root)",
            max_length=41,
            pattern="^([A-Z]:/[a-z0-9_-]{1,16}|/(srv|data|scratch)/[a-z0-9_-]{1,32})$",
        ),
    ]


class Gpu(BaseModel):
    """
    nominal device facts for planning; the live (or fake) backend value governs the guards
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    index: Annotated[int, Field(ge=0, le=15)]
    vram_bytes: Annotated[int, Field(ge=1, le=9007199254740991)]
    power_class: Literal["laptop-power-limited", "desktop", "server"]


class Guards(BaseModel):
    """
    pre-flight guard settings; margins in GiB (2^30 B), floors of FR-002-19 / FR-002-20
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    vram_margin_gib: Annotated[float, Field(ge=1.5, le=256.0)]
    disk_margin_gib: Annotated[float, Field(ge=20.0, le=10000.0)]
    max_start_temp_c: Annotated[float, Field(ge=0.0, le=80.0)]
    cooldown_wait_s: Annotated[int, Field(ge=0, le=3600)]
    lock_wait_s: Annotated[int, Field(ge=0, le=86400)]


class SeriesField(
    RootModel[
        Literal[
            "free_bytes",
            "temp_c",
            "power_w",
            "power_limit_w",
            "util_pct",
            "sm_clock_mhz",
            "clocks_event_mask",
            "energy_mj_per_s",
            "nvenc_util_pct",
            "pcie_replays",
        ]
    ]
):
    root: Literal[
        "free_bytes",
        "temp_c",
        "power_w",
        "power_limit_w",
        "util_pct",
        "sm_clock_mhz",
        "clocks_event_mask",
        "energy_mj_per_s",
        "nvenc_util_pct",
        "pcie_replays",
    ]


class StepItem(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=9007199254740991.0)]


class Step(RootModel[list[StepItem]]):
    """
    [t_s, value]: seconds since the backend started and the value from then on; per-field value ranges and ascending t_s are checked by the fake backend's loader (FR-002-57)
    """

    root: Annotated[
        list[StepItem],
        Field(
            description="[t_s, value]: seconds since the backend started and the value from then on; per-field value ranges and ascending t_s are checked by the fake backend's loader (FR-002-57)",
            max_length=2,
            min_length=2,
        ),
    ]


class Steps(RootModel[list[Step]]):
    root: Annotated[list[Step], Field(max_length=10000, min_length=1)]


class FreeBytes(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=9007199254740991)]


class TempC(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=200.0)]


class PowerW(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10000.0)]


class PowerLimitW(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10000.0)]


class UtilPct(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class SmClockMhz(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=20000.0)]


class ClocksEventMask(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=4294967295)]


class EnergyMjPerS(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=10000000.0)]


class NvencUtilPct(RootModel[float]):
    root: Annotated[float, Field(ge=0.0, le=100.0)]


class PcieReplays(RootModel[int]):
    root: Annotated[int, Field(ge=0, le=4294967295)]


class FakeSeries(BaseModel):
    """
    scripted backend answers per field: a constant, or [t_s, value] steps
    """

    model_config = ConfigDict(
        extra="forbid",
    )
    free_bytes: FreeBytes | Steps | None = None
    temp_c: TempC | Steps | None = None
    power_w: PowerW | Steps | None = None
    power_limit_w: PowerLimitW | Steps | None = None
    util_pct: UtilPct | Steps | None = None
    sm_clock_mhz: SmClockMhz | Steps | None = None
    clocks_event_mask: ClocksEventMask | Steps | None = None
    energy_mj_per_s: EnergyMjPerS | Steps | None = None
    nvenc_util_pct: NvencUtilPct | Steps | None = None
    pcie_replays: PcieReplays | Steps | None = None


class FakeDevice(BaseModel):
    """
    device file of the fake GPU backend (PITSTUDIO_GPU_BACKEND=fake:<file>, FR-002-55); all values finite
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
    name: Annotated[str, Field(max_length=128, pattern="^[A-Za-z0-9][A-Za-z0-9 ._()+-]{0,127}$")]
    driver: Driver
    vram_total_bytes: Annotated[int, Field(ge=1, le=9007199254740991)]
    init_error: bool
    unsupported: Annotated[list[SeriesField] | None, Field(max_length=10)] = None
    series: FakeSeries


class PitstudioMachineProfile(BaseModel):
    """
    Machine profile studio/recipes/_profiles/<id>.yaml read by the runner, with $defs/fake_device for the fake GPU backend's device files (DC-002-01, spec 002-runner).
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
    id: Slug
    os: Literal["windows", "linux"]
    gpus: Annotated[list[Gpu], Field(max_length=16)]
    store_default: StoreDefault
    cpu_slots: Annotated[int, Field(ge=1, le=256)]
    envs_enabled: Annotated[list[Environment], Field(max_length=9, min_length=1)]
    process_control: Literal["job-object", "process-group"]
    guards: Guards
    telemetry_hz: Annotated[float, Field(ge=1.0, le=4.0)]
    keep_awake: bool
    quotas: Annotated[
        dict[
            Literal[
                "s00_download",
                "s05_synthesize",
                "s10_preprocess",
                "s20_feature_extraction",
                "s30_train",
                "s40_infer",
                "s50_evaluate",
                "s60_export",
                "s62_accel",
                "s64_bench",
                "st10_terrain",
                "st20_pit_design",
                "st30_assets",
                "st40_compose",
                "st45_validate",
                "st45b_kit_validate",
                "st50_physics",
                "st52_rtx_render",
                "st53_sensors",
                "st54_vehicles",
                "st55_sdg",
                "st56_encode",
                "st57_rain_lidar",
                "st58_kit_capture",
                "st58b_capture_splat",
                "st59_reason_bench",
                "st59a_vqa",
                "st59b_plausibility",
                "st59c_captions",
                "st60_il_train",
                "st61_il_mpm_eval",
            ],
            QuotasAdditionalProperty,
        ]
        | None,
        Field(
            description="store quota per stage id, GiB (2^30 B); absent = no quota",
            max_length=64,
        ),
    ] = None
    binaries: Annotated[
        dict[constr(pattern=r"^[a-z][a-z0-9-]{1,31}$", max_length=32), EnvVar] | None,
        Field(
            description="pinned executable id -> name of the environment variable holding its path (never the path)",
            max_length=32,
        ),
    ] = None
