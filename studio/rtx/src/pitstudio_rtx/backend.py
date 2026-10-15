# SPDX-License-Identifier: Apache-2.0
"""The sensor-backend protocol, the runtime-isolation rule and the backend factory (FR-013-01, FR-013-03).

Standard library only. A backend renders one session of sensors over a pose trace; the lane (`lane.py`) owns every
guard, so a backend stays a thin adapter. The renderer runtimes are imported lazily by the backend modules and
never by this one.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: Module-name prefixes of the Kit-based runtimes that must not share a process with the Kit-less `ovrtx` renderer.
KIT_PREFIXES = ("omni.kit", "isaacsim", "carb")
BACKEND_NAMES = ("ovrtx", "isaac", "fake")


class RuntimeIsolationError(RuntimeError):
    """The requested renderer cannot start because a conflicting runtime is already loaded in this process."""


@dataclass(frozen=True)
class BackendInfo:
    """What a backend is: its name, the versions of its runtime and its capabilities (`warmup_frames`, ...)."""

    name: str
    versions: dict[str, str] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SensorBackend(Protocol):
    """Exactly four operations. `open` returns an opaque session, `step` one dict of outputs per sensor id."""

    def describe(self) -> BackendInfo: ...

    def open(self, stage: str | None, sensors: list[dict[str, Any]]) -> Any: ...

    def step(self, session: Any, pose: Mapping[str, Any]) -> dict[str, dict[str, Any]]: ...

    def close(self, session: Any) -> None: ...


def _matches(names: Iterable[str], prefixes: Iterable[str]) -> list[str]:
    return sorted(n for n in names if any(n == p or n.startswith(p + ".") for p in prefixes))


def check_runtime_isolation(requested: str, modules: Mapping[str, Any] | None = None) -> None:
    """Raise `RuntimeIsolationError` when `requested` conflicts with a module in `modules` (default `sys.modules`).

    `ovrtx` is refused when `omni.kit*`, `isaacsim*` or `carb*` is loaded; `isaac` is refused when `ovrtx*` is loaded;
    `fake` is never refused. The check reads module names only: it never imports or touches a runtime.
    """
    table = sys.modules if modules is None else modules
    if requested == "ovrtx":
        found = _matches(table, KIT_PREFIXES)
        if found:
            raise RuntimeIsolationError(
                f"the ovrtx backend cannot start: Kit-based modules are loaded in this process ({', '.join(found)}); "
                "run it in its own interpreter"
            )
    elif requested == "isaac":
        found = _matches(table, ("ovrtx",))
        if found:
            raise RuntimeIsolationError(
                f"the isaac backend cannot start: the ovrtx runtime is loaded in this process ({', '.join(found)}); "
                "run it in its own interpreter"
            )


def create_backend(name: str, **kwargs: Any) -> SensorBackend:
    """Build the backend `name` (`ovrtx`, `isaac` or `fake`); the isolation rule runs before any runtime is imported."""
    if name not in BACKEND_NAMES:
        raise ValueError(f"unknown sensor backend {name!r}; expected one of {', '.join(BACKEND_NAMES)}")
    check_runtime_isolation(name)
    if name == "fake":
        from pitstudio_rtx.backends.fake import FakeBackend

        return FakeBackend(**kwargs)
    if name == "ovrtx":
        return importlib.import_module("pitstudio_rtx.backends.ovrtx_backend").OvrtxBackend(**kwargs)
    return importlib.import_module("pitstudio_isaac.sensor_backend").IsaacSensorBackend(**kwargs)
