"""GPU backends: the NVML backend (imported lazily) and the fake backend driven by a device file (FR-002-22, 55..57)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from pitstudio.runner.recipe import Usage, load_device


class BackendInitError(Exception):
    """No driver, no device, or an NVML error (or a scripted `init_error`)."""


class FakeBackend:
    def __init__(self, doc: dict, clock: Any = time) -> None:
        if doc["init_error"]:
            raise BackendInitError("the fake device is scripted to fail initialisation")
        self.name, self.driver, self.vram_total_bytes = doc["name"], doc["driver"], doc["vram_total_bytes"]
        self.series, self.unsupported, self.clock = doc["series"], set(doc.get("unsupported", [])), clock
        self.t0 = clock.monotonic()

    def read(self, field: str) -> float:
        key = "energy_mj_per_s" if field == "energy_mj" else field
        if key in self.unsupported or key not in self.series:
            raise RuntimeError(f"{field} is not supported by this device")
        now, steps = self.clock.monotonic() - self.t0, self.series[key]
        steps = steps if isinstance(steps, list) else [[0, steps]]
        if field != "energy_mj":
            return next((v for t, v in reversed(steps) if t <= now), steps[0][1])
        ends = [s[0] for s in steps[1:]] + [float("inf")]  # the integral of the scripted rate (mJ/s) from 0 to now
        return sum(max(0.0, min(now, end) - t) * v for (t, v), end in zip(steps, ends, strict=True))


class NvmlBackend:
    """Real GPU 0 through `nvidia-ml-py` (module `pynvml`)."""

    def __init__(self, index: int = 0) -> None:
        try:
            import pynvml as nv

            nv.nvmlInit()
            self.nv, self.h = nv, nv.nvmlDeviceGetHandleByIndex(index)
            self.name, self.driver = nv.nvmlDeviceGetName(self.h), nv.nvmlSystemGetDriverVersion()
            self.vram_total_bytes = int(nv.nvmlDeviceGetMemoryInfo(self.h).total)
        except Exception as e:
            raise BackendInitError(f"NVML: {type(e).__name__}") from e
        self.name, self.driver = (x.decode() if isinstance(x, bytes) else x for x in (self.name, self.driver))

    def read(self, field: str) -> float:
        nv, h = self.nv, self.h
        return {
            "free_bytes": lambda: nv.nvmlDeviceGetMemoryInfo(h).free,
            "temp_c": lambda: nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU),
            "power_w": lambda: nv.nvmlDeviceGetPowerUsage(h) / 1000,
            "power_limit_w": lambda: nv.nvmlDeviceGetEnforcedPowerLimit(h) / 1000,
            "util_pct": lambda: nv.nvmlDeviceGetUtilizationRates(h).gpu,
            "sm_clock_mhz": lambda: nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM),
            "clocks_event_mask": lambda: nv.nvmlDeviceGetCurrentClocksEventReasons(h),
            "energy_mj": lambda: nv.nvmlDeviceGetTotalEnergyConsumption(h),
            "nvenc_util_pct": lambda: nv.nvmlDeviceGetEncoderUtilization(h)[0],
            "pcie_replays": lambda: nv.nvmlDeviceGetPcieReplayCounter(h),
        }[field]()


def backend_spec(flag: str | None) -> str:
    """The backend named by `--gpu-backend` (wins) or PITSTUDIO_GPU_BACKEND; `nvml` when neither is given."""
    return flag or os.environ.get("PITSTUDIO_GPU_BACKEND") or "nvml"


def load_backend(spec: str, clock: Any = time):
    if spec == "nvml":
        return NvmlBackend()
    kind, _, path = spec.partition(":")
    if kind != "fake" or not path:
        raise Usage(f"--gpu-backend must be nvml or fake:<device file>, got {spec[:60]!r}")
    return FakeBackend(load_device(Path(path)), clock)
