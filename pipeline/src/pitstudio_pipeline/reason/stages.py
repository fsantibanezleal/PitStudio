"""The four `st59_*` stages of the reason lane: a pin check first, then the stage body (FR-015-01, FR-015-02).

`run_stage` is the only way a stage starts. It runs `preflight` before anything else; on a `PinError` it writes the
message (naming the file) to standard error, returns exit code 2 and never calls the launcher, so no process is
started from an unverified runtime. The stage bodies are handed to `launcher`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pitstudio_pipeline.reason.runtime import PinError, VerifiedRuntime, load_pins, verify_runtime

STAGES = ("st59_reason_bench", "st59a_vqa", "st59b_plausibility", "st59c_captions")


def preflight(stage: str, *, pins_path: Path, archive_dir: Path, runtime_dir: Path, repo_root: Path) -> VerifiedRuntime:
    """The check every stage runs first: a valid pin file, both archives and every executable matching their pins."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; known: {STAGES}")
    pins = load_pins(pins_path)
    return verify_runtime(pins, archive_dir=archive_dir, runtime_dir=runtime_dir, repo_root=repo_root)


def run_stage(
    stage: str,
    *,
    pins_path: Path,
    archive_dir: Path,
    runtime_dir: Path,
    repo_root: Path,
    launcher: Callable[..., Any],
    **stage_args: Any,
) -> int:
    """Run `preflight`, then `launcher(stage, runtime, **stage_args)`; return the stage's exit code (0 when it returns
    None). A `PinError` is written to stderr and gives exit code 2 without calling the launcher."""
    try:
        runtime = preflight(
            stage, pins_path=pins_path, archive_dir=archive_dir, runtime_dir=runtime_dir, repo_root=repo_root
        )
    except PinError as err:
        print(f"{stage}: refused to start: {err}", file=sys.stderr)
        return err.exit_code
    code = launcher(stage, runtime, **stage_args)
    return 0 if code is None else int(code)
