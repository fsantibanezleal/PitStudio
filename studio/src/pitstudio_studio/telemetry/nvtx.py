"""Nested NVTX step ranges for the studio GPU stages (FR-006-17, P-006-08).

The stage helper opens the range named by `PITSTUDIO_NVTX_RANGE`; a stage opens one nested range `<range>/<step>`
per declared step with `StepRanges.step`, balanced also when the body raises. Without the `nvtx` module, or
without a profiler attached, the ranges do nothing.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Iterator, Mapping
from types import ModuleType
from typing import Any

_UNSET: Any = object()
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class StepRanges:
    def __init__(self, *, env: Mapping[str, str] | None = None, nvtx_module: ModuleType | None = _UNSET) -> None:
        environment = os.environ if env is None else env
        self.range_name = environment.get("PITSTUDIO_NVTX_RANGE", "")
        if nvtx_module is _UNSET:
            try:
                import nvtx as nvtx_module  # type: ignore[no-redef]
            except Exception:
                nvtx_module = None
        self._nvtx = nvtx_module

    @contextlib.contextmanager
    def step(self, name: str) -> Iterator[None]:
        if not isinstance(name, str) or not name or _CONTROL.search(name):
            raise ValueError("a step name is a non-empty string without control characters")
        nvtx = self._nvtx
        if nvtx is None:
            yield
            return
        label = f"{self.range_name}/{name}" if self.range_name else name
        nvtx.push_range(label)
        try:
            yield
        finally:
            nvtx.pop_range()


def scoped_timer(name: str, *, warp: Any = None, **kwargs: Any) -> Any:
    """`warp.ScopedTimer(name, use_nvtx=True, ...)`; `use_nvtx` is always True."""
    if warp is None:
        import warp  # type: ignore[no-redef]
    kwargs["use_nvtx"] = True
    return warp.ScopedTimer(name, **kwargs)
