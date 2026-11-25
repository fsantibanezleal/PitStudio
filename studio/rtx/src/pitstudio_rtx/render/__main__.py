# SPDX-License-Identifier: Apache-2.0
"""Command line of the render job: `python -m pitstudio_rtx.render --recipe <yaml> --out <folder> [--dry-run]`.

A real run needs `PITSTUDIO_DATA` (the data root that holds the scene) and `PITSTUDIO_GPU_LOCK` (the machine lock file
`gpu0.compute`); it takes the lock, refuses above 80 C and ticks the shared guard before every renderer step. There is
no backend switch: the only renderer is ovrtx. Exit codes: 0 done, 1 error, 2 bad environment or arguments, 3 the guard
stopped the job (overheating or a hardware error; the output folder resumes where it stopped).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from pitstudio_rtx.render.backend import build_backend
from pitstudio_rtx.render.encode import RenderEncodeError, find_ffmpeg
from pitstudio_rtx.render.gpu import GpuError, gpu_session, load_guard_module
from pitstudio_rtx.render.recipe import RenderRecipeError, load_recipe
from pitstudio_rtx.render.run import RenderError, dry_run, run

DEFAULT_RECIPE = Path(__file__).resolve().parents[5] / "studio" / "recipes" / "render" / "bingham-flyover.yaml"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m pitstudio_rtx.render", description=__doc__)
    parser.add_argument("--recipe", type=Path, default=DEFAULT_RECIPE, help="render recipe (YAML)")
    parser.add_argument("--out", type=Path, required=True, help="output folder (stills, flyover, clip, manifest)")
    parser.add_argument("--dry-run", action="store_true", help="plan a reduced render and check every prerequisite")
    parser.add_argument("--no-resume", action="store_true", help="render every image again instead of resuming")
    return parser


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if env is None else env
    data_root, lock = env.get("PITSTUDIO_DATA"), env.get("PITSTUDIO_GPU_LOCK")
    if not data_root:
        print("error: PITSTUDIO_DATA is not set (the data root that holds processed/scene/)", file=sys.stderr)
        return 2
    if not args.dry_run and not lock:
        print("error: PITSTUDIO_GPU_LOCK is not set (the machine lock file gpu0.compute)", file=sys.stderr)
        return 2
    try:
        recipe = load_recipe(args.recipe)
        if args.dry_run:
            dry_run(recipe, data_root, args.out, run=subprocess.run, ffmpeg=find_ffmpeg(env))
            print("dry run passed")
            return 0
        guard_stop = load_guard_module().GuardStop
        try:
            with gpu_session(lock) as session:  # type: ignore[arg-type]
                result = run(
                    recipe,
                    args.out,
                    resume=not args.no_resume,
                    backend=build_backend("ovrtx"),
                    data_root=data_root,
                    tick=session.tick,
                    gpu={"name": session.device.name, "driver": session.device.driver},
                    gpu_seconds=lambda: session.gpu_seconds,
                )
        except guard_stop as stop:
            print(f"guard stop: {stop}; rerun the job to resume", file=sys.stderr)
            return 3
    except (RenderRecipeError, RenderError, RenderEncodeError, GpuError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"rendered {result.rendered} images, resumed over {result.skipped}; manifest: {result.manifest_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
