# ruff: noqa: E501
"""Shared launcher of the spec 014 local GPU integration tests (T-014-060 to T-014-063).

This module holds no test. It is imported by `tests/gpu/test_t_014_06*.py` and is locked with the first of them. The Isaac Lab environment is Python 3.12 and has no pytest (FR-000-17), so the
GPU tests run in the root environment and start the task code of the `studio/isaaclab` project as a child process:

    uv run --project studio/isaaclab --frozen python -m pitstudio_isaaclab.<module> <args>

with `PYTHONPATH=studio/isaaclab/src`. Every entry point prints, as the LAST line of stdout, one JSON object (the same convention as the capability probes of `studio/bench/_common.py`). This module
only builds the command, runs it and parses that line; nothing here calls the code under test. Tests that use it are marked `gpu` and run only on the reference machine under the `gpu0.compute`
lock (never in CI, never during the red phase).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "studio" / "isaaclab"


def run_module(module: str, *args: str, timeout: float = 3600.0, cwd: Path | None = None) -> dict[str, Any]:
    uv = shutil.which("uv")
    assert uv, "uv is needed to enter the studio/isaaclab environment"
    env = {**os.environ, "PYTHONPATH": str(PROJECT / "src")}
    proc = subprocess.run(
        [uv, "run", "--project", str(PROJECT), "--frozen", "python", "-m", f"pitstudio_isaaclab.{module}", *args],
        capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd or ROOT, check=False,
    )  # fmt: skip
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"pitstudio_isaaclab.{module} printed nothing (exit {proc.returncode}): {proc.stderr[-800:]}"
    try:
        out = json.loads(lines[-1])
    except json.JSONDecodeError as e:
        raise AssertionError(f"last line of pitstudio_isaaclab.{module} is not JSON: {lines[-1][:200]!r}") from e
    out["_returncode"] = proc.returncode
    return out
