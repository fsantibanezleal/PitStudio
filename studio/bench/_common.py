"""Shared helpers for capability probes. Standard library only: every probe imports this from its own environment.

A probe prints one JSON object (the last line of stdout) with this shape:
    {"probe": str, "status": "pass" | "fail" | "skip", "publish": "public" | "local-only",
     "versions": {...}, "metrics": {...}, "notes": [...]}
`publish` follows the tool's licence: performance figures of NVIDIA SDKs whose licence forbids publishing benchmarks
are "local-only" and never reach the committed capabilities file.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def python_info() -> dict[str, Any]:
    exe = sys.executable
    return {
        "python": platform.python_version(),
        # a uv-managed interpreter, never the Microsoft Store shim (WindowsApps)
        "managed_interpreter": "WindowsApps" not in exe,
        "platform": f"{platform.system()} {platform.release()}",
    }


@contextmanager
def timer(metrics: dict[str, Any], key: str) -> Iterator[None]:
    t0 = time.perf_counter()
    yield
    metrics[key] = round(time.perf_counter() - t0, 4)


class SkipProbe(Exception):
    """A prerequisite outside the environment (an external tool, an owner action) is missing."""


def tmp_dir(*parts: str) -> Path:
    """Local scratch: $PITSTUDIO_TMP, else the git-ignored .tmp/ at the repo root."""
    base = Path(os.environ.get("PITSTUDIO_TMP") or Path(__file__).resolve().parents[2] / ".tmp")
    d = base.joinpath("bench", *parts)
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_probe(name: str, publish: str, body: Callable[[dict[str, Any]], None]) -> None:
    """Run `body(result)`; any exception marks the probe as failed with its message. Always prints the JSON result."""
    result: dict[str, Any] = {
        "probe": name,
        "status": "pass",
        "publish": publish,
        "versions": {},
        "metrics": {},
        "notes": [],
        **{"env": python_info()},
    }
    try:
        body(result)
    except SkipProbe as e:
        result["status"] = "skip"
        result["notes"].append(str(e))
    except Exception as e:  # a probe reports failures, it never raises
        result["status"] = "fail"
        result["error"] = f"{type(e).__name__}: {e}"
        result["notes"].append(traceback.format_exc(limit=3).strip().splitlines()[-1])
    if not result["env"]["managed_interpreter"]:
        result["status"] = "fail"
        result["notes"].append("interpreter is the Microsoft Store shim, not a uv-managed Python")
    print(json.dumps(result), flush=True)
